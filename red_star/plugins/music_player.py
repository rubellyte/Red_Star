import discord.opus
import logging
from asyncio import get_event_loop
from collections import deque
from discord import FFmpegPCMAudio, PCMVolumeTransformer
from discord.errors import ClientException
from math import floor, ceil
from functools import partial
from time import monotonic as time
from youtube_dl import YoutubeDL
from red_star.command_dispatcher import Command
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import UserPermissionError, CommandSyntaxError
from red_star.rs_utils import respond, split_output, get_guild_config


class MusicPlayer(BasePlugin):
    name = "music_player"
    version = "2.0"
    default_config = {
        "opus_path": "A valid path to your libopus file. On Linux, this is likely unnecessary.",
        "save_audio": True,
        "default_volume": 15,
        "youtube_dl_config": {
            "quiet": True,
            "restrictfilenames": True,
            "source_address": "0.0.0.0",
            "audioformat": "mp3",
            "default_search": "auto",
            "extractaudio": True,
            "logtostderr": False,
            "nocheckcertificate": True,
            "format": "bestaudio/best"
        },
        "default": {
            "max_queue_length": 30,
            "max_video_length": 1800,
            "vote_skip_threshold": 0.5
        }
    }

    async def activate(self):
        self.storage = self.config_manager.get_plugin_config_file("music_player.json")

        if not discord.opus.is_loaded():
            try:
                discord.opus.load_opus(self.plugin_config["opus_path"])
            except (OSError, TypeError):
                raise RuntimeError("Error occurred while loading libopus! Ensure that the path is correct.")

        self.players = {}

        self.ydl_options = self.plugin_config["youtube_dl_config"].copy()
        self.ydl_options["logger"] = logging.getLogger("red_star.plugin.music_player.youtube-dl")

    async def deactivate(self):
        for player in self.players.values():
            await player.voice_client.disconnect()

    # Command functions

    @Command("JoinVoice", "JoinVC",
             doc="Tells the bot to join the voice channel you're currently in.",
             category="music_player")
    async def _join_voice(self, msg):
        try:
            voice_channel = msg.author.voice.channel
        except AttributeError:
            await respond(msg, "**ANALYSIS: User is not connected to voice channel.**")
            return
        if msg.guild.id in self.players:
            player = self.players[msg.guild.id]
            await player.voice_client.move_to(voice_channel)
        else:
            player = await self.create_player(voice_channel, msg.channel)
        await respond(msg, f"**AFFIRMATIVE. Connected to channel {voice_channel.name}.**")
        return player

    @Command("LeaveVoice", "LeaveVC",
             doc="Tells the bot to leave the voice channel it's currently in.",
             category="music_player")
    async def _leave_voice(self, msg):
        player = self.get_guild_player(msg)
        if not player:
            try:
                msg.guild.voice_client.stop()
                await msg.guild.voice_client.disconnect(force=True)
                await respond(msg, "**ANALYSIS: Disconnected from voice channel.**")
                return
            except AttributeError:
                await respond(msg, "**ANALYSIS: Bot is not currently in voice channel.**")
                return
        if player.is_playing and not player.voice_client.channel.permissions_for(msg.author).mute_members:
            raise PermissionError
        player.queue.clear()
        player.stop()
        await player.voice_client.disconnect()
        del self.players[msg.guild.id]
        await respond(msg, "**ANALYSIS: Disconnected from voice channel.**")

    @Command("PlaySong", "Play",
             doc="Tells the bot to queue a song for playing. User must be in the same channel as the bot.",
             syntax="(url)",
             category="music_player")
    async def _play_song(self, msg):
        player = self.get_guild_player(msg)
        if not player:
            player = await self._join_voice(msg)
        self.check_user_permission(msg.author, player)
        url = msg.clean_content.split(None, 1)[1]
        await player.enqueue(url)

    @Command("SongQueue", "Queue",
             doc="Tells the bot to list the current song queue.",
             category="music_player")
    async def _list_queue(self, msg):
        player = self.get_guild_player(msg)
        if not player:
            await respond(msg, "**ANALYSIS: Bot is not in a voice channel.**")
            return
        elif len(player.queue) < 1 and not player.current_song:
            await respond(msg, "**ANALYSIS: The queue is empty.**")
            return
        if player.current_song:
            now_playing = self.now_playing(player)
            await respond(msg, f"**ANALYSIS: Now playing:**\n```{now_playing}```")
        if player.queue:
            await split_output(msg, "**ANALYSIS: Current queue:**\n", self.print_queue(player))

    @Command("SongVolume", "Volume",
             doc="Sets the volume at which the player plays music, between 0 and 100.",
             category="music_player")
    async def _set_volume(self, msg):
        player = self.get_guild_player(msg)
        self.check_user_permission(msg.author, player)
        try:
            new_volume = msg.clean_content.split(None, 1)[1]
            new_volume = int(new_volume)
            if new_volume == 0:
                raise CommandSyntaxError("Please use PauseSong to mute the bot")
            elif not 0 < new_volume <= 100:
                raise CommandSyntaxError("Expected value between 0 and 100")
        except ValueError:
            raise CommandSyntaxError(f"Value {new_volume} is not a valid integer")
        except IndexError:
            await respond(msg, f"**ANALYSIS: Current volume is {int(player.volume * 100)}%.**")
            return
        player.volume = new_volume / 100
        await respond(msg, f"**AFFIRMATIVE. Set volume to {new_volume}%.**")

    @Command("SkipSong", "Skip",
             doc="Tells the bot to skip the currently playing song.",
             category="music_player")
    async def _skip_song(self, msg):
        player = self.get_guild_player(msg)
        self.check_user_permission(msg.author, player)
        if not player or not player.is_playing:
            await respond(msg, "**ANALYSIS: No music currently playing.**")
            return
        elif player.voice_client.channel.permissions_for(msg.author).mute_members:
            await respond(msg, "**ANALYSIS: Skipping to next song in queue...**")
            player.stop()
        else:
            await player.skip_vote()

    @Command("PauseSong", "Pause", "ResumeSong", "Resume",
             doc="Tells the bot to pause or resume the current song.",
             perms="mute_members",
             category="music_player")
    async def _pause_song(self, msg):
        player = self.get_guild_player(msg)
        if not player or player.is_playing is False:
            await respond(msg, "**WARNING: No music currently playing.**")
            return
        if player.toggle_pause():
            await respond(msg, "**ANALYSIS: Song paused.**")
        else:
            await respond(msg, "**ANALYSIS: Song resumed.**")

    @Command("StopMusic", "StopSong", "Stop",
             doc="Tells the bot to stop playing songs and empty the queue.",
             perms="mute_members",
             category="music_player")
    async def _stop_music(self, msg):
        player = self.get_guild_player(msg)
        if not player or not player.is_playing:
            await respond(msg, "**ANALYSIS: No music currently playing.")
            return
        player.queue.clear()
        player.stop()
        await respond(msg, "**ANALYSIS: The music has been stopped and the queue has been cleared.**")

    # Utility functions

    async def create_player(self, voice_channel, text_channel):
        voice_client = await voice_channel.connect()
        player = GuildPlayer(self, voice_client, text_channel)
        self.players[voice_channel.guild.id] = player
        return player

    def check_user_permission(self, user, player):
        if user.id in self.storage["banned_users"].get(str(player.voice_client.guild.id), []):
            raise UserPermissionError("You are banned from using the music player.")
        if user not in player.voice_client.channel.members:
            raise UserPermissionError("You are not in the voice channel.")
        return True

    def get_guild_player(self, msg):
        return self.players.get(msg.guild.id, None)

    @staticmethod
    def print_queue(player):
        str_list = []
        for i, vid in enumerate(player.queue):
            # Duration formatting
            duration = vid.get("duration", 0)
            if duration <= 0:
                duration = "--:--"
            else:
                duration = seconds_to_minutes(duration)
                duration = f"{duration[0]:02d}:{duration[1]:02d}"
            # Title truncating and padding
            title = vid.get("title", "Unknown")
            if len(title) >= 59:
                title = title[:56] + "..."
            str_list.append(f"[{i+1:02d}][{title:-<59}][{duration}]")
        return str_list

    @staticmethod
    def now_playing(player):
        play_time = player.play_time()
        play_time_tup = seconds_to_minutes(play_time)
        duration = player.current_song.get("duration", 0)
        dur_str = f"{play_time[0]:02d}:{play_time[1]:02d}/"
        if duration > 0:
            played = play_time / duration
            duration= seconds_to_minutes(duration)
            dur_str += f"{duration[0]:02d}:{floor(duration[1]):02d}"
        else:
            played = 0
            dur_str += "--:--"
        bars = floor(70 * played)
        progress_bar = f"{'█'*bars}{'-'*(70-bars)}"
        title = player.current_song.get("title", "Unknown")
        if len(title) > 57:
            title = title[:54] + "..."
        return f"[{title:-<57}][{dur_str}]\n[{progress_bar}]"


class GuildPlayer:
    def __init__(self, parent, voice_client, channel):
        self.parent = parent
        self.text_channel = channel
        self.voice_client = voice_client
        self.logger = logging.getLogger(f"red_star.plugin.music_player.player_{self.voice_client.guild.id}")
        self.queue = deque()
        self.is_playing = False
        self.current_song = {}
        self._volume = self.parent.plugin_config["default_volume"] / 100
        self._loop = get_event_loop()
        self._song_start_time = None
        self._song_pause_time = None
        self._skip_votes = 0
        self.gid = str(voice_client.guild.id)

    async def enqueue(self, url):
        with self.text_channel.typing():
            with YoutubeDL(self.parent.ydl_options) as ydl:
                vid_info = await self._loop.run_in_executor(None, partial(ydl.extract_info, url, download=False))
            if vid_info.get("_type") == "playlist":
                self._loop.create_task(self._enqueue_playlist(vid_info["entries"]))
                return
            else:
                if len(self.queue) >= get_guild_config(self.parent, self.gid, "max_queue_length"):
                    await self.text_channel.send(f"**WARNING: The queue is full. {vid_info['title']} "
                                                 f"will not be added.")
                    return
                elif vid_info["duration"] > get_guild_config(self.parent, self.gid, "max_video_length"):
                    max_len = seconds_to_minutes(get_guild_config(self.parent, self.gid, "max_video_length"))
                    max_len_str = f"{max_len[0]:02d}:{max_len[1]:02d}"
                    await self.text_channel.send(f"**WARNING: Your video exceeds the maximum video length "
                                                 f"({max_len_str}). It will not be added.**")
                    return
                else:
                    await self._process_video(vid_info)
        await self.text_channel.send(f"**ANALYSIS: Queued `{vid_info['title']}`.**")
        if not self.is_playing:
            await self._play()

    async def _enqueue_playlist(self, entries):
        await self.text_channel.send(f"**ANALYSIS: Attempting to queue {len(entries)} videos. Your playback will "
                                     f"begin shortly.")
        orig_len = len(self.queue)
        with self.text_channel.typing():
            for vid in entries:
                if len(self.queue) >= get_guild_config(self.parent, self.gid, "max_queue_length"):
                    await self.text_channel.send(f"**WARNING: The queue is full. No more videos will be added.**")
                    break
                elif vid["duration"] > get_guild_config(self.parent, self.gid, "max_video_length"):
                    max_len = seconds_to_minutes(get_guild_config(self.parent, self.gid, "max_video_length"))
                    max_len_str = f"{max_len[0]:02d}:{max_len[1]:02d}"
                    await self.text_channel.send(f"**WARNING: Video {vid['title']} exceeds the maximum video length"
                                                 f"({max_len_str}). It will not be added.**")
                    continue
                try:
                    await self._process_video(vid)
                except TypeError:
                    continue
                if not self.is_playing:
                    try:
                        self._loop.create_task(self._play())
                    except ClientException:
                        pass
        await self.text_channel.send(f"**ANALYSIS: Queued {len(self.queue) - orig_len} videos.**")

    async def _process_video(self, vid):
        if not vid:
            raise TypeError
        if self.parent.plugin_config["save_audio"] and not vid.get("is_live", False):
            with YoutubeDL(self.parent.ydl_options) as ydl:
                await self._loop.run_in_executor(None, partial(ydl.process_info, vid))
                vid["filename"] = ydl.prepare_filename(vid)
        vid.setdefault("title", "Unknown")
        vid.setdefault("is_live", False)
        vid.setdefault("duration", 0)
        if vid["duration"] < 0:
            vid["duration"] = 0
        self.queue.append(vid)

    async def _play(self):
        try:
            next_song = self.queue.popleft()
        except IndexError:
            await self.text_channel.send("**ANALYSIS: Queue complete.**")
            self.is_playing = False
            self.current_song = {}
            self._skip_votes = 0
            self.voice_client.stop()
            try:
                self.voice_client.source.cleanup()
            except AttributeError:
                pass
            return
        before_args = ""
        if self.parent.plugin_config["save_audio"] and not next_song["is_live"]:
            file = next_song["filename"]
        else:
            file = next_song["url"]
            before_args += " -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30"
        self.is_playing = True
        source = PCMVolumeTransformer(FFmpegPCMAudio(file, before_options=before_args, options="-vn"),
                                      volume=self._volume)
        self.voice_client.play(source, after=self._after)
        self._song_start_time = time()
        self.current_song = next_song
        self._skip_votes = 0
        await self.text_channel.send(f"**NOW PLAYING: {next_song['title']}.**")

    def toggle_pause(self):
        if self.voice_client.is_paused():
            self.voice_client.resume()
            self._song_start_time += (time() - self._song_pause_time)
            return False
        else:
            self.voice_client.pause()
            self._song_pause_time = time()
            return True

    def _after(self, error):
        if error:
            self.logger.error(error)
        self._loop.create_task(self._play())

    def stop(self):
        self.is_playing = False
        self.current_song = {}
        self._skip_votes = 0
        try:
            self.voice_client.source.cleanup()
        except AttributeError:
            pass
        self.voice_client.stop()

    def play_time(self):
        if self.voice_client.is_paused():
            return self._song_pause_time - self._song_start_time
        else:
            return time() - self._song_start_time

    async def skip_vote(self):
        self._skip_votes += 1
        total_users = len(self.voice_client.channel.members) - 1  # Don't want to count the bot itself
        threshold = get_guild_config(self.parent, self.gid, "vote_skip_threshold")
        if self._skip_votes / total_users >= threshold:
            await self.text_channel.send("**AFFIRMATIVE. Skipping current song.**")
            self.stop()
        else:
            votes_needed = ceil(total_users * threshold) - self._skip_votes
            await self.text_channel.send(f"**AFFIRMATIVE. Skip vote recorded. {votes_needed} votes needed to skip.")

    @property
    def volume(self):
        return self.volume

    @volume.setter
    def volume(self, val):
        self._volume = val
        self.voice_client.source.volume = val


def seconds_to_minutes(secs, hours=False):
    mn, sec = divmod(secs, 60)
    if hours:
        hr, mn = divmod(mn, 60)
        return int(hr), int(mn), floor(sec)
    else:
        return int(mn), int(floor(sec))
