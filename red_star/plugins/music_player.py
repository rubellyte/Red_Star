import enum
import logging
import re
import shlex
from asyncio import create_task, get_running_loop, run_coroutine_threadsafe, TimeoutError
from discord import FFmpegPCMAudio, PCMVolumeTransformer, Embed, ClientException
from math import floor, ceil
from functools import partial
from os import remove as remove_file
from random import randint
from time import monotonic as time
from yt_dlp import YoutubeDL
from yt_dlp.utils import YoutubeDLError
from red_star.command_dispatcher import Command
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import UserPermissionError, CommandSyntaxError
from red_star.rs_utils import respond, split_message, get_guild_config, find_user, is_positive


class MusicPlayer(BasePlugin):
    name = "music_player"
    version = "2.2"
    author = "medeor413 (original by GTG3000)"
    description = "A plugin for playing audio from videos in a voice channel."
    default_config = {
        "save_audio": True,
        "video_cache_clear_age": 259200,
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
            "format": "bestaudio/best",
            "noplaylist": True,
            "no_color": True
        },
        "default": {
            "max_queue_length": 30,
            "max_video_length": 1800,
            "vote_skip_threshold": 0.5,
            "print_queue_on_edit": True,
            "idle_disconnect_time": 300
        }
    }

    async def activate(self):
        self.storage = self.config_manager.get_plugin_config_file("music_player.json")

        self.players = {}

        self.ydl_options = self.plugin_config["youtube_dl_config"].copy()
        self.ydl_options["logger"] = logging.getLogger("red_star.plugin.music_player.youtube-dl")
        self.ydl_options["extract_flat"] = "in_playlist"
        self.ydl_options["outtmpl"] = str(self.client.storage_dir / "music_cache" /
                                          self.ydl_options.get("outtmpl", "%(id)s-%(extractor)s.%(ext)s"))

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
            raise UserPermissionError("**ANALYSIS: User is not connected to voice channel.**")
        try:
            if msg.guild.id in self.players:
                player = self.players[msg.guild.id]
                await player.voice_client.move_to(voice_channel)
            else:
                player = await self.create_player(voice_channel, msg.channel)
        except TimeoutError:
            raise CommandSyntaxError("Bot failed to join channel. Make sure bot can access the channel.")
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
        if player.is_playing \
                and not player.voice_client.channel.permissions_for(msg.author).mute_members\
                and not self.config_manager.is_maintainer(msg.author):
            raise UserPermissionError
        player.queue.clear()
        player.already_played.clear()
        player.stop()
        await player.voice_client.disconnect()
        del self.players[msg.guild.id]
        await respond(msg, "**ANALYSIS: Disconnected from voice channel.**")

    @Command("PlaySong", "Play",
             doc="Tells the bot to queue video links for playing. User must be in the same channel as the bot. "
                 "Supports an arbitrary number of links in a single command.\n"
                 "Supports playlists. Additionally, subsets of playlists can be played using slice notation.\n"
                 "Subset syntax: http://example.url{1,3-5,-2,6-}. {1} selects the first video, {3-5} selects the "
                 "third through fifth videos, {-2} selects all videos up to the second, {6-} selects the sixth video "
                 "and all after it. Multiple slices can be used on one playlist by separating them with ,.",
             syntax="(url) [url_2] [url_3]...",
             category="music_player")
    async def _play_song(self, msg):
        player = self.get_guild_player(msg)
        if not player:
            player = await self._join_voice(msg)
        self.check_user_permission(msg.author, player)
        try:
            urls = shlex.split(msg.clean_content)[1:]
            print(urls)
            # Is it supposed to be a search query, or a bunch of URLs?
            if len(urls) > 1:
                url_validator = re.compile(r"https?://(www\.)?[-a-zA-Z\d@:%._+~#=]{1,256}\.[a-zA-Z\d()]{1,6}"
                                           r"\b([-a-zA-Z\d()@:%_+.~#?&/=]*)")
                print("validating")
                if any((not url_validator.fullmatch(url) and " " not in url) for url in urls):
                    # If it's just a plain search query (no URLs, no quoted spaces), join it back together for QoL
                    urls = [" ".join(urls)]
        except ValueError as e:
            raise CommandSyntaxError(e)
        print(urls)
        await player.prepare_playlist(urls)

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
            await respond(msg, f"**ANALYSIS: Now playing:**\n```{player.print_now_playing()}```")
        if player.queue:
            queue_duration = pretty_duration(player.queue_duration)
            for split_msg in split_message(f"**ANALYSIS: Current queue: ({queue_duration})**{player.print_queue()}"):
                await respond(msg, split_msg)

    @Command("NowPlaying", "SongInfo",
             doc="Displays detailed information about the currently playing song.",
             category="music_player")
    async def _song_info(self, msg):
        player = self.get_guild_player(msg)
        if not player or not player.current_song:
            await respond(msg, "**ANALYSIS: There is no song currently playing.**")
            return
        vid = player.current_song
        desc = vid.get("description", "*No description.*")
        if len(desc) > 2048:
            desc = desc[:2045] + "..."
        embed = Embed(title=vid.get("title", "Unknown"), description=desc, url=vid["url"])
        if vid.get("thumbnail") is not None:
            embed.set_thumbnail(url=vid["thumbnail"])
        if vid.get("uploader") is not None:
            embed.set_author(name=vid["uploader"])
        if vid.get("tags") is not None:
            embed.set_footer(text=f"Tags: {', '.join(vid['tags'])}")
        play_time, duration, _ = player.progress
        rating_field = f"Views: {vid.get('view_count', 'Unknown'):,}."
        if vid.get("like_count") is not None:
            rating_field += f" {vid['like_count']:,}👍"
        if vid.get("dislike_count") is not None:
            rating_field += f"/{vid['dislike_count']:,}👎"
        if vid.get("average_rating") is not None:
            rating_field += f" (Average rating: {vid['average_rating']:.2f})"
        embed.add_field(name="Ratings", value=rating_field)
        await respond(msg, embed=embed)

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
            if index in player.already_played:
                player.already_played.remove(index)
            new_already_played = set()
            for i in player.already_played:
                if i > index:
                    i -= 1
                new_already_played.add(i)
            player.already_played = new_already_played
        except IndexError:
            raise CommandSyntaxError("Integer provided is not a valid index")
        await respond(msg, f"**AFFIRMATIVE. Deleted song at position {index + 1} ({del_song['title']}).**")
        if get_guild_config(self, str(msg.guild.id), "print_queue_on_edit") and player.queue:
            for split_msg in split_message(f"**ANALYSIS: Current queue:**{player.print_queue()}"):
                await respond(msg, split_msg)

    @Command("SongVolume", "Volume",
             doc="Sets the volume at which the player plays music, between 0 and 100.\nUse --temporary flag to "
                 "automatically reset volume at the end of the current song.",
             syntax="[-t/--temporary] (0-100)",
             category="music_player")
    async def _set_volume(self, msg):
        player = self.get_guild_player(msg)
        self.check_user_permission(msg.author, player)
        new_volume = 0
        try:
            temp_flag = False
            new_volume = msg.clean_content.split(None, 2)[1:]
            if len(new_volume) > 1:
                if new_volume[0] in ("-t", "--temporary"):
                    temp_flag = True
                    new_volume = int(new_volume[1])
                else:
                    raise CommandSyntaxError
            else:
                new_volume = int(new_volume[0])
            if new_volume == 0:
                raise CommandSyntaxError("Please use PauseSong to mute the bot")
            elif not 0 < new_volume <= 100:
                raise CommandSyntaxError("Expected value between 0 and 100")
        except IndexError:
            await respond(msg, f"**ANALYSIS: Current volume is {int(player.volume * 100)}%.**")
            return
        except ValueError:
            raise CommandSyntaxError(f"Value {new_volume} is not a valid integer")
        if temp_flag:
            player.prev_volume = player.volume
        player.volume = new_volume / 100
        await respond(msg, f"**AFFIRMATIVE. Set volume to {new_volume}%.**")

    @Command("SongMode",
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
            player.already_played.clear()
        else:
            raise CommandSyntaxError(f"Argument {arg} is not a valid mode")
        await respond(msg, f"**AFFIRMATIVE. Song mode changed to {player.song_mode}.**")

    @Command("Shuffle",
             doc="Enables or disables shuffling of song order.",
             syntax="[true/yes/on/false/no/off",
             category="music_player")
    async def _shuffle_toggle(self, msg):
        player = self.get_guild_player(msg)
        self.check_user_permission(msg.author, player)
        shuffle_on = player.song_mode in (SongMode.SHUFFLE, SongMode.SHUFFLE_REPEAT)
        try:
            arg = is_positive(msg.clean_content.split(None, 1)[1])
        except IndexError:
            await respond(msg, f"**ANALYSIS: Shuffle is currently {'enabled' if shuffle_on else 'disabled'}.**")
            return
        if arg:
            if shuffle_on:
                await respond(msg, f"**ANALYSIS: Shuffle is already enabled.**")
            else:
                if player.song_mode is SongMode.NORMAL:
                    player.song_mode = SongMode.SHUFFLE
                    await respond(msg, f"**AFFIRMATIVE. Shuffle enabled.**")
                elif player.song_mode is SongMode.REPEAT_QUEUE:
                    player.song_mode = SongMode.SHUFFLE_REPEAT
                    await respond(msg, f"**AFFIRMATIVE. Shuffle enabled with repeat.**")
                elif player.song_mode is SongMode.REPEAT_SONG:
                    await respond(msg, "**NEGATIVE. Shuffle cannot be enabled at the same time as song repeat.**")
        else:
            if shuffle_on:
                if player.song_mode is SongMode.SHUFFLE:
                    player.song_mode = SongMode.NORMAL
                    await respond(msg, f"**AFFIRMATIVE. Shuffle disabled.**")
                elif player.song_mode is SongMode.SHUFFLE_REPEAT:
                    player.already_played.clear()
                    player.song_mode = SongMode.REPEAT_QUEUE
                    await respond(msg, f"**AFFIRMATIVE. Shuffle disabled. Queue repeat still enabled.**")
            else:
                await respond(msg, "**ANALYSIS: Shuffle is not enabled.**")

    @Command("Repeat",
             doc="Modifies repeating mode of song queue.",
             syntax="[song/one/queue/all/false/no/off]",
             category="music_player")
    async def _repeat_mode(self, msg):
        player = self.get_guild_player(msg)
        self.check_user_permission(msg.author, player)
        try:
            arg = msg.clean_content.split(None, 1)[1].lower()
            if arg not in ("song", "one", "queue", "all"):
                arg = is_positive(arg)
                if arg:
                    raise CommandSyntaxError
        except IndexError:
            if player.song_mode is SongMode.REPEAT_SONG:
                repeat_mode = "set to repeat current song"
            elif player.song_mode is SongMode.REPEAT_QUEUE:
                repeat_mode = "set to repeat the queue"
            elif player.song_mode is SongMode.SHUFFLE_REPEAT:
                repeat_mode = "set to repeat the queue. Shuffle is also enabled"
            else:
                repeat_mode = "disabled"
            await respond(msg, f"**ANALYSIS: Repeat is currently {repeat_mode}.**")
            return
        if arg in ("song", "one"):
            if player.song_mode is SongMode.REPEAT_SONG:
                await respond(msg, "**ANALYSIS: Song repeat is already enabled.**")
            elif player.song_mode in (SongMode.SHUFFLE, SongMode.SHUFFLE_REPEAT):
                await respond(msg, "**NEGATIVE. Song repeat cannot be enabled at the same time as shuffle.**")
            else:
                player.song_mode = SongMode.REPEAT_SONG
                await respond(msg, "**AFFIRMATIVE. Repeat mode set to song.**")
        elif arg in ("queue", "all"):
            if player.song_mode in (SongMode.REPEAT_QUEUE, SongMode.SHUFFLE_REPEAT):
                await respond(msg, "**ANALYSIS: Queue repeat is already enabled.**")
            elif player.song_mode is SongMode.SHUFFLE:
                player.song_mode = SongMode.SHUFFLE_REPEAT
                await respond(msg, "**AFFIRMATIVE. Repeat mode set to queue with shuffle.**")
            else:
                player.song_mode = SongMode.REPEAT_QUEUE
                await respond(msg, "**AFFIRMATIVE. Repeat mode set to queue.**")
        else:
            if player.song_mode in (SongMode.NORMAL, SongMode.SHUFFLE):
                await respond("**ANALYSIS: Repeat mode is disabled.**")
            elif player.song_mode is SongMode.SHUFFLE_REPEAT:
                player.already_played.clear()
                player.song_mode = SongMode.SHUFFLE
                await respond(msg, "**AFFIRMATIVE. Repeat mode disabled. Shuffle still enabled.**")
            else:
                player.song_mode = SongMode.NORMAL
                await respond(msg, "**AFFIRMATIVE. Repeat mode disabled.**")

    @Command("SkipSong", "Skip",
             doc="Tells the bot to skip the currently playing song.",
             category="music_player")
    async def _skip_song(self, msg):
        player = self.get_guild_player(msg)
        self.check_user_permission(msg.author, player)
        if not player or not player.is_playing:
            await respond(msg, "**ANALYSIS: No music currently playing.**")
            return
        elif player.voice_client.channel.permissions_for(msg.author).mute_members\
                or self.config_manager.is_maintainer(msg.author):
            await respond(msg, "**ANALYSIS: Skipping to next song in queue...**")
            player.stop()
        else:
            await player.skip_vote(msg.author.id)

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
        player.already_played.clear()
        player.stop()
        await respond(msg, "**ANALYSIS: The music has been stopped and the queue has been cleared.**")

    @Command("MusicBan",
             doc="Bans or unbans a user from using music bot commands, or lists bans if no user specified..",
             syntax="(user)",
             perms="mute_members",
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
            banned_list = "\n".join(str(x) if x else "Unknown" for x in user_li)
            if not banned_list:
                banned_list = "None."
            for split_msg in split_message(f"**ANALYSIS: Banned users:**\n```\n{banned_list}```"):
                await respond(msg, split_msg)
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

    @Command("MusicConfig",
             doc="Allows the configuration of per-server music bot options.\n"
                 "Valid options: 'max_queue_length', 'max_video_length', 'vote_skip_threshold', "
                 "'print_queue_on_edit', 'idle_disconnect_time'",
             syntax="[(option) (value)]",
             perms="manage_guild",
             category="music_player")
    async def _music_config(self, msg):
        gid = str(msg.guild.id)
        try:
            opt, val = msg.clean_content.split(None, 2)[1:]
        except ValueError:
            current_conf = "\n".join(f"{k}: {v}" for k, v in self.plugin_config[gid].items())
            await respond(msg, f"**ANALYSIS: Current configuration:**```{current_conf}```")
            return
        opt = opt.lower()
        if opt in ("max_queue_length", "max_video_length", "idle_disconnect_time"):
            try:
                val = int(val)
            except ValueError:
                raise CommandSyntaxError(f"{val} is not a valid integer")
        elif opt == "vote_skip_threshold":
            try:
                val = float(val)
                if not 0 < val <= 1:
                    raise ValueError
            except ValueError:
                raise CommandSyntaxError("Value must be a number between 0 and 1.")
        elif opt == "print_queue_on_edit":
            val = is_positive(val)
        else:
            raise CommandSyntaxError(f"Option {opt} does not exist")
        self.plugin_config[gid][opt] = val
        await respond(msg, f"**AFFIRMATIVE. Option `{opt}` edited to `{val}` successfully.**")

    # Utility functions

    async def on_global_tick(self, _, dt):
        # Cache reaper
        save_required = False
        for file, dl_time in self.storage["downloaded_songs"].copy().items():
            if time() - dl_time > self.plugin_config["video_cache_clear_age"]:
                try:
                    remove_file(file)
                    del self.storage["downloaded_songs"][file]
                    self.logger.debug(f"Deleted old video cache file {file}.")
                    save_required = True
                except OSError:
                    continue
        if save_required:
            self.storage.save()
        # Auto-disconnect
        for player in tuple(self.players.values()):
            await player.idle_check(dt)

    async def create_player(self, voice_channel, text_channel):
        async with text_channel.typing():
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
        self.already_played = set()
        self.is_playing = False
        self.current_song = {}
        self.song_mode = SongMode.NORMAL
        self.prev_volume = None
        self._volume = self.parent.plugin_config["default_volume"] / 100
        self._song_start_time = None
        self._song_pause_time = None
        self._skip_votes = set()
        self.gid = str(voice_client.guild.id)
        self._alone_time = 0

    async def prepare_playlist(self, urls):
        async with self.text_channel.typing():
            # Fetch video info
            with YoutubeDL(self.parent.ydl_options) as ydl:
                # Create a list of videos to be queued
                to_queue = []
                for url in urls:
                    try:
                        pl_slice = re.match(r"([^{`]+)`*(?:{([^}]*)})?", url)
                        vid_info = await get_running_loop().run_in_executor(None, partial(ydl.extract_info,
                                                                                          pl_slice[1], download=False))
                    except YoutubeDLError as e:
                        await self.text_channel.send(f"**WARNING. An error occurred while downloading video <{url}>. "
                                                     f"It will not be queued.\nError details:** `{e}`")
                        continue
                    # If it's a playlist, we need to flatten it into our to_queue list, and deal with the slicing
                    if vid_info.get("_type") == "playlist":
                        # Slice handling
                        if pl_slice[2]:
                            pl_slices = pl_slice[2].split(",")
                            for s in pl_slices:
                                # Ranges handling
                                if "-" in s:
                                    s_start, s_end = s.split("-", 1)
                                    try:
                                        s_start = int(s_start) - 1
                                    except ValueError:
                                        s_start = 0
                                    try:
                                        s_end = int(s_end)
                                        if s_end > len(vid_info["entries"]):
                                            raise ValueError
                                    except ValueError:
                                        s_end = len(vid_info["entries"])
                                    if s_end < s_start:
                                        continue
                                    to_queue.extend(vid_info["entries"][s_start:s_end])
                                # Single values
                                else:
                                    try:
                                        s = int(s) - 1
                                        to_queue.append(vid_info["entries"][s])
                                    except (ValueError, IndexError):
                                        continue
                        # No slice
                        else:
                            to_queue.extend(vid_info["entries"])
                    # If it's just a video, throw it in
                    else:
                        to_queue.append(vid_info)
            # Queuing is handled by _enqueue_playlist function. Don't bother it if we got nothing.
            if len(to_queue) > 0:
                create_task(self._enqueue_playlist(to_queue))
                return

    async def _enqueue_playlist(self, entries):
        if len(self.queue) > 0:
            time_until_song = self.queue_duration + (self.current_song.get("duration", 0) - self.play_time)
            time_until_song = f"\nTime until your song: {pretty_duration(time_until_song)}"
            await self.text_channel.send(f"**ANALYSIS: Attempting to queue {len(entries)} videos. Your playback will "
                                         f"begin shortly.{time_until_song}**")
        orig_len = len(self.queue)
        async with self.text_channel.typing():
            with YoutubeDL(self.parent.ydl_options) as ydl:
                for vid in entries:
                    # We only want to extract info if we don't already have it. Things get a little funky otherwise.
                    if vid.get("_type") in ("url", "url_transparent"):
                        try:
                            vid = await get_running_loop().run_in_executor(None, partial(ydl.extract_info, vid["url"],
                                                                                         download=False))
                        # Skip broken videos while trying the rest
                        except YoutubeDLError as e:
                            await self.text_channel.send(f"**WARNING. An error occurred while downloading video "
                                                         f"<{vid['url']}>. It will not be queued.\nError details:** "
                                                         f"`{e}`")
                            continue
                    # Abort once the queue is full
                    if len(self.queue) >= get_guild_config(self.parent, self.gid, "max_queue_length"):
                        await self.text_channel.send(f"**WARNING: The queue is full. No more videos will be added.**")
                        break
                    # Skip over videos that are too long
                    elif vid.get("duration", 0) > get_guild_config(self.parent, self.gid, "max_video_length"):
                        max_len = pretty_duration(get_guild_config(self.parent, self.gid, "max_video_length"))
                        await self.text_channel.send(f"**WARNING: Video {vid['title']} exceeds the maximum video"
                                                     f" length ({max_len}). It will not be added.**")
                        continue
                    try:
                        await self._process_video(vid)
                    except TypeError:
                        continue
                    if not self.is_playing:
                        try:
                            create_task(self._play())
                        except ClientException:
                            pass
        await self.text_channel.send(f"**ANALYSIS: Queued {len(self.queue) - orig_len} videos.**")
        if get_guild_config(self.parent, self.gid, "print_queue_on_edit") and self.queue:
            final_msg = f"**ANALYSIS: Current queue:**{self.print_queue()}"
            for msg in split_message(final_msg):
                await self.text_channel.send(msg)

    async def _process_video(self, vid):
        if not vid:
            raise TypeError
        if self.parent.plugin_config["save_audio"] and not vid.get("is_live", False):
            with YoutubeDL(self.parent.ydl_options) as ydl:
                try:
                    await get_running_loop().run_in_executor(None, partial(ydl.process_info, vid))
                    vid["filename"] = ydl.prepare_filename(vid)
                    self.parent.storage["downloaded_songs"][vid["filename"]] = time()
                    self.parent.storage.save()
                except YoutubeDLError as e:
                    await self.text_channel.send(f"**WARNING. An error occurred while downloading video "
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
                try:
                    vids = {i for i, _ in enumerate(self.queue)}
                    eligible_songs = vids - self.already_played
                    if not eligible_songs:
                        self.already_played.clear()
                        eligible_songs = vids
                    eligible_songs = tuple(eligible_songs)
                    next_song = eligible_songs[randint(0, len(eligible_songs) - 1)]
                    self.already_played.add(next_song)
                    next_song = self.queue[next_song]
                except ValueError:
                    next_song = self.queue[0]
            elif self.song_mode == SongMode.SHUFFLE:
                try:
                    next_song = self.queue.pop(randint(0, len(self.queue) - 1))
                except ValueError:
                    next_song = self.queue.pop()
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
            self._skip_votes = set()
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
        if self.prev_volume:
            self.volume = self.prev_volume
            self.prev_volume = None
            await self.text_channel.send(f"**ANALYSIS: Volume reset to {int(self.volume * 100)}%.**")
        source = PCMVolumeTransformer(FFmpegPCMAudio(file, before_options=before_args, options="-vn"),
                                      volume=self._volume)
        self.voice_client.play(source, after=partial(self._after, loop=get_running_loop()))
        self._song_start_time = time()
        self.current_song = next_song
        self._skip_votes = set()
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

    def _after(self, error, loop):
        if error:
            self.logger.error(error)
        run_coroutine_threadsafe(self._play(), loop)

    def stop(self):
        self.is_playing = False
        self._skip_votes = set()
        try:
            self.voice_client.source.cleanup()
        except AttributeError:
            pass
        self.voice_client.stop()

    @property
    def play_time(self):
        try:
            if self.voice_client.is_paused():
                return self._song_pause_time - self._song_start_time
            else:
                return time() - self._song_start_time
        except TypeError:
            return 0

    @property
    def progress(self):
        try:
            fraction = self.play_time / self.current_song["duration"]
        except ZeroDivisionError:
            fraction = 0
        return self.play_time, self.current_song["duration"], fraction

    async def skip_vote(self, uid):
        if uid not in self._skip_votes:
            self._skip_votes.add(uid)
        else:
            await self.text_channel.send("**NEGATIVE. Skip vote already recorded.**")
            return
        total_users = len(self.voice_client.channel.members) - 1  # Don't want to count the bot itself
        threshold = get_guild_config(self.parent, self.gid, "vote_skip_threshold")
        vote_count = len(self._skip_votes)
        if vote_count / total_users >= threshold:
            await self.text_channel.send("**AFFIRMATIVE. Skipping current song.**")
            self.stop()
        else:
            votes_needed = ceil(total_users * threshold) - vote_count
            await self.text_channel.send(f"**AFFIRMATIVE. Skip vote recorded. {votes_needed} votes needed to skip.**")

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, val):
        self._volume = val
        try:
            self.voice_client.source.volume = val
        except AttributeError:
            pass

    @property
    def queue_duration(self):
        try:
            return sum(vid["duration"] for vid in self.queue)
        except TypeError:
            return 0

    def print_queue(self):
        str_list = []
        for i, vid in enumerate(self.queue):
            duration = fixed_width_duration(vid.get("duration", 0))
            # Title truncating and padding
            title = vid.get("title", "Unknown")
            if len(title) >= 59:
                title = title[:56] + "..."
            str_list.append(f"[{i+1:02d}][{title:-<59}][{duration}]")
        return "```\n{}```".format("\n".join(str_list))

    def print_now_playing(self):
        play_time, duration, progress = self.progress
        dur_str = fixed_width_duration(play_time) + "/" + fixed_width_duration(duration)
        progbar = progress_bar(progress, 70)
        title = self.current_song.get("title", "Unknown")
        if len(title) > 57:
            title = title[:54] + "..."
        return f"[{title:-<57}][{dur_str}]\n[{progbar}]"

    async def idle_check(self, dt):
        alone = len(self.voice_client.channel.members) <= 1
        if not alone:
            self._alone_time = 0
            return
        self._alone_time += dt
        if self._alone_time > get_guild_config(self.parent, self.gid, "idle_disconnect_time"):
            self.stop()
            await self.voice_client.disconnect()
            del self.parent.players[int(self.gid)]


def seconds_to_minutes(secs, hours=False):
    mn, sec = divmod(secs, 60)
    if hours:
        hr, mn = divmod(mn, 60)
        return int(hr), int(mn), int(ceil(sec))
    else:
        return int(mn), int(ceil(sec))


def pretty_duration(seconds):
    if seconds <= 0:
        return "Unknown"
    elif seconds >= 3600:
        hours, minutes, seconds = seconds_to_minutes(seconds, hours=True)
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        minutes, seconds = seconds_to_minutes(seconds)
        return f"{minutes:02d}:{seconds:02d}"


def fixed_width_duration(seconds):
    minutes, seconds = seconds_to_minutes(seconds)
    if seconds <= 0:
        return "--:--"
    if minutes > 99:
        if seconds >= 30:
            minutes += 1
        return f"{minutes:04d}m"
    else:
        return f"{minutes:02d}:{seconds:02d}"


def progress_bar(progress, length=70):
    if not 0 <= progress <= 1:
        raise ValueError("First argument is expected to be a floating-point between 0 and 1.")
    bars = floor(length * progress)
    return "█" * bars + "-" * (length - bars)


class SongMode(enum.Enum):
    NORMAL = "normal"
    REPEAT_SONG = "repeat_song"
    REPEAT_QUEUE = "repeat_queue"
    SHUFFLE = "shuffle"
    SHUFFLE_REPEAT = "shuffle_repeat"

    def __str__(self):
        return self.name
