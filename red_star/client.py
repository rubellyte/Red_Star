import datetime
import logging
import discord
from argparse import Namespace
from pathlib import Path
from sys import exc_info
from red_star.config_manager import ConfigManager
from red_star.plugin_manager import PluginManager


class RedStar(discord.AutoShardedClient):
    def __init__(self, storage_dir: Path, argv: Namespace):
        self.logger = logging.getLogger("red_star")
        dpy_logger = logging.getLogger("discord")
        if argv.verbose > 0:
            self.logger.setLevel(logging.DEBUG)
            dpy_logger.setLevel(logging.DEBUG if argv.verbose >= 2 else logging.INFO)
        else:
            self.logger.setLevel(logging.INFO)
            dpy_logger.setLevel(logging.INFO)
        self.logger.info("Initializing...")

        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(intents=intents, enable_debug_events=(argv.verbose >= 2))

        self.storage_dir = storage_dir
        self.plugin_directories = [Path.cwd() / "plugins"]
        if not argv.portable:
            self.plugin_directories.append(self.storage_dir / "plugins")

        self.config_manager = ConfigManager(storage_dir / "config")
        self.config = self.config_manager.config

        self.plugin_manager = PluginManager(self)
        self.plugin_manager.load_all_plugins(self.plugin_directories)

        self.logged_in = False
        self.last_error = None

    async def on_ready(self):
        if not self.logged_in:
            self.logged_in = True
            self.logger.info("Logged in as:")
            self.logger.info(self.user)
            self.logger.info(self.user.id)
            self.logger.info("------------")
            self.logger.info("Activating plugins.")
            # create_task(self.global_tick_dispatcher())
            if len(self.guilds) == 0:
                self.logger.info("It looks like you haven't yet added the bot to any servers. Paste the link below "
                                 "into your browser and invite the bot to some servers!")
                self.logger.info(discord.utils.oauth_url(self.user.id))
            await self.plugin_manager.activate_all()

    async def close(self):
        self.logger.warning("Logging out and shutting down.")
        await self.plugin_manager.deactivate_all()
        self.config_manager.save_config()
        await super().close()

    async def on_error(self, event_method: str, *pargs, **kwargs):
        exc = exc_info()
        self.last_error = exc
        self.logger.exception(f"Unhandled {exc[0].__name__} occurred in {event_method}: ", exc_info=True)

    # async def on_resumed(self):
    #     await self.plugin_manager.hook_event("on_resumed")

    async def on_typing(self, channel: discord.abc.Messageable, user: discord.abc.User,
                        when: datetime.datetime):
        if not isinstance(channel, discord.abc.GuildChannel):
            return
        # if self.channel_manager.channel_in_category(channel.guild, "no_read", channel):
        #     return
        await self.plugin_manager.hook_event("on_typing", channel.guild, channel, user, when)

    async def on_message(self, msg: discord.Message):
        if msg.guild is not None:
            # if self.channel_manager.channel_in_category(msg.guild, "no_read", msg.channel):
            #     return
            # await self.command_dispatcher.command_check(msg)
            await self.plugin_manager.hook_event("on_message", msg.guild, msg)
        # else:
        #     await self.command_dispatcher.command_check(msg)
        #     await self.plugin_manager.hook_event("on_dm_message", msg)

    async def on_message_delete(self, msg: discord.Message):
        if msg.guild is None:
            return
        # if self.channel_manager.channel_in_category(msg.guild, "no_read", msg.channel):
        #     return
        await self.plugin_manager.hook_event("on_message_delete", msg.guild, msg)

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.guild is None:
            return
        # if self.channel_manager.channel_in_category(after.guild, "no_read", after.channel):
        #     return
        await self.plugin_manager.hook_event("on_message_edit", after.guild, before, after)

    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.abc.User):
        if reaction.message.guild is None:
            return
        # if self.channel_manager.channel_in_category(reaction.message.guild, "no_read", reaction.message.channel):
        #     return
        await self.plugin_manager.hook_event("on_reaction_add", reaction.message.guild, reaction, user)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.channel_id is not None:
            channel = self.get_channel(payload.channel_id)
            if isinstance(channel, discord.abc.GuildChannel):
                await self.plugin_manager.hook_event("on_raw_reaction_add", channel.guild, payload)

    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.abc.User):
        if reaction.message.guild is None:
            return
        # if self.channel_manager.channel_in_category(reaction.message.guild, "no_read", reaction.message.channel):
        #     return
        await self.plugin_manager.hook_event("on_reaction_remove", reaction, user)

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.channel_id is not None:
            channel = self.get_channel(payload.channel_id)
            if isinstance(channel, discord.abc.GuildChannel):
                await self.plugin_manager.hook_event("on_raw_reaction_remove", channel.guild, payload)

    async def on_reaction_clear(self, message: discord.Message, reactions: [discord.Reaction]):
        if message.guild is None:
            return
        # if self.channel_manager.channel_in_category(message.guild, "no_read", message.channel):
        #     return
        await self.plugin_manager.hook_event("on_reaction_clear", message.guild, message, reactions)

    # async def on_private_channel_update(self, before: discord.abc.PrivateChannel, after: discord.abc.PrivateChannel):
    #     await self.plugin_manager.hook_event("on_private_channel_update", before, after)
    #  TODO: update me
    # async def on_private_channel_pins_update(self, channel: discord.abc.PrivateChannel, last_pin: datetime.datetime):
    #     await self.plugin_manager.hook_event("on_private_channel_pins_update", channel, last_pin)

    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await self.plugin_manager.hook_event("on_guild_channel_create", channel.guild, channel)

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await self.plugin_manager.hook_event("on_guild_channel_delete", channel.guild, channel)

    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        await self.plugin_manager.hook_event("on_guild_channel_update", after.guild, before, after)

    async def on_guild_channel_pins_update(self, channel: discord.abc.GuildChannel, last_pin: datetime.datetime):
        # if self.channel_manager.channel_in_category(channel.guild, "no_read", channel):
        #     return
        await self.plugin_manager.hook_event("on_guild_channel_pins_update", channel.guild, channel, last_pin)

    async def on_member_join(self, member: discord.Member):
        await self.plugin_manager.hook_event("on_member_join", member.guild, member)

    async def on_member_remove(self, member: discord.Member):
        await self.plugin_manager.hook_event("on_member_remove", member.guild, member)

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        await self.plugin_manager.hook_event("on_member_update", after.guild, before, after)

    # async def on_guild_join(self, guild: discord.Guild): # TODO: this will activate plugins for server
    #     self.channel_manager.add_guild(str(guild.id))
    #     await self.plugin_manager.hook_event("on_guild_join", guild)

    # async def on_guild_remove(self, guild: discord.Guild): # TODO: this will deactivate plugins for server
    #     await self.plugin_manager.hook_event("on_guild_remove", guild) # and trash all the configs, probably

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        await self.plugin_manager.hook_event("on_guild_update", after, before, after)

    async def on_guild_role_create(self, role: discord.Role):
        await self.plugin_manager.hook_event("on_guild_role_create", role.guild, role)

    async def on_guild_role_delete(self, role: discord.Role):
        await self.plugin_manager.hook_event("on_guild_role_delete", role.guild, role)

    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        await self.plugin_manager.hook_event("on_guild_role_update", after.guild, before, after)

    async def on_guild_emojis_update(self, guild: discord.Guild, before: discord.Emoji, after: discord.Emoji):
        await self.plugin_manager.hook_event("on_guild_emojis_update", guild, before, after)

    async def on_guild_available(self, guild: discord.Guild):
        await self.plugin_manager.hook_event("on_guild_available", guild)

    async def on_guild_unavailable(self, guild: discord.Guild):
        await self.plugin_manager.hook_event("on_guild_unavailable", guild)

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState):
        await self.plugin_manager.hook_event("on_voice_state_update", member.guild, member, before, after)

    async def on_member_ban(self, guild: discord.Guild, member: discord.Member):
        await self.plugin_manager.hook_event("on_member_ban", guild, member)

    async def on_member_unban(self, guild: discord.Guild, member: discord.Member):
        await self.plugin_manager.hook_event("on_member_unban", guild, member)

    # async def on_group_join(self, channel: discord.GroupChannel, user: discord.User):
    #     await self.plugin_manager.hook_event("on_group_join", channel, user)
    #
    # async def on_group_remove(self, channel: discord.GroupChannel, user: discord.User):
    #     await self.plugin_manager.hook_event("on_group_remove", channel, user)

    # async def global_tick_dispatcher(self):
    #     timer = self.config.get("global_tick_interval", 15)
    #     while self.logged_in:
    #         await sleep(timer)
    #         create_task(self.plugin_manager.hook_event("on_global_tick", discord.utils.utcnow(), timer))
