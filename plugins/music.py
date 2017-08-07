from plugin_manager import BasePlugin
from utils import Command, respond, process_args, split_message, find_user
from youtube_dl.utils import DownloadError
import discord.game
from random import choice
from math import ceil
import asyncio
import threading
import youtube_dl
import functools
import datetime
import time
import os


class MusicPlayer(BasePlugin):
    name = "music_player"
    default_config = {
        'music_channel': "CHANNEL ID HERE",
        'force_music_channel': False,
        'no_permission_lines': [
            "**NEGATIVE. Insufficient permissions for funky beats in channel: {}.**",
            "**NEGATIVE. Insufficient permissions for rocking you like a hurricane in channel: {}.**",
            "**NEGATIVE. Insufficient permissions for putting hands in the air in channel: {}.**",
            "**NEGATIVE. Insufficient permissions for wanting to rock in channel: {}.**",
            "**NEGATIVE. Insufficient permissions for dropping the base in channel: {}.**"
        ],
        'max_video_length': 1800,
        'max_queue_length': 30,
        'default_volume': 15,
        'allow_pause': True,
        'allow_playlists': True,
        'twitch_stream': False,
        'download_songs': True,
        'download_songs_timeout': 259200,  # Default value of three days (3*24*60*60)
        'ytdl_options': {
            'format': 'bestaudio/best',
            "cachedir": "cache/",
            'extractaudio': True,
            'audioformat': 'mp3',
            'outtmpl': 'cache/%(extractor)s-%(id)s-%(title)s.%(ext)s',
            'restrictfilenames': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'nooverwrites': True,
            'ignoreerrors': True,
            'logtostderr': False,
            'quiet': True,
            'no_warnings': False,
            'default_search': 'auto',
            'source_address': '0.0.0.0'
        }
    }

    async def activate(self):
        c = self.plugin_config
        """
        Dynamic storage.
        vc - instance of voicechat, for control purposes.
        player - instance of currently active player. DO NOT NULL, it will keep playing anyway.
        queue - queue of player objects
        vote_set - set of member ids for skip voting purposes, is emptied for every song
        time_started - time of song load, for displaying duration
        time_pause - time of pause star, for displaying duration properly with pausing
        time_skip - total time paused, for displaying duration properly with pausing
        run_timer - keep running the timer coroutine
        """
        self.vc = False
        self.player = False
        self.queue = []
        self.vote_set = set()
        self.time_started = 0
        self.time_pause = 0
        self.time_skip = 0
        self.run_timer = True

        loop = asyncio.new_event_loop()
        self.timer = threading.Thread(target=self.start_timer, args=(loop,))
        self.timer.setDaemon(True)
        self.timer.start()

        # stuff from config
        self.no_perm_lines = c.no_permission_lines
        self.ytdl_options = c.ytdl_options
        self.volume = c.default_volume
        self.max_length = c.max_video_length
        self.max_queue = c.max_queue_length
        self.ytdl_options["playlistend"] = self.max_queue+5
        self.m_channel = c.music_channel if c.force_music_channel else False
        self.allow_pause = c.allow_pause
        self.stream = c.twitch_stream
        if not "banned_members" in self.storage:
            self.storage["banned_members"] = set()
        if not "stored_songs" in self.storage:
            self.storage["stored_songs"] = {}

    async def deactivate(self):
        # stop the damn timer
        self.run_timer = False
        # serialise the queue. Hopefully.
        self.storage["serialized_queue"] = []
        if self.player and not self.player.is_done():
            self.storage["serialized_queue"].append((self.player.url, self.player.author))
            print("Serializing the current player")
            self.player.stop()
        if len(self.queue) > 0:
            for player in self.queue:
                self.storage["serialized_queue"].append((player.url, player.author))
            print("Serializing the queue")
        self.queue = []
        if self.vc:
            self.vc.disconnect()

    # Command functions

    @Command("joinvoice", "joinvc",
             category="music",
             doc="Joins same voice channel as user.")
    async def _joinvc(self, data):
        """
        Joins the same voice chat as the caller.
        Checks the permissions before joining - must be able to join, speak and not use ptt.
        """
        # leave if there's already a vc client in self.
        if self.check_ban(data.author.id):
            raise PermissionError("You are banned from using the music module.")
        if self.vc:
            await self.vc.disconnect()
        for server in self.client.servers:
            # doublecheck, just in case bot crashed earlier and discord is being weird
            if self.client.is_voice_connected(server):
                await self.client.voice_client_in(server).disconnect()
            a_voice = self.m_channel
            if not self.m_channel:
                a_voice = data.author.voice.voice_channel
            if not a_voice:
                raise PermissionError("Must be in voice chat.")
            perms = server.me.permissions_in(a_voice)
            if perms.connect and perms.speak and perms.use_voice_activation:
                self.vc = await self.client.join_voice_channel(a_voice)
                # restore the queue from storage
                if "serialized_queue" in self.storage and len(self.storage["serialized_queue"]) > 0:
                    await respond(self.client, data, "**RESTORING QUEUE. Thank you for your patience.**")
                    for x in self.storage["serialized_queue"]:
                        t_d = data
                        t_d.author.id = x[1]
                        await self.add_song(x[0], t_d)
                    await self.play_next(data)
                    await respond(self.client, data, f"**ANALYSIS: Current queue:**\n```{self.build_queue()}```")
                    self.storage["serialized_queue"] = []
                await respond(self.client, data, f"**AFFIRMATIVE. Connected to: {a_voice}.**")
            else:
                await respond(self.client, data, choice(self.no_perm_lines).format(a_voice))

    @Command("play",
             category="music",
             syntax="(URL or search query)",
             doc="Plays presented youtube video or searches for one.\nNO PLAYLISTS ALLOWED.")
    async def _playvc(self, data):
        """
        Decorates the input to make sure ytdl can eat it and filters out playlists before pushing the video in the
        queue.
        """
        if self.check_ban(data.author.id):
            raise PermissionError("You are banned from using the music module.")
        if not self.vc or (self.vc and not self.vc.is_connected()):
            await self._joinvc(data)
        if not self.check_in(data.author):
            raise PermissionError("Must be in voicechat.")
            # await respond(self.client, data, "**WARNING: Can not play music while not connected.**")
        args = data.content.split(' ', 1)
        if len(args) > 1:
            if not (args[1].startswith("http://") or args[1].startswith("https://")):
                args[1] = "ytsearch:" + args[1]
            if not self.plugin_config["allow_playlists"]:
                if args[1].find("list=") > -1:
                    raise SyntaxWarning("No playlists allowed!")
            await self.play_video(args[1], data)
        else:
            raise SyntaxError("Expected URL or search query.")

    @Command("skipsong",
             category="music",
             doc="Votes to skip the current song.\n Forces skip if the current song is stuck.")
    async def _skipvc(self, data):
        """
        Collects votes for skipping current song or skips if you got mute_members permission
        """
        if self.check_ban(data.author.id):
            raise PermissionError("You are banned from using the music module.")
        if not self.check_in(data.author):
            raise PermissionError("Must be in voicechat.")
        if (self.player and self.player.is_done() or not self.player) and len(self.queue) > 0:
            await self.play_next(data)
            await respond(self.client, data, "**AFFIRMATIVE. Forcing next song in queue.**")
            return
        self.vote_set.add(data.author.id)
        override = data.author.permissions_in(self.vc.channel).mute_members
        votes = len(self.vote_set)
        m_votes = (len(self.vc.channel.voice_members) - 1) / 2
        if votes >= m_votes or override:
            if self.player and not self.player.is_done():
                self.player.stop()
                self.vote_set = set()
            else:
                await self.play_next(self)
            await respond(self.client, data, "**AFFIRMATIVE. Skipping current song.**"
                          if not override else "**AFFIRMATIVE. Override accepted. Skipping current song.**")
        else:
            await respond(self.client, data, f"**Skip vote: ACCEPTED. {votes} out of required {ceil(m_votes)}**")

    @Command("volume",
             category="music",
             syntax="[volume from 0 to 200]",
             doc="Adjusts volume, from 0 to 200%.")
    async def _volvc(self, data):
        """
        Checks that the user didn't put in something stupid and adjusts volume.
        """
        if self.check_ban(data.author.id):
            raise PermissionError("You are banned from using the music module.")
        if not self.check_in(data.author):
            raise PermissionError("Must be in voicechat.")
        args = process_args(data.content.split())
        if len(args) > 1:
            try:
                vol = int(args[1])
            except ValueError:
                raise SyntaxError("Expected integer value between 0 and 200!")
            if vol < 0:
                vol = 0
            if vol > 200:
                raise SyntaxError("Expected integer value between 0 and 200!")
            self.volume = vol
            if self.player:
                self.player.volume = vol / 100
        else:
            await respond(self.client, data, f"**ANALYSIS: Current volume: {self.volume}%.**")

    @Command("stopsong",
             category="music",
             doc="Stops the music and empties the queue."
                 "\nRequires mute_members permission in the voice channel",
             syntax="(HARD) to erase the downloaded files.")
    async def _stopvc(self, data):
        if self.check_ban(data.author.id):
            raise PermissionError("You are banned from using the music module.")
        if not self.vc:
            return
        if self.vc and not data.author.permissions_in(self.vc.channel).mute_members:
            raise PermissionError
        if len(self.queue) > 0:
            self.queue = []
        if self.player:
            self.player.stop()
        if self.plugin_config["download_songs"]:
            args = data.content.split()
            if len(args)>1 and args[1] == 'HARD':
                for song, _ in self.storage["stored_songs"].items():
                    try:
                        os.remove(song)
                    except Exception:
                        pass
        await respond(self.client, data, "**AFFIRMATIVE. Ceasing the rhythmical noise.**")

    @Command("queue",
             category="music",
             doc="Writes out the current queue.")
    async def _queuevc(self, data):
        if self.check_ban(data.author.id):
            raise PermissionError("You are banned from using the music module.")
        t_string = "**ANALYSIS: Currently playing:**\n"
        if self.player and not self.player.is_done():
            if self.player.duration:
                t_bar = ceil((self.play_length() / self.player.duration) * 58)
                duration = f"{self.player.duration//60:02d}:{self.player.duration%60:02d}"
            else:
                t_bar = 58
                duration = " N/A "
            progress = self.play_length()
            progress = f"{progress//60:02d}:{progress%60:02d}"
            t_name = self.player.title[:37]
            if len(t_name) == 37:
                t_name += "..."
            else:
                t_name = t_name.ljust(40)
            t_string = f"{t_string}```[{t_name}]     [{progress}/{duration}]\n" \
                       f"[{'█' * int(t_bar)}{'-' * int(58 - t_bar)}]```"
        else:
            t_string = f"{t_string}```NOTHING PLAYING```"
        await respond(self.client, data, t_string)
        if len(self.queue) > 0:
            t_string = f"{self.build_queue()}"
        else:
            t_string = f"QUEUE EMPTY"
        for s in split_message(t_string, "\n"):
            await respond(self.client, data, "```"+s+"```")
        t_m, t_s = divmod(ceil(self.queue_length(self.queue)), 60)
        await respond(self.client, data, f"**ANALYSIS: Current duration: {t_m}:{t_s:02d}**")

    @Command("nowplaying",
             category="music",
             doc="Writes out the current song information.")
    async def _nowvc(self, data):
        if self.check_ban(data.author.id):
            raise PermissionError("You are banned from using the music module.")
        if self.player and not self.player.is_done():
            progress = self.play_length()
            progress = f"{progress//60}:{progress%60:02d} /"
            if self.player.duration:
                duration = f"{self.player.duration//60}:{self.player.duration%60:02d}"
            else:
                duration = " N/A "
            if self.player.description:
                desc = self.player.description.replace('https://', '').replace('http://', '')[0:1000]
            else:
                desc = "No description."
            t_string = f"**CURRENTLY PLAYING:**\n```" \
                       f"TITLE: {self.player.title}\n{'='*60}\n" \
                       f"DESCRIPTION: {desc}\n{'='*60}\n" \
                       f"DURATION: {progress} {duration}```"
            await respond(self.client, data, t_string)
        else:
            await respond(self.client, data, "**ANALYSIS: Playing nothing.\nANALYSIS: If a song is stuck, "
                                             "use !skipsong.**")

    @Command("pausesong",
             category="music",
             doc="Pauses currently playing music stream.")
    async def _pausevc(self, data):
        if self.check_ban(data.author.id):
            raise PermissionError("You are banned from using the music module.")
        if not self.allow_pause:
            raise PermissionError("Pause not allowed")
        if not self.check_in(data.author):
            raise PermissionError("Must be in voicechat.")
        if self.player and self.player.is_playing():
            self.player.pause()
            progress = self.play_length()
            progress = f"{progress//60}:{progress%60:02d} /"
            if self.player.duration:
                duration = f"{self.player.duration//60}:{self.player.duration%60:02d}"
            else:
                duration = " N/A "
            self.time_pause = time.time()
            await respond(self.client, data, f"**AFFIRMATIVE. Song paused at {progress} {duration}**")
        else:
            await respond(self.client, data, f"**NEGATIVE. Invalid pause request.**")

    @Command("resumesong",
             category="music",
             doc="Resumes currently paused music stream.")
    async def _resumevc(self, data):
        if self.check_ban(data.author.id):
            raise PermissionError("You are banned from using the music module.")
        if not self.allow_pause:
            raise PermissionError("Pause not allowed")
        if not self.check_in(data.author):
            raise PermissionError("Must be in voicechat.")
        if self.player and not self.player.is_playing() and not self.player.is_done():
            self.player.resume()
            self.time_skip += time.time() - self.time_pause
            self.time_pause = 0
            await respond(self.client, data, "**AFFIRMATIVE. Resuming song.**")
        else:
            await respond(self.client, data, "**NEGATIVE. No song to resume.**")

    @Command("delsong",
             category="music",
             syntax="[queue index]",
             doc="Deletes a song from the queue by it's position number, starting from 1."
                 "\nRequires mute_members permission in the voice channel")
    async def _delvc(self, data):
        if self.check_ban(data.author.id):
            raise PermissionError("You are banned from using the music module.")
        if not self.vc:
            return
        if self.vc and not data.author.permissions_in(self.vc.channel).mute_members:
            raise PermissionError
        args = data.content.split(" ", 1)
        try:
            pos = int(args[1])
        except ValueError:
            raise SyntaxError("Expected an integer value!")
        if pos < 1 or pos > len(self.queue):
            raise SyntaxError("Index out of list.")
        t_p = self.queue.pop(pos - 1)
        await respond(self.client, data, f"**AFFIRMATIVE. Removed song \"{t_p.title}\" from position {pos}.**")

    @Command("musicban",
             category="music",
             perms={"mute_members"},
             doc="Bans members from using the music module.")
    async def _musicban(self, data):
        args = process_args(data.content.split())
        t_string = ""
        for uid in args[1:]:
            t_member = find_user(data.server, uid)
            if t_member:
                self.storage["banned_members"].add(t_member.id)
                t_string = f"{t_string} <@{t_member.id}>\n"
        await respond(self.client, data, f"**AFFIRMATIVE. Users banned from using music module:**\n"
                                         f"{t_string}")

    @Command("musicunban",
             category="music",
             perms={"mute_members"},
             doc="Unbans members from using the music module.")
    async def _musicunban(self, data):
        args = process_args(data.content.split())
        t_string = ""
        for uid in args[1:]:
            t_member = find_user(data.server, uid)
            if t_member:
                self.storage["banned_members"].remove(t_member.id)
                t_string = f"{t_string} <@{t_member.id}>\n"
        await respond(self.client, data, f"**AFFIRMATIVE. Users unbanned from using music module:**\n"
                                         f"{t_string}")

    @Command("dumpqueue",
             category="music",
             doc="Serializes and dumps the currently playing queue.\nRequires mute_members permission in the "
                 "voice channel")
    async def _dumpvc(self, data):
        if self.check_ban(data.author.id):
            raise PermissionError("You are banned from using the music module.")
        if not self.vc:
            return
        if self.vc and not data.author.permissions_in(self.vc.channel).mute_members:
            raise PermissionError
        t_string = ""
        if self.player:
            t_string = f"!\"{self.player.url}\" "
        for player in self.queue:
            t_string = f"{t_string}!\"{player.url}\" "
        if t_string != "":
            await respond(self.client, data, f"**AFFIRMATIVE. Current queue:**\n"
                                             f"```{t_string}```")

    @Command("appendqueue",
             category="music",
             doc="Appends a number of songs to the queue, takes output from dumpqueue."
                 "\nRequires mute_members permission in the voice channel",
             syntax="[song] or [!\"ytsearch:song with spaces\"], accepts multiple.")
    async def _appendvc(self, data):
        if self.check_ban(data.author.id):
            raise PermissionError("You are banned from using the music module.")
        if not self.vc:
            await self._joinvc(data)
        if self.vc and not data.author.permissions_in(self.vc.channel).mute_members:
            raise PermissionError
        args = process_args(data.content.split())
        if len(args) > 1:
            await respond(self.client, data, "**AFFIRMATIVE. Extending queue.**")
            for arg in args[1:]:
                await self.add_song(arg, data)
            await respond(self.client, data, f"**ANALYSIS: Current queue:**")
            for s in split_message(self.build_queue(), "\n"):
                await respond(self.client, data, f"```{s}```")
            if not self.player or self.player and self.player.is_done():
                await self.play_next(data)
        else:
            raise SyntaxError("Expected arguments!")

    @Command("delqueue",
             category="music",
             doc="Erases serialised queue. Useful if bot was shut down with ridiculous queue saved.",
             perms="mute_members")
    async def _delqueue(self, data):
        if self.check_ban(data.author.id):
            raise PermissionError("You are banned from using the music module.")
        await respond(self.client, data, "**AFFIRMATIVE. Purging.**")
        self.storage["serialized_queue"] = []

    # Music playing

    """
    a bunch of functions that handle creation of players and queue.
    create_player creates the player object, returning a list of players (playlist support) and a playlist name.
    play_video receives a URL or search query and handles starting playback if nothing is playing
    process_queue receives a list of players and adds it to queue
    play_next stops current song and advances on next in queue
    add_song creates a player and adds it to queue, no questions asked
    """

    async def create_player(self, url, *, ytdl_options=None, **kwargs):
        """|coro|

        Creates a stream player for youtube or other services that launches
        in a separate thread to play the audio.

        The player uses the ``youtube_dl`` python library to get the information
        required to get audio from the URL. Since this uses an external library,
        you must install it yourself. You can do so by calling
        ``pip install youtube_dl``.

        You must have the ffmpeg or avconv executable in your path environment
        variable in order for this to work.

        The operations that can be done on the player are the same as those in
        :meth:`create_stream_player`. The player has been augmented and enhanced
        to have some info extracted from the URL. If youtube-dl fails to extract
        the information then the attribute is ``None``. The ``yt``, ``url``, and
        ``download_url`` attributes are always available.

        +---------------------+---------------------------------------------------------+
        |      Operation      |                       Description                       |
        +=====================+=========================================================+
        | player.yt           | The `YoutubeDL <ytdl>` instance.                        |
        +---------------------+---------------------------------------------------------+
        | player.url          | The URL that is currently playing.                      |
        +---------------------+---------------------------------------------------------+
        | player.download_url | The URL that is currently being downloaded to ffmpeg.   |
        +---------------------+---------------------------------------------------------+
        | player.title        | The title of the audio stream.                          |
        +---------------------+---------------------------------------------------------+
        | player.description  | The description of the audio stream.                    |
        +---------------------+---------------------------------------------------------+
        | player.uploader     | The uploader of the audio stream.                       |
        +---------------------+---------------------------------------------------------+
        | player.upload_date  | A datetime.date object of when the stream was uploaded. |
        +---------------------+---------------------------------------------------------+
        | player.duration     | The duration of the audio in seconds.                   |
        +---------------------+---------------------------------------------------------+
        | player.likes        | How many likes the audio stream has.                    |
        +---------------------+---------------------------------------------------------+
        | player.dislikes     | How many dislikes the audio stream has.                 |
        +---------------------+---------------------------------------------------------+
        | player.is_live      | Checks if the audio stream is currently livestreaming.  |
        +---------------------+---------------------------------------------------------+
        | player.views        | How many views the audio stream has.                    |
        +---------------------+---------------------------------------------------------+

        .. _ytdl: https://github.com/rg3/youtube-dl/blob/master/youtube_dl/YoutubeDL.py#L128-L278

        Examples
        ----------

        Basic usage: ::

            voice = await client.join_voice_channel(channel)
            player = await voice.create_ytdl_player('https://www.youtube.com/watch?v=d62TYemN6MQ')
            player.start()

        Parameters
        -----------
        url : str
            The URL that ``youtube_dl`` will take and download audio to pass
            to ``ffmpeg`` or ``avconv`` to convert to PCM bytes.
        ytdl_options : dict
            A dictionary of options to pass into the ``YoutubeDL`` instance.
            See `the documentation <ytdl>`_ for more details.
        \*\*kwargs
            The rest of the keyword arguments are forwarded to
            :func:`create_ffmpeg_player`.

        Raises
        -------
        ClientException
            Popen failure from either ``ffmpeg``/``avconv``.

        Returns
        --------
        StreamPlayer
            An augmented StreamPlayer that uses ffmpeg.
            See :meth:`create_stream_player` for base operations.
        """
        use_avconv = kwargs.get('use_avconv', False)
        opts = {
            'format': 'webm[abr>0]/bestaudio/best',
            'prefer_ffmpeg': not use_avconv
        }

        if ytdl_options is not None and isinstance(ytdl_options, dict):
            opts.update(ytdl_options)

        ydl = youtube_dl.YoutubeDL(opts)
        loop = asyncio.get_event_loop()
        func = functools.partial(ydl.extract_info, url, download=self.plugin_config["download_songs"])
        data = await loop.run_in_executor(None, func)
        if not data:
            raise DownloadError("Could not download video(s).")
        if "entries" in data:
            t_players = []
            for info in data["entries"]:
                if info is not None:
                    self.logger.info(f'processing URL {info["title"]}')
                    if self.plugin_config["download_songs"]:
                        filename = ydl.prepare_filename(info)
                    else:
                        filename = info['url']
                    self.storage["stored_songs"][filename] = time.time()
                    t_player = self.vc.create_ffmpeg_player(filename, **kwargs)
                    t_player.download_url = filename
                    t_player.url = info.get('webpage_url')
                    t_player.yt = ydl
                    t_player.views = info.get('view_count')
                    t_player.is_live = bool(info.get('is_live'))
                    t_player.likes = info.get('like_count')
                    t_player.dislikes = info.get('dislike_count')
                    t_player.duration = info.get('duration', 0)
                    t_player.uploader = info.get('uploader')

                    is_twitch = 'twitch' in url

                    if is_twitch:
                        # twitch has 'title' and 'description' sort of mixed up.
                        t_player.title = info.get('description')
                        t_player.description = None
                    else:
                        t_player.title = info.get('title')
                        t_player.description = info.get('description')

                    # upload date handling
                    date = info.get('upload_date')
                    if date:
                        try:
                            date = datetime.datetime.strptime(date, '%Y%M%d').date()
                        except ValueError:
                            date = None

                    t_player.upload_date = date
                    t_players.append(t_player)
            return t_players, data.get('title', False)
        else:
            info = data
            self.logger.info(f'playing URL {url}')
            if self.plugin_config["download_songs"]:
                filename = ydl.prepare_filename(info)
            else:
                filename = info['url']
            self.storage["stored_songs"][filename] = time.time()
            player = self.vc.create_ffmpeg_player(filename, **kwargs)

            # set the dynamic attributes from the info extraction
            player.download_url = filename
            player.url = info.get('webpage_url')
            player.yt = ydl
            player.views = info.get('view_count')
            player.is_live = bool(info.get('is_live'))
            player.likes = info.get('like_count')
            player.dislikes = info.get('dislike_count')
            player.duration = info.get('duration')
            player.uploader = info.get('uploader')

            is_twitch = 'twitch' in url
            if is_twitch:
                # twitch has 'title' and 'description' sort of mixed up.
                player.title = info.get('description')
                player.description = None
            else:
                player.title = info.get('title')
                player.description = info.get('description')

            # upload date handling
            date = info.get('upload_date')
            if date:
                try:
                    date = datetime.datetime.strptime(date, '%Y%M%d').date()
                except ValueError:
                    date = None

            player.upload_date = date
            return [player], False

    async def play_video(self, vid, data):
        """
        Processes provided video request, either starting to play it instantly or adding it to queue.
        :param vid: URL or ytsearch: query to process or NEXT for skipping
        :param data: message data for responses
        """
        if self.player and self.player.error:
            print(self.player.error)
        before_args = "" if self.plugin_config["download_songs"] else " -reconnect 1 -reconnect_streamed 1 " \
                                                                      "-reconnect_delay_max 30"
        t_loop = asyncio.get_event_loop()
        if self.player and not self.player.is_done() or len(self.queue) > 0:
            t_players = []
            try:
                t_players, t_playlist = await self.create_player(vid, ytdl_options=self.ytdl_options,
                                                                 before_options=before_args,
                                                                 after=lambda: t_loop.create_task(self.play_next(
                                                                         data)))
            except DownloadError as e:
                await respond(self.client, data, f"**NEGATIVE. Could not load song.\n{e}**")
                return
            t_m, t_s = divmod(ceil(self.queue_length(self.queue)), 60)
            if not t_playlist:
                await respond(self.client, data, f"**AFFIRMATIVE. Adding \"{t_players[0].title}\" to queue.**")
            else:
                await respond(self.client, data, f"**AFFIRMATIVE. Adding \"{t_playlist}\" to queue.**")
            await self.process_queue(t_players, data)
            await respond(self.client, data, f"**ANALYSIS: Current queue:**\n")
            for s in split_message(self.build_queue(), "\n"):
                await respond(self.client, data, f"```{s}```")
            await respond(self.client, data, f"**ANALYSIS: time until your song: {t_m}:{t_s:02d}**")
        else:
            self.vote_set = set()
            # self.logger.debug(time.time() - self.time_started)
            # creates a player with a callback to play next video
            t_players = []
            try:
                t_players, t_playlist = await self.create_player(vid, ytdl_options=self.ytdl_options,
                                                                 before_options=before_args,
                                                                 after=lambda: t_loop.create_task(self.play_next(
                                                                         data)))
            except DownloadError as e:
                await respond(self.client, data, f"**NEGATIVE. Could not load song.\n{e}**")
                return
            self.player = t_players[0]
            if self.player.duration and self.player.duration <= self.max_length:
                self.player.author = data.author.id
                self.player.volume = self.volume / 100
                self.player.start()
                self.logger.info(f"Playing {self.player.title}. Submitted by {self.player.author}.")
                self.time_started = time.time()
                self.time_skip = 0
                await respond(self.client, data, f"**CURRENTLY PLAYING: \"{self.player.title}\"**")
            else:
                self.player.stop()
                await respond(self.client, data, f"**NEGATIVE. ANALYSIS: Song over the maximum duration of "
                                                 f"{self.max_length//60}:{self.max_length%60:02d}.**")
            if len(t_players) > 1:
                await self.process_queue(t_players[1:], data)
                await respond(self.client, data, f"**ANALYSIS: Current queue:**")
                for s in split_message(self.build_queue(), "\n"):
                    await respond(self.client, data, f"```{s}```")

    async def process_queue(self, players, data):
        """
        A function to go over a list of players and add them to queue, checking length and queue length
        :param players: a list of player objects
        :param data: message data for responding
        :return: nothing
        """
        if len(players) > 0:
            for t_player in players:
                if len(self.queue) < self.max_queue:
                    if t_player.duration > self.max_length:
                        await respond(self.client, data, f"**NEGATIVE. ANALYSIS: Song {t_player.title:40} over the "
                                                         f"maximum duration of "
                                                         f"{self.max_length//60}:{self.max_length%60:02d}.**")
                    else:
                        t_player.author = data.author.id
                        self.queue.append(t_player)
                        self.logger.info(f"Adding {t_player.title} to music queue. Submitted by {t_player.author}.")
                else:
                    await respond(self.client, data, f"**NEGATIVE. ANALYSIS: Queue full. Dropping \"{t_player.title}"
                                                     f"\".\nCurrent queue:**\n```{self.build_queue()}```")
                    break
        else:
            return

    async def play_next(self, data):
        """
        Plays next song in queue
        :param data: message data for responding
        :return:
        """
        if len(self.queue) > 0:
            if self.player:
                self.player.stop()
            self.player = self.queue.pop(0)
            self.player.volume = self.volume / 100
            self.player.start()
            self.logger.info(f"Playing {self.player.title}. Submitted by {self.player.author}.")
            self.time_started = time.time()
            self.time_skip = 0
            await respond(self.client, data, f"**CURRENTLY PLAYING: \"{self.player.title}\"**")
        else:
            if self.player:
                self.player.stop()
            await respond(self.client, data, "**ANALYSIS: Queue complete.**")

    async def add_song(self, vid, data):
        """
        Adds songs to queue, no question asked
        :param vid: URL or search query
        :param data: message data for responding
        :return:
        """
        before_args = "" if self.plugin_config["download_songs"] else " -reconnect 1 -reconnect_streamed 1 " \
                                                                      "-reconnect_delay_max 30"
        t_loop = asyncio.get_event_loop()
        try:
            t_players, t_playlist = await self.create_player(vid, ytdl_options=self.ytdl_options,
                                                             before_options=before_args,
                                                             after=lambda: t_loop.create_task(self.play_next(data)))
        except DownloadError:
            await respond(self.client, data, "**NEGATIVE. Could not load song.**")
            return
        for t_player in t_players:
            t_player.author = data.author.id
            self.logger.info(f"Adding {t_player.title} to music queue. Submitted by {t_player.author}.")
            self.queue.append(t_player)

    def start_timer(self, loop):
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.display_time())
        except Exception:
            self.logger.exception("Error starting timer. ", exc_info=True)

    async def display_time(self):
        """
        Updates client status every ten seconds based on music status.
        Also runs the every-few-second stuff
        """
        playing = True
        while self.run_timer:
            await asyncio.sleep(10)

            # check old songs
            if self.plugin_config["download_songs"]:
                del_list = []
                for song, time_added in self.storage["stored_songs"].items():
                    if time.time() - time_added > self.plugin_config["download_songs_timeout"]:
                        del_list.append(song)
                for song in del_list:
                    try:
                        os.remove(song)
                        self.storage["stored_songs"].pop(song)
                        print(f"Attempting to remove {song}.")
                    except Exception:
                        self.logger.exception("Error pruning song cache. ", exc_info=True)

            # time display
            game = None
            if self.player and not self.player.is_done():
                if self.player.is_playing():
                    progress = self.play_length()
                    progress = f"{progress//60}:{progress%60:02d}"
                    if self.player.duration:
                        duration = self.player.duration
                        duration = f"{duration//60}:{duration%60:02d}"
                    else:
                        duration = "N/A"
                    if not self.stream:
                        game = discord.Game(name=f"[{progress}/{duration}]")
                    else:
                        game = discord.Game(name=f"[{progress}/{duration}]", url=self.stream, type=1)
                    playing = True
                else:
                    game = discord.Game(name=f"[PAUSED]")
            if game or playing:
                await self.client.change_presence(game=game)
            if playing and not game:
                playing = False

    # Utility functions

    def build_queue(self):
        """
        builds a nice newline separated queue
        :return: returns queue string
        """
        t_string = ""
        for k, player in enumerate(self.queue):
            title = player.title[0:44].ljust(47) if len(player.title) < 44 else player.title[0:44] + "..."
            if player.duration:
                mins, secs = divmod(player.duration, 60)
            else:
                mins, secs = 99, 99
            t_string = f"{t_string}[{k+1:02d}][{title}][{mins:02d}:{secs:02d}]\n"
        return t_string if t_string != "" else f"[{'EMPTY'.center(58)}]"

    def queue_length(self, queue):
        """
        Calculates the complete length of the current queue, including song playing
        :param queue: the queue of player objects. Takes queue in case you want to keep something out
        :return: the duration in seconds
        """
        if self.player and not self.player.is_done() and self.player.duration:
            t = self.player.duration - self.play_length()
        else:
            t = 0
        for player in queue:
            if player.duration:
                t += player.duration
        return t

    def play_length(self):
        """
        Calculates the duration of the current song, including time skipped by pausing
        :return: duration in seconds
        """
        t = 0
        if self.player and not self.player.is_done():
            t_skip = 0
            if self.time_pause > 0:
                t_skip = time.time() - self.time_pause
            t = min(ceil(time.time() - self.time_started - self.time_skip - t_skip), self.player.duration if
                    self.player.duration else self.max_length)
        return t

    def check_in(self, author):
        """
        :param author: author from message data
        :return: is he in same vc channel?
        """
        return self.vc and self.vc.is_connected() and author in self.vc.channel.voice_members

    def check_ban(self, uid):
        if "banned_members" in self.storage:
            return uid in self.storage["banned_members"]
        else:
            self.storage["banned_members"] = set()
            return False
