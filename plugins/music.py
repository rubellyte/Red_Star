from plugin_manager import BasePlugin
from utils import Command, respond, process_args
from random import choice
from asyncio import get_event_loop
from math import ceil
from youtube_dl.utils import DownloadError
import time


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
            "**NEGATIVE. Insufficient permissions for dropping the beat in channel: {}.**"
        ],
        'max_video_length': 1800,
        'max_queue_length': 30,
        'default_volume': 15,
        'allow_pause': True,
        'ytdl_options': {
            'format': 'bestaudio/best',
            'extractaudio': True,
            'audioformat': 'mp3',
            'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
            'restrictfilenames': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'quiet': True,
            'no_warnings': False,
            'default_search': 'auto',
            'source_address': '0.0.0.0'
        }
    }

    async def activate(self):
        c = self.plugin_config
        self.vc = False
        self.player = False
        self.queue = []
        self.vote_set = set()
        # stuff from config
        self.no_perm_lines = c.no_permission_lines
        self.ytdl_options = c.ytdl_options
        self.volume = c.default_volume
        self.max_length = c.max_video_length
        self.max_queue = c.max_queue_length
        self.m_channel = c.music_channel if c.force_music_channel else False
        self.time_started = 0
        self.allow_pause = c.allow_pause
        self.time_pause = 0
        self.time_skip = 0

    async def deactivate(self):
        if self.player:
            self.player.stop()
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
        if self.vc:
            self.vc.disconnect()
        for server in self.client.servers:
            # doublecheck, just in case bot crashed earlier and discord is being weird
            if self.client.is_voice_connected(server):
                await self.client.voice_client_in(server).disconnect()
            a_voice = self.m_channel
            if not self.m_channel:
                a_voice = data.author.voice.voice_channel
            perms = server.me.permissions_in(a_voice)
            if perms.connect and perms.speak and perms.use_voice_activation:
                self.vc = await self.client.join_voice_channel(a_voice)
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
        if not self.vc:
            await self._joinvc(data)
        if not self.check_in(data.author):
            raise PermissionError("Must be in voicechat.")
            # await respond(self.client, data, "**WARNING: Can not play music while not connected.**")
        args = data.content.split(' ', 1)
        if len(args) > 1:
            if not (args[1].startswith("http://") or args[1].startswith("https://")):
                args[1] = "ytsearch:" + args[1]
            if args[1].find("list=") > -1:
                raise SyntaxWarning("No playlists allowed!")
            await self.play_video(args[1], data)
        else:
            raise SyntaxError("Expected URL or search query.")

    @Command("skipsong",
             category="music",
             doc="Votes to skip the current song.")
    async def _skipvc(self, data):
        """
        Collects votes for skipping current song or skips if you got mute_members permission
        """
        if not self.check_in(data.author):
            raise PermissionError("Must be in voicechat.")
        if self.player and self.player.is_done() and len(self.queue) > 0:
            await self.play_next(data)
            await respond(self.client, data, "**AFFIRMATIVE. Forcing next song in queue.**")
            return
        self.vote_set.add(data.author.id)
        override = data.author.permissions_in(self.vc.channel).mute_members
        votes = len(self.vote_set)
        m_votes = (len(self.vc.channel.voice_members) - 1) / 2
        if votes >= m_votes or override:
            if self.player:
                self.player.stop()
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
                vol = 200
            self.volume = vol
            if self.player:
                self.player.volume = vol / 100
        else:
            await respond(self.client, data, f"**ANALYSIS: Current volume: {self.volume}%.**")

    @Command("stopsong",
             perms={"mute_members"},
             category="music",
             doc="Stops the music and empties the queue.")
    async def _stopvc(self, data):
        if len(self.queue) > 0:
            self.queue = []
        if self.player:
            self.player.stop()
        await respond(self.client, data, "**AFFIRMATIVE. Ceasing the rhythmical noise.**")

    @Command("queue",
             category="music",
             doc="Writes out the current queue.")
    async def _queuevc(self, data):
        if len(self.queue) > 0:
            t_m, t_s = divmod(ceil(self.queue_length(self.queue)), 60)
            await respond(self.client, data, f"**ANALYSIS: Current queue:**\n```{self.build_queue()}```\n"
                                             f"**ANALYSIS: Current duration: {t_m}:{t_s:02d}**")
        else:
            await respond(self.client, data, "**ANALYSIS: Queue empty.**")

    @Command("nowplaying",
             category="music",
             doc="Writes out the current song information.")
    async def _nowvc(self, data):
        if self.player and not self.player.is_done():
            progress = self.play_length()
            progress = f"{progress//60}:{progress%60:02d} /"
            desc = self.player.description.replace('https://', '').replace('http://', '')[0:1000]
            t_string = f"**CURRENTLY PLAYING:**\n```" \
                       f"TITLE: {self.player.title}\n{'='*60}\n" \
                       f"DESCRIPTION: {desc}\n{'='*60}\n" \
                       f"DURATION: {progress} {self.player.duration//60}:{self.player.duration%60:02d}```"
            await respond(self.client, data, t_string)

    @Command("pausesong",
             category="music",
             doc="Pauses currently playing music stream.")
    async def _pausevc(self, data):
        if not self.allow_pause:
            raise PermissionError("Pause not allowed")
        if not self.check_in(data.author):
            raise PermissionError("Must be in voicechat.")
        if self.player and self.player.is_playing():
            self.player.pause()
            progress = self.play_length()
            progress = f"{progress//60}:{progress%60:02d} /"
            self.time_pause = time.time()
            await respond(self.client, data, f"**AFFIRMATIVE. Song paused at {progress} "
                                             f"{self.player.duration//60}:{self.player.duration%60:02d}**")
        else:
            await respond(self.client, data, f"**NEGATIVE. Invalid pause request.**")

    @Command("resumesong",
             category="music",
             doc="Resumes currently paused music stream.")
    async def _resumevc(self, data):
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

    # Music playing

    async def play_video(self, vid, data):
        """
        Processes provided video request, either starting to play it instantly or adding it to queue.
        :param vid: URL or ytsearch: query to process or NEXT for skipping
        :param data: message data for responses
        """
        if self.player and self.player.error:
            print(self.player.error)
        before_args = " -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 15"
        t_loop = get_event_loop()
        if self.player and not self.player.is_done() or len(self.queue) > 0:
            try:
                t_player = await self.vc.create_ytdl_player(vid, ytdl_options=self.ytdl_options,
                                                            before_options=before_args,
                                                            after=lambda: t_loop.create_task(self.play_next(data)))
            except DownloadError:
                await respond(self.client, data, "**NEGATIVE. Could not load song.**")
                raise Exception
            if t_player.duration > self.max_length:
                await respond(self.client, data, f"**NEGATIVE. ANALYSIS: Song over the maximum duration of "
                                                 f"{self.max_length//60}:{self.max_length%60:02d}.**")
                return
            if len(self.queue) < self.max_queue:
                t_m, t_s = divmod(ceil(self.queue_length(self.queue)), 60)
                self.queue.append(t_player)
                await respond(self.client, data, f"**AFFIRMATIVE. ADDING \"{t_player.title}\" to queue.\n"
                                                 f"Current queue:**\n```{self.build_queue()}```\n"
                                                 f"**ANALYSIS: time until your song: {t_m}:{t_s:02d}**")
            else:
                await respond(self.client, data, f"**NEGATIVE. ANALYSIS: Queue full. Dropping \"{t_player.title}\".\n"
                                                 f"Current queue:**\n```{self.build_queue()}```")
        else:
            self.vote_set = set()
            # self.logger.debug(time.time() - self.time_started)
            # creates a player with a callback to play next video
            try:
                self.player = await self.vc.create_ytdl_player(vid, ytdl_options=self.ytdl_options,
                                                               before_options=before_args,
                                                               after=lambda: t_loop.create_task(self.play_next(data)))
            except DownloadError:
                await respond(self.client, data, "**NEGATIVE. Could not load song.**")
                raise Exception
            if self.player.duration <= self.max_length:
                self.player.volume = self.volume / 100
                self.player.start()
                self.time_started = time.time()
                self.time_skip = 0
                await respond(self.client, data, f"**CURRENTLY PLAYING: \"{self.player.title}\"**")
            else:
                self.player.stop()
                await respond(self.client, data, f"**NEGATIVE. ANALYSIS: Song over the maximum duration of "
                                                 f"{self.max_length//60}:{self.max_length%60:02d}.**")

    async def play_next(self, data):
        if len(self.queue) > 0:
            if self.player:
                self.player.stop()
            self.player = self.queue.pop(0)
            self.player.volume = self.volume / 100
            self.player.start()
            self.time_started = time.time()
            self.time_skip = 0
            await respond(self.client, data, f"**CURRENTLY PLAYING: \"{self.player.title}\"**")
        else:
            if self.player:
                self.player.stop()
            await respond(self.client, data, "**ANALYSIS: Queue complete.**")

    # Utility functions

    def build_queue(self):
        """
        builds a nice newline separated queue
        :return: returns queue string
        """
        t_string = ""
        for player in self.queue:
            title = player.title[0:36].ljust(39) if len(player.title) < 36 else player.title[0:36] + "..."
            mins, secs = divmod(player.duration, 60)
            t_string = f"{t_string}{title} [{mins}:{secs:02d}]\n"
        return t_string

    def queue_length(self, queue):
        """
        Calculates the complete length of the current queue, including song playing
        :param queue: the queue of player objects. Takes queue in case you want to keep something out
        :return: the duration in seconds
        """
        if self.player and not self.player.is_done():
            t = self.player.duration - self.play_length()
        else:
            t = 0
        for player in queue:
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
            t = ceil(time.time() - self.time_started - self.time_skip-t_skip)
        return t

    def check_in(self, author):
        """
        :param author: author from message data
        :return: is he in same vc channel?
        """
        return self.vc and author in self.vc.channel.voice_members
