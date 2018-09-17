import discord.opus
import logging
from asyncio import get_event_loop
from collections import deque
from discord import FFmpegPCMAudio, PCMVolumeTransformer
from math import floor
from functools import partial
from time import monotonic as time
from youtube_dl import YoutubeDL
from red_star.command_dispatcher import Command
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import UserPermissionError, CommandSyntaxError
from red_star.rs_utils import respond

class MusicPlayer(BasePlugin):
    name = "music_player"
    version = "2.0"

    async def activate(self):
        self.storage = self.config_manager.get_plugin_config_file("music_player.json")
        self.config = self.storage["config"]

        if not discord.opus.is_loaded():
            try:
                discord.opus.load_opus(self.config["opus_path"])
            except (OSError, TypeError):
                raise RuntimeError("Error occurred while loading libopus! Ensure that the path is correct.")

        self.players = {}

        self.ydl_options = self.config["youtube_dl_config"].copy()
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
        final = ""
        if player.current_song:
            now_playing = self.now_playing(player)
            final += f"**ANALYSIS: Now playing:**\n```{now_playing}```"
        if player.queue:
            queue_list = self.print_queue(player)
            final += f"**ANALYSIS: Current queue:**\n```{queue_list}```"
        await respond(msg, final)

    @Command("SongVolume", "Volume",
             doc="Sets the volume at which the player plays music, between 0 and 100.",
             category="music_player")
    async def _set_volume(self, msg):
        player = self.get_guild_player(msg)
        self.check_user_permission(msg.author, player)
        try:
            new_volume = msg.clean_content(None, 1)[1]
            new_volume = int(new_volume)
            if new_volume == 0:
                raise CommandSyntaxError("Please use PauseSong to mute the bot.")
            elif 0 < new_volume <= 100:
                raise CommandSyntaxError("Expected value between 0 and 100.")
        except ValueError:
            raise CommandSyntaxError(f"Value {new_volume} is not a valid integer.")
        player.volume = new_volume / 100
        await respond(msg, f"**AFFIRMATIVE. Set volume to {new_volume}%.**")

    @Command("SkipSong", "Skip",
             doc="Tells the bot to skip the currently playing song.",
             perms="mute_members",
             category="music_player")
    async def _skip_song(self, msg):
        player = self.get_guild_player(msg)
        if not player or not player.is_playing:
            await respond(msg, "**ANALYSIS: No music currently playing.**")
            return
        await respond(msg, "**ANALYSIS: Skipping to next song in queue...**")
        player.stop()

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
        if not user in player.voice_client.channel.members:
            raise UserPermissionError("You are not in the voice channel.")
        return True

    def get_guild_player(self, msg):
        return self.players.get(msg.guild.id, None)

    def get_guild_config(self, guild, key):
        gid = str(guild.id)
        try:
            return self.config["per_server_configs"][gid][key]
        except KeyError:
            self.config["per_server_configs"][gid] = self.config["per_server_configs"]["default"].copy()

    @staticmethod
    def print_queue(player):
        str_list = []
        for i, vid in enumerate(player.queue):
            # Duration formatting
            duration = vid.get("duration", 0)
            if duration <= 0:
                duration = "--:--"
            else:
                mn, sec = divmod(duration, 60)
                sec = floor(sec)
                if mn > 99:
                    hr, mn = divmod(mn, 60)
                    duration = f"{hr:02d}:{mn:02d}:{sec:02d}"
                else:
                    duration = f"{mn:02d}:{sec:02d}"
            # Title truncating and padding
            title = vid.get("title", "Unknown")
            if len(title) >= 59:
                title = title[:56] + "..."
            str_list.append(f"[{i+1:02d}][{title:-<59}][{duration}]")
        return "\n".join(str_list)

    @staticmethod
    def now_playing(player):
        play_time = player.play_time()
        play_time_min, play_time_sec = divmod(play_time, 60)
        duration = player.current_song.get("duration", 0)
        dur_str = f"{int(play_time_min):02d}:{floor(play_time_sec):02d}/"
        if duration > 0:
            played = play_time / duration
            duration_min, duration_sec = divmod(duration, 60)
            dur_str += f"{duration_min:02d}:{floor(duration_sec):02d}"
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
        self.queue = deque(maxlen=self.parent.get_guild_config(self.voice_client.guild, "max_queue_length"))
        self.is_playing = False
        self.current_song = {}
        self.volume = self.parent.config["default_volume"] / 100
        self.loop = get_event_loop()
        self.song_start_time = None
        self.song_pause_time = None

    async def enqueue(self, url):
        count = 1
        with self.text_channel.typing():
            with YoutubeDL(self.parent.ydl_options) as ydl:
                vid_info = await self.loop.run_in_executor(None, partial(ydl.extract_info, url, download=False))
            if vid_info.get("_type") == "playlist":
                for inf in vid_info["entries"]:
                    self.queue.append(inf)
                count = len(vid_info["entries"])
            else:
                self.queue.append(vid_info)
        await self.text_channel.send(f"**ANALYSIS: Queued {count} songs for listening.**")
        if not self.is_playing:
            await self.play()

    async def play(self):
        try:
            next_song = self.queue.popleft()
        except IndexError:
            await self.text_channel.send("**ANALYSIS: Queue complete.**")
            self.is_playing = False
            self.current_song = {}
            self.voice_client.stop()
            try:
                self.voice_client.source.cleanup()
            except AttributeError:
                pass
            return
        before_args = ""
        if self.parent.config["save_audio"] and not next_song.get("is_live", False):
            with YoutubeDL(self.parent.ydl_options) as ydl:
                await self.loop.run_in_executor(None, partial(ydl.process_info, next_song))
                file = ydl.prepare_filename(next_song)
        else:
            file = next_song["url"]
            before_args += " -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30"
        source = PCMVolumeTransformer(FFmpegPCMAudio(file, before_options=before_args, options="-vn"),
                                      volume=self.volume)
        self.voice_client.play(source, after=self.after)
        self.is_playing = True
        self.song_start_time = time()
        self.current_song = next_song
        await self.text_channel.send(f"**NOW PLAYING: {next_song.get('title', 'Unkown')}.**")

    def toggle_pause(self):
        if self.voice_client.is_paused():
            self.voice_client.resume()
            self.song_start_time += (time() - self.song_pause_time)
            return False
        else:
            self.voice_client.pause()
            self.song_pause_time = time()
            return True

    def after(self, error):
        if error:
            self.logger.error(error)
        self.loop.create_task(self.play())

    def stop(self):
        self.is_playing = False
        self.current_song = {}
        try:
            self.voice_client.source.cleanup()
        except AttributeError:
            pass
        self.voice_client.stop()

    def play_time(self):
        if self.voice_client.is_paused():
            return self.song_pause_time - self.song_start_time
        else:
            return time() - self.song_start_time