from plugin_manager import BasePlugin
from utils import Command, respond, process_args, split_message, find_user
from youtube_dl.utils import DownloadError
from discord import InvalidArgument, ClientException
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
        'default': {
            'music_channel': "CHANNEL ID HERE",
            'force_music_channel': False,
            'max_video_length': 1800,
            'max_queue_length': 30,
            'default_volume': 15,
            'allow_pause': True,
            'allow_playlists': True,
            'idle_time': 30,  # seconds/10
            'idle_terminate': 60  # seconds/10
        },
        'no_permission_lines': [
            "**NEGATIVE. Insufficient permissions for funky beats in channel: {}.**",
            "**NEGATIVE. Insufficient permissions for rocking you like a hurricane in channel: {}.**",
            "**NEGATIVE. Insufficient permissions for putting hands in the air in channel: {}.**",
            "**NEGATIVE. Insufficient permissions for wanting to rock in channel: {}.**",
            "**NEGATIVE. Insufficient permissions for dropping the base in channel: {}.**"
        ],
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
            'playlistend': 35,  # set to queue length + some (in case it doesn't load full)
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

    class ServerStorage:
        server = None
        config = None

        vc = None  # voice chat instance
        player = None  # active player instance
        queue = []  # queue of players
        vote_set = set()

        time_started = 0  # time storage, for length calculating purposes
        time_pause = 0  # time of pause start
        time_skip = 0  # total time spent paused

        idle_count = 0

        volume = 10

        def __init__(self, parent, srv, config):
            """
            Creates new server-speific instance
            :param srv: discord.server object
            """
            self.parent = parent
            self.server = srv
            self.vc = srv.voice_client
            self.config = config
            self.volume = self.config["default_volume"]

        # Connection functions

        async def connect(self, data):
            """
            Connect to a channel in the specific server
            :param: false or default channel id
            :param data: message data to get author out of
            :return: True if connected, False if something went wrong
            """
            if self.vc:
                await self.vc.disconnect()
            if self.config["force_music_channel"]:
                m_channel = self.parent.plugins.channel_manager.get_channel(self.server, "voice_music")
                m_channel = self.parent.client.get_channel(m_channel)
            elif data.author.voice.voice_channel:
                m_channel = data.author.voice.voice_channel
            else:
                raise PermissionError("Must be in voice chat.")
            perms = self.server.me.permissions_in(m_channel)
            if perms.connect and perms.speak and perms.use_voice_activation:
                try:
                    self.vc = await self.parent.client.join_voice_channel(m_channel)
                    if self.player and not self.player.is_done() and not self.player.is_playing():
                        self.player.resume()
                    return m_channel
                except(InvalidArgument, ClientException):
                    self.parent.logger.exception("Error connecting to voice chat. ", exc_info=True)
                    return False
            else:
                return False

        async def connected(self, data):
            if not self.vc or not self.vc.is_connected():
                await self.connect(data)

        async def disconnect(self):
            """
            Disconnects the current VC instance for this server
            """
            if self.vc:
                await self.vc.disconnect()

        async def check_connection(self):
            if self.vc:
                t_me = self.server.me
                for t_member in self.vc.channel.voice_members:
                    if t_member != t_me:
                        self.idle_count = 0
                        break
                else:
                    self.idle_count += 1
                if self.idle_count == self.config["idle_time"]:
                    self.pause_song()
                    await self.disconnect()
                    self.parent.logger.info(f"Leaving voice on {self.server.name} due to inactivity.")
                if self.idle_count == self.config["idle_terminate"]:
                    self.stop_song()
                    self.parent.logger.info(f"Terminating queue on {self.server.name} due to inactivity.")

        # Playback functions

        async def play_song(self, vid, data):
            before_args = "" if self.parent.plugin_config["download_songs"] else " -reconnect 1 -reconnect_streamed " \
                                                                                 "1 -reconnect_delay_max 30"
            t_loop = asyncio.get_event_loop()
            try:
                t_players, t_id = await self.parent.create_player(vid, self.vc,
                                                                  ytdl_options=self.parent.plugin_config[
                                                                      "ytdl_options"],
                                                                  before_options=before_args,
                                                                  after=lambda: t_loop.create_task(self.play_next(
                                                                          data)))
            except DownloadError as e:
                self.parent.logger.info(f"Error loading songs. {e}")
                return False
            t_count = len(t_players)
            t_added = 0
            t_m, t_s = divmod(ceil(self.queue_length(self.queue)), 60)
            if (not self.player or self.player.is_done()) and not self.queue:
                self.player = t_players.pop(0)
                while self.player.duration > self.config["max_video_length"] and t_players:
                    self.player = t_players.pop(0)
                if self.player.duration > self.config["max_video_length"] and not t_players:
                    return False
                self.vote_set = set()
                self.player.volume = self.volume / 100
                self.player.start()
                self.time_started = time.time()
                self.time_skip = 0
                t_added += 1
            t_queue = self.add_songs(t_players)

            # all the cosmetic output
            if t_queue and t_id:
                await respond(self.parent.client, data, f"**AFFIRMATIVE. ANALYSIS: Processed: {t_count} "
                                                        f"songs from \"{t_id}\" "
                                                        f"playlist.\nAdded: {t_added+t_queue} songs.**")
            elif t_added:
                await respond(self.parent.client, data, f"**AFFIRMATIVE. Adding \"{self.player.title}\" to queue.**")
            if t_added == 0 or t_queue:
                await respond(self.parent.client, data, f"**ANALYSIS: Current queue:**")
                for s in split_message(self.build_queue(), splitter="\n"):
                    await respond(self.parent.client, data, f"```{s}```")
            if t_added == 0:
                await respond(self.parent.client, data, f"**Time until your song: {t_m}:{t_s:02d}.**")
            return t_queue + t_added, t_count if t_queue else False

        async def play_next(self, data):
            if self.player and not self.player.is_done():
                self.player.stop()
            elif len(self.queue) > 0:
                self.player = self.queue.pop(0)
                self.player.volume = self.volume / 100
                self.player.start()
                self.time_started = time.time()
                self.time_skip = 0
                self.parent.logger.info(f"Playing {self.player.title} on {self.server.name}.")
                await respond(self.parent.client, data, f"**CURRENTLY PLAYING: \"{self.player.title}\"**")
            else:
                await respond(self.parent.client, data, "**ANALYSIS: Queue complete.**")

        def add_songs(self, players):
            """
            Processes a list of player instances for duration and queue length.
            :param players: list of players
            :return:
            """
            if len(players) > 0:
                t_count = 0
                for player in players:
                    if len(self.queue) < self.config["max_queue_length"]:
                        if player.duration < self.config["max_video_length"]:
                            t_count += 1
                            self.queue.append(player)
                            self.parent.logger.info(f"Appending {player.title} to queue of {self.server.name}.")
                self.parent.logger.info(f"{t_count} songs appended.")
                return t_count if t_count > 0 else False
            else:
                return False

        async def add_song(self, vid, data):
            """
            Adds songs to queue, no question asked
            :param vid: URL or search query
            :param data: message data for responding
            :return:
            """
            before_args = "" if self.parent.plugin_config["download_songs"] else " -reconnect 1 -reconnect_streamed " \
                                                                                 "1 -reconnect_delay_max 30"
            t_loop = asyncio.get_event_loop()
            try:
                t_players, t_id = await self.parent.create_player(vid, self.vc,
                                                                  ytdl_options=self.parent.plugin_config[
                                                                      "ytdl_options"],
                                                                  before_options=before_args,
                                                                  after=lambda: t_loop.create_task(self.play_next(
                                                                          data)))
            except DownloadError as e:
                self.parent.logger.info(f"Error loading songs. {e}")
                return False
            for t_player in t_players:
                self.parent.logger.info(f"Adding {t_player.title} to music queue.")
                self.queue.append(t_player)
                return True

        async def skip_song(self, data):
            if (self.player and self.player.is_done() or not self.player) and self.queue:
                await self.play_next(data)
                await respond(self.parent.client, data, "**AFFIRMATIVE. Forcing next song in queue.**")
                return
            self.vote_set.add(data.author.id)
            override = data.author.permissions_in(self.vc.channel).mute_members
            votes = len(self.vote_set)
            m_votes = (len(self.vc.channel.voice_members) - 1) / 2
            if votes >= m_votes or override:
                await self.play_next(self)
                await respond(self.parent.client, data, "**AFFIRMATIVE. Skipping current song.**"
                              if not override else "**AFFIRMATIVE. Override accepted. Skipping current song.**")
            else:
                await respond(self.parent.client, data, f"**Skip vote: ACCEPTED. {votes} "
                                                        f"out of required {ceil(m_votes)}**")

        def set_volume(self, volume):
            self.volume = volume
            if self.player:
                self.player.volume = volume / 100

        def stop_song(self):
            if self.queue:
                self.queue = []
            if self.player and not self.player.is_done():
                self.player.stop()

        def pause_song(self):
            if not self.config["allow_pause"]:
                raise PermissionError("Pause not allowed")
            if self.player and self.player.is_playing:
                self.player.pause()
                self.time_pause = time.time()
                return True
            else:
                return False

        def resume_song(self):
            if not self.config["allow_pause"]:
                raise PermissionError("Pause not allowed")
            if self.player and not self.player.is_playing() and not self.player.is_done():
                self.player.resume()
                self.time_skip += time.time() - self.time_pause
                self.time_pause = 0
                return True
            else:
                return False

        def pop_song(self, number):
            if number < 1 or number > len(self.queue):
                raise SyntaxError("Index out of list.")
            return self.queue.pop(number - 1)

        # Utility functions

        def check_in(self, data):
            return self.vc and self.vc.is_connected() and data.author in self.vc.channel.voice_members

        def check_perm(self, data):
            return self.check_in(data) and data.author.permissions_in(self.vc.channel).mute_members

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
                        self.player.duration else self.config["max_video_length"])
            return t

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

    async def activate(self):
        c = self.plugin_config
        """
        Dynamic storage.
        vc - instance of voicechat, for control purposes.
        player - instance of currently active player. DO NOT NULL, it will keep playing anyway.
        queue - queue of player objects
        vote_set - set of member ids for skip voting purposes, is emptied for every song
        time_started - time of song load, for displaying duration
        time_pause - time of pause start, for displaying duration properly with pausing
        time_skip - total time paused, for displaying duration properly with pausing
        run_timer - keep running the timer coroutine
        """
        self.run_timer = True
        self.stream = c.twitch_stream
        self.players = {}

        loop = asyncio.new_event_loop()
        t_loop = asyncio.get_event_loop()
        self.timer = threading.Thread(target=self.start_timer, args=[loop, t_loop])
        self.timer.setDaemon(True)
        self.timer.start()

        if "banned_members" not in self.storage:
            self.storage["banned_members"] = {}
        for server in self.client.servers:
            if server.id not in self.plugin_config:
                self.plugin_config[server.id] = self.plugin_config["default"]
            if server.id not in self.storage["banned_members"]:
                self.storage["banned_members"][server.id] = set()
            self.players[server.id] = self.ServerStorage(self, server, self.plugin_config[server.id])

        if "stored_songs" not in self.storage:
            self.storage["stored_songs"] = {}

    async def deactivate(self):
        # stop the damn timer
        self.run_timer = False
        for k, player in self.players.items():
            await player.disconnect()

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
        if self.check_ban(data):
            raise PermissionError("You are banned from using the music module.")
        a_voice = await self.players[data.server.id].connect(data)
        if a_voice:
            await respond(self.client, data, f"**AFFIRMATIVE. Connected to: {a_voice}.**")
        else:
            await respond(self.client, data, choice(self.plugin_config["no_permission_lines"]).format(
                    data.channel.name))

    @Command("play",
             category="music",
             syntax="(URL or search query)",
             doc="Plays presented youtube video or searches for one.\nNO PLAYLISTS ALLOWED.")
    async def _playvc(self, data):
        """
        Decorates the input to make sure ytdl can eat it and filters out playlists before pushing the video in the
        queue.
        """
        if self.check_ban(data):
            raise PermissionError("You are banned from using the music module.")
        t_play = self.players[data.server.id]
        await t_play.connected(data)
        if not t_play.check_in(data):
            raise PermissionError("Must be in voicechat.")
        args = data.content.split(' ', 1)
        if len(args) > 1:
            if not (args[1].startswith("http://") or args[1].startswith("https://")):
                args[1] = "ytsearch:" + args[1]
            if not self.plugin_config[data.server.id]["allow_playlists"]:
                if args[1].find("list=") > -1:
                    raise SyntaxWarning("No playlists allowed!")
            await t_play.play_song(args[1], data)
        else:
            raise SyntaxError("Expected URL or search query.")

    @Command("skipsong",
             category="music",
             doc="Votes to skip the current song.\n Forces skip if the current song is stuck.")
    async def _skipvc(self, data):
        """
        Collects votes for skipping current song or skips if you got mute_members permission
        """
        if self.check_ban(data):
            raise PermissionError("You are banned from using the music module.")
        t_play = self.players[data.server.id]
        if not t_play.check_in(data):
            raise PermissionError("Must be in voicechat.")
        await t_play.skip_song(data)

    @Command("volume",
             category="music",
             syntax="[volume from 0 to 200]",
             doc="Adjusts volume, from 0 to 200%.")
    async def _volvc(self, data):
        """
        Checks that the user didn't put in something stupid and adjusts volume.
        """
        if self.check_ban(data):
            raise PermissionError("You are banned from using the music module.")
        t_play = self.players[data.server.id]
        if not t_play.check_in(data):
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
            if vol != t_play.volume:
                await respond(self.client, data, f"**AFFIRMATIVE. Adjusting volume: {t_play.volume}% to {vol}%.**")
                t_play.set_volume(vol)
            else:
                await respond(self.client, data, f"**NEGATIVE. Current volume: {t_play.volume}%.**")
        else:
            await respond(self.client, data, f"**ANALYSIS: Current volume: {t_play.volume}%.**")

    @Command("stopsong",
             category="music",
             doc="Stops the music and empties the queue."
                 "\nRequires mute_members permission in the voice channel.",
             syntax="(HARD) to erase the downloaded files.")
    async def _stopvc(self, data):
        if self.check_ban(data):
            raise PermissionError("You are banned from using the music module.")
        t_play = self.players[data.server.id]
        if not t_play.check_perm(data):
            raise PermissionError("You lack the required permissions.")
        t_play.stop_song()
        if self.plugin_config["download_songs"]:
            args = data.content.split()
            if len(args) > 1 and args[1] == 'HARD':
                for song, _ in self.storage["stored_songs"].items():
                    try:
                        os.remove(song)
                    except Exception:
                        self.logger.exception("Error pruning song cache. ", exc_info=True)
        await respond(self.client, data, "**AFFIRMATIVE. Ceasing the rhythmical noise.**")

    @Command("queue",
             category="music",
             doc="Writes out the current queue.")
    async def _queuevc(self, data):
        if self.check_ban(data):
            raise PermissionError("You are banned from using the music module.")
        t_play = self.players[data.server.id]
        t_string = "**ANALYSIS: Currently playing:**\n"
        if t_play.player and not t_play.player.is_done():
            if t_play.player.duration:
                t_bar = ceil((t_play.play_length() / t_play.player.duration) * 58)
                duration = f"{t_play.player.duration//60:02d}:{t_play.player.duration%60:02d}"
            else:
                t_bar = 58
                duration = " N/A "
            progress = t_play.play_length()
            progress = f"{progress//60:02d}:{progress%60:02d}"
            t_name = t_play.player.title[:37]
            if len(t_name) == 37:
                t_name += "..."
            else:
                t_name = t_name.ljust(40)
            t_string = f"{t_string}```[{t_name}]     [{progress}/{duration}]\n" \
                       f"[{'█' * int(t_bar)}{'-' * int(58 - t_bar)}]```"
        else:
            t_string = f"{t_string}```NOTHING PLAYING```"
        await respond(self.client, data, t_string)
        if len(t_play.queue) > 0:
            t_string = f"{t_play.build_queue()}"
        else:
            t_string = f"QUEUE EMPTY"
        for s in split_message(t_string, "\n"):
            await respond(self.client, data, "```" + s + "```")
        t_m, t_s = divmod(ceil(t_play.queue_length(t_play.queue)), 60)
        await respond(self.client, data, f"**ANALYSIS: Current duration: {t_m}:{t_s:02d}**")

    @Command("nowplaying",
             category="music",
             doc="Writes out the current song information.")
    async def _nowvc(self, data):
        if self.check_ban(data):
            raise PermissionError("You are banned from using the music module.")
        t_play = self.players[data.server.id]
        if t_play.player and not t_play.player.is_done():
            progress = t_play.play_length()
            progress = f"{progress//60}:{progress%60:02d} /"
            if t_play.player.duration:
                duration = f"{t_play.player.duration//60}:{t_play.player.duration%60:02d}"
            else:
                duration = " N/A "
            if t_play.player.description:
                desc = t_play.player.description.replace('https://', '').replace('http://', '')[0:1000]
            else:
                desc = "No description."
            t_string = f"**CURRENTLY PLAYING:**\n```" \
                       f"TITLE: {t_play.player.title}\n{'='*60}\n" \
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
        if self.check_ban(data):
            raise PermissionError("You are banned from using the music module.")
        t_play = self.players[data.server.id]
        if not t_play.check_in(data):
            raise PermissionError("Must be in voicechat.")
        if t_play.pause_song():
            progress = t_play.play_length()
            progress = f"{progress//60}:{progress%60:02d}"
            if t_play.player.duration:
                duration = f"{t_play.player.duration//60}:{t_play.player.duration%60:02d}"
            else:
                duration = " N/A "
            await respond(self.client, data, f"**AFFIRMATIVE. Song paused at {progress} / {duration}**")
        else:
            await respond(self.client, data, f"**NEGATIVE. Invalid pause request.**")

    @Command("resumesong",
             category="music",
             doc="Resumes currently paused music stream.")
    async def _resumevc(self, data):
        if self.check_ban(data):
            raise PermissionError("You are banned from using the music module.")
        t_play = self.players[data.server.id]
        if not t_play.check_in(data):
            raise PermissionError("Must be in voicechat.")
        if t_play.resume_song():
            await respond(self.client, data, "**AFFIRMATIVE. Resuming song.**")
        else:
            await respond(self.client, data, "**NEGATIVE. No song to resume.**")

    @Command("delsong",
             category="music",
             syntax="[queue index]",
             doc="Deletes a song from the queue by it's position number, starting from 1."
                 "\nRequires mute_members permission in the voice channel.")
    async def _delvc(self, data):
        if self.check_ban(data):
            raise PermissionError("You are banned from using the music module.")
        t_play = self.players[data.server.id]
        if not t_play.check_perm(data):
            raise PermissionError("You lack the required permissions.")
        args = data.content.split(" ", 1)
        try:
            pos = int(args[1])
        except ValueError:
            raise SyntaxError("Expected an integer value!")
        t_p = t_play.pop_song(pos)
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
                self.storage["banned_members"][data.server.id].add(t_member.id)
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
                self.storage["banned_members"][data.server.id].remove(t_member.id)
                t_string = f"{t_string} <@{t_member.id}>\n"
        await respond(self.client, data, f"**AFFIRMATIVE. Users unbanned from using music module:**\n"
                                         f"{t_string}")

    @Command("dumpqueue",
             category="music",
             doc="Serializes and dumps the currently playing queue.\nRequires mute_members permission in the "
                 "voice channel")
    async def _dumpvc(self, data):
        if self.check_ban(data):
            raise PermissionError("You are banned from using the music module.")
        t_play = self.players[data.server.id]
        if not t_play.check_perm(data):
            raise PermissionError("You lack the required permissions.")
        t_string = ""
        if t_play.player:
            t_string = f"!\"{t_play.player.url}\" "
        for player in t_play.queue:
            t_string = f"{t_string}!\"{player.url}\" "
        if t_string != "":
            await respond(self.client, data, f"**AFFIRMATIVE. Current queue:**\n")
            for s in split_message(t_string, splitter="\n"):
                await respond(self.client, data, f"```{s}```")

    @Command("appendqueue",
             category="music",
             doc="Appends a number of songs to the queue, takes output from dumpqueue."
                 "\nRequires mute_members permission in the voice channel.",
             syntax="[song] or [!\"ytsearch:song with spaces\"], accepts multiple.")
    async def _appendvc(self, data):
        if self.check_ban(data):
            raise PermissionError("You are banned from using the music module.")
        t_play = self.players[data.server.id]
        await t_play.connected(data)
        if not t_play.check_perm(data):
            raise PermissionError("You lack the required permissions.")
        args = process_args(data.content.split())
        if len(args) > 1:
            await respond(self.client, data, "**AFFIRMATIVE. Extending queue.**")
            for arg in args[1:]:
                await t_play.add_song(arg, data)
            await respond(self.client, data, f"**ANALYSIS: Current queue:**")
            for s in split_message(t_play.build_queue(), "\n"):
                await respond(self.client, data, f"```{s}```")
            if not t_play.player or t_play.player and t_play.player.is_done():
                await t_play.play_next(data)
        else:
            raise SyntaxError("Expected arguments!")

    @Command("leavevc", "leavevoice",
             category="music",
             doc="Leaves voicechat.\nRequires mute_members permission in the voice channel to exit while playing.")
    async def _leavevc(self, data):
        if self.check_ban(data):
            raise PermissionError("You are banned from using the music module.")
        t_play = self.players[data.server.id]
        if not t_play.player or t_play.player.is_done():
            await t_play.disconnect()
            await respond(self.client, data, "**AFFIRMATIVE. Leaving voice chat.**")
        elif t_play.check_perm(data):
            t_play.pause_song()
            await t_play.disconnect()
            await respond(self.client, data, "**AFFIRMATIVE. Override accepted. Leaving voice chat.**")
        else:
            await respond(self.client, data, "**NEGATIVE.**")

    # Music playing

    async def create_player(self, url, vc, *, ytdl_options=None, **kwargs):
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
        vc : VoiceClient
            Voice client instance to create the ffmpeg player off of
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
                    t_player = vc.create_ffmpeg_player(filename, **kwargs)
                    t_player.download_url = filename
                    t_player.url = info.get('webpage_url')
                    t_player.yt = ydl
                    t_player.views = info.get('view_count')
                    t_player.is_live = bool(info.get('is_live'))
                    t_player.likes = info.get('like_count')
                    t_player.dislikes = info.get('dislike_count')
                    t_player.duration = ceil(info.get('duration', 0))
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
            player = vc.create_ffmpeg_player(filename, **kwargs)

            # set the dynamic attributes from the info extraction
            player.download_url = filename
            player.url = info.get('webpage_url')
            player.yt = ydl
            player.views = info.get('view_count')
            player.is_live = bool(info.get('is_live'))
            player.likes = info.get('like_count')
            player.dislikes = info.get('dislike_count')
            player.duration = ceil(info.get('duration', 0))
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

    # Utility functions

    def start_timer(self, loop, t_loop):
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.display_time(t_loop))
        except Exception:
            self.logger.exception("Error starting timer. ", exc_info=True)

    async def display_time(self, t_loop):
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

            # check that people are still listening
            for _, t_player in self.players.items():
                asyncio.ensure_future(t_player.check_connection(), loop=t_loop)

            # time display (only if playing on *one* server, since status is cross-server
            if len(self.client.servers) == 1:
                t_player = self.players[next(iter(self.client.servers)).id]
                game = None
                if t_player.player and isinstance(t_player.player, discord.voice_client.ProcessPlayer) \
                        and not t_player.player.is_done():
                    if t_player.player.is_playing():
                        progress = t_player.play_length()
                        progress = f"{progress//60}:{progress%60:02d}"
                        if t_player.player.duration:
                            duration = t_player.player.duration
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

    def check_ban(self, data):
        if "banned_members" in self.storage and data.server.id in self.storage["banned_members"]:
            return data.author.id in self.storage["banned_members"][data.server.id]
        else:
            return False
