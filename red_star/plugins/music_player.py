import enum
import discord.opus
import logging
from asyncio import get_event_loop
from discord import FFmpegPCMAudio, PCMVolumeTransformer
from discord.errors import ClientException
from math import floor, ceil
from functools import partial
from random import randint
from time import monotonic as time
from youtube_dl import YoutubeDL
from youtube_dl.utils import YoutubeDLError
from red_star.command_dispatcher import Command
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import UserPermissionError, CommandSyntaxError
from red_star.rs_utils import respond, split_output, get_guild_config, split_message, find_user


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
            "vote_skip_threshold": 0.5,
            "print_queue_on_edit": True
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
        elif player.queue and not player.current_song:
            await respond(msg, "**ANALYSIS: The queue is empty.**")
            return
        if player.current_song:
            await respond(msg, f"**ANALYSIS: Now playing:**\n```{player.now_playing()}```")
        if player.queue:
            await split_output(msg, "**ANALYSIS: Current queue:**\n", player.print_queue())

    @Command("DeleteSong", "DelSong", "RMSong",
             doc="Removes a song from the bot's queue.",
             syntax="(index)",
             perms="mute_members",
             category="music_player")
    async def _delete_song(self, msg):
        player = self.get_guild_player(msg)
        if not player:
            await respond(msg, "**ANALYSIS: Bot is not in a voice channel.**")
            return
        elif not player.queue:
            await respond(msg, "**ANALYSIS: The queue is empty.**")
            return
        try:
            index = int(msg.clean_content.split(None, 1)[1])
        except IndexError:
            raise CommandSyntaxError("No arguments provided")
        except ValueError:
            raise CommandSyntaxError(f"{msg.clean_content.split(None, 1)[1]} is not a valid integer.")
        if index == 0:
            raise CommandSyntaxError("Use Skip to skip the currently playing song")
        elif index < 0:
            raise CommandSyntaxError("Provided integer must be positive")
        index -= 1
        try:
            del_song = player.queue.pop(index)
        except IndexError:
            raise CommandSyntaxError("Integer provided is not a valid index")
        await respond(msg, f"**AFFIRMATIVE. Deleted song at position {index + 1} ({del_song['title']}).**")
        if get_guild_config(self, str(msg.guild.id), "print_queue_on_edit"):
            await split_output(msg, "**ANALYSIS: Current queue:**\n", player.print_queue())

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

    @Command("SongMode", "Shuffle", "Repeat",
             doc="Tells the bot in what order the bot should play its queue, or prints the current mode if no mode "
                 "is specified.",
             syntax="[n/normal|rs/repeat_song|rq/repeat_queue|s/shuffle|sr/shuffle_repeat]",
             category="music_player")
    async def _song_mode(self, msg):
        player = self.get_guild_player(msg)
        self.check_user_permission(msg.author, player)
        try:
            arg = msg.clean_content.split(None, 1)[1].lower()
        except IndexError:
            await respond(msg, f"**ANALYSIS: Current song mode is {player.song_mode}.**")
            return
        if arg in ("n", "normal", "reset"):
            player.song_mode = SongMode.NORMAL
        elif arg in ("rs", "repeat_song", "loop"):
            player.song_mode = SongMode.REPEAT_SONG
        elif arg in ("rq", "repeat", "repeat_queue", "cycle"):
            player.song_mode = SongMode.REPEAT_QUEUE
        elif arg in ("s", "shuffle", "random"):
            player.song_mode = SongMode.SHUFFLE
        elif arg in ("sr", "shuffle_repeat", "random_repeat"):
            player.song_mode = SongMode.SHUFFLE_REPEAT
        else:
            raise CommandSyntaxError(f"Argument {arg} is not a valid mode")
        await respond(msg, f"**AFFIRMATIVE. Song mode changed to {player.song_mode}.**")

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

    @Command("MusicBan",
             doc="Bans or unbans a user from using music bot commands, or lists bans if no user specified..",
             syntax="(user)",
             perms="mute_memebers",
             category="music_player")
    async def _music_ban(self, msg):
        try:
            ban_store = self.storage["banned_users"][str(msg.guild.id)]
        except KeyError:
            ban_store = self.storage["banned_users"][str(msg.guild.id)] = []
        try:
            user = find_user(msg.guild, msg.content.split(None, 1)[1])
        except IndexError:
            user_li = [find_user(msg.guild, x) for x in ban_store]
            banned_list = [str(x) if x else "Unknown" for x in user_li]
            if not banned_list:
                banned_list = ["None."]
            await split_output(msg, "**ANALYSIS: Banned users:**\n", banned_list)
            return
        if user:
            if user.id in ban_store:
                ban_store.remove(user.id)
                await respond(msg, f"**AFFIRMATIVE. User {user} has been unbanned from using the music module.**")
                return
            else:
                ban_store.append(user.id)
            await respond(msg, f"**AFFIRMATIVE. User {user} has been banned from using the music module.**")
        else:
            raise CommandSyntaxError(f"No such user {msg.clean_content.split(None, 1)[1]}")


    # Utility functions

    async def create_player(self, voice_channel, text_channel):
        voice_client = await voice_channel.connect()
        player = GuildPlayer(self, voice_client, text_channel)
        self.players[voice_channel.guild.id] = player
        return player

    def check_user_permission(self, user, player):
        try:
            if user.id in self.storage["banned_users"].get(str(player.voice_client.guild.id), []):
                raise UserPermissionError("You are banned from using the music player.")
            if user not in player.voice_client.channel.members:
                raise UserPermissionError("You are not in the voice channel.")
        except AttributeError:
            raise UserPermissionError("The bot is not currently in a voice channel.")
        return True

    def get_guild_player(self, msg):
        return self.players.get(msg.guild.id, None)


class GuildPlayer:
    def __init__(self, parent, voice_client, channel):
        self.parent = parent
        self.text_channel = channel
        self.voice_client = voice_client
        self.logger = logging.getLogger(f"red_star.plugin.music_player.player_{self.voice_client.guild.id}")
        self.queue = []
        self.is_playing = False
        self.current_song = {}
        self.song_mode = SongMode.NORMAL
        self._volume = self.parent.plugin_config["default_volume"] / 100
        self._loop = get_event_loop()
        self._song_start_time = None
        self._song_pause_time = None
        self._skip_votes = 0
        self.gid = str(voice_client.guild.id)

    async def enqueue(self, url):
        with self.text_channel.typing():
            with YoutubeDL(self.parent.ydl_options) as ydl:
                try:
                    vid_info = await self._loop.run_in_executor(None, partial(ydl.extract_info, url, download=False))
                except YoutubeDLError as e:
                    await self.text_channel.send(f"**WARNING. An error occurred while downloading video <{url}>. "
                                                 f"It will not be queued.\nError details:** `{e}`")
                    return
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
        if get_guild_config(self.parent, self.gid, "print_queue_on_edit"):
            await self.text_channel.send(f"**ANALYSIS: Current queue:**")
            for msg in split_message("\n".join(self.print_queue()), splitter="\n", max_len=1994):
                await self.text_channel.send(f"```{msg}```")
        if not self.is_playing:
            await self._play()

    async def _enqueue_playlist(self, entries):
        await self.text_channel.send(f"**ANALYSIS: Attempting to queue {len(entries)} videos. Your playback will "
                                     f"begin shortly.**")
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
        if get_guild_config(self.parent, self.gid, "print_queue_on_edit"):
            await self.text_channel.send(f"**ANALYSIS: Current queue:**")
            for msg in split_message("\n".join(self.print_queue()), splitter="\n", max_len=1994):
                await self.text_channel.send(f"```{msg}```")

    async def _process_video(self, vid):
        if not vid:
            raise TypeError
        if self.parent.plugin_config["save_audio"] and not vid.get("is_live", False):
            with YoutubeDL(self.parent.ydl_options) as ydl:
                try:
                    await self._loop.run_in_executor(None, partial(ydl.process_info, vid))
                    vid["filename"] = ydl.prepare_filename(vid)
                except YoutubeDLError as e:
                    await self.text_channel.send(f"**WARNING. An error occurred while downloading video"
                                                 f"{vid['title']}. It will not be queued.\nError details:** `{e}`")
                    return
        vid.setdefault("title", "Unknown")
        vid.setdefault("is_live", False)
        vid.setdefault("duration", 0)
        if vid["duration"] < 0:
            vid["duration"] = 0
        self.queue.append(vid)

    async def _play(self):
        try:
            if self.song_mode == SongMode.SHUFFLE_REPEAT:
                next_song = self.queue[randint(0, len(self.queue) - 1)]
            elif self.song_mode == SongMode.SHUFFLE:
                next_song = self.queue.pop(randint(0, len(self.queue) - 1))
            elif self.song_mode == SongMode.REPEAT_QUEUE:
                if self.current_song:
                    self.queue.append(self.current_song)
                next_song = self.queue.pop(0)
            elif self.song_mode == SongMode.REPEAT_SONG:
                if self.current_song:
                    next_song = self.current_song
                else:
                    next_song = self.queue.pop(0)
            else:
                next_song = self.queue.pop(0)
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

    def print_queue(self):
        str_list = []
        for i, vid in enumerate(self.queue):
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

    def now_playing(self):
        play_time = self.play_time()
        play_time_tup = seconds_to_minutes(play_time)
        duration = self.current_song.get("duration", 0)
        dur_str = f"{play_time_tup[0]:02d}:{play_time_tup[1]:02d}/"
        if duration > 0:
            played = play_time / duration
            duration= seconds_to_minutes(duration)
            dur_str += f"{duration[0]:02d}:{floor(duration[1]):02d}"
        else:
            played = 0
            dur_str += "--:--"
        bars = floor(70 * played)
        progress_bar = f"{'█'*bars}{'-'*(70-bars)}"
        title = self.current_song.get("title", "Unknown")
        if len(title) > 57:
            title = title[:54] + "..."
        return f"[{title:-<57}][{dur_str}]\n[{progress_bar}]"


def seconds_to_minutes(secs, hours=False):
    mn, sec = divmod(secs, 60)
    if hours:
        hr, mn = divmod(mn, 60)
        return int(hr), int(mn), floor(sec)
    else:
        return int(mn), int(floor(sec))


class SongMode(enum.Enum):
    NORMAL = "normal"
    REPEAT_SONG = "repeat_song"
    REPEAT_QUEUE = "repeat_queue"
    SHUFFLE = "shuffle"
    SHUFFLE_REPEAT = "shuffle_repeat"

    def __str__(self):
        return self.name
