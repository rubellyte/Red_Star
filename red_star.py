import discord
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from channel_manager import ChannelManager
from command_dispatcher import CommandDispatcher
from config_manager import ConfigManager
from plugin_manager import PluginManager
from sys import exc_info


class RedStar(discord.AutoShardedClient):

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("red_star")
        if DEBUG:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)
        self.logger.debug("Initializing...")
        self.config_manager = ConfigManager()
        self.config_manager.load_config(path / "config" / "config.json")
        self.config = self.config_manager.config
        self.channel_manager = ChannelManager(self)
        self.command_dispatcher = CommandDispatcher(self)
        self.plugin_manager = PluginManager(self)
        self.plugin_manager.load_from_path(path / self.config.plugin_path)
        self.plugin_manager.final_load()
        self.logged_in = False
        self.server_ready = False
        self.last_error = None

    async def on_ready(self):
        if not self.logged_in:
            self.logged_in = True
            self.logger.info("Logged in as")
            self.logger.info(self.user.name)
            self.logger.info(self.user.id)
            self.logger.info("------------")
            if self.server_ready:
                self.logger.info("Logged in with server; activating plugins.")
                await self.plugin_manager.activate_all()

    async def stop_bot(self):
        await self.plugin_manager.deactivate_all()
        self.logger.info("Closing the shelf.")
        self.plugin_manager.shelve.close()
        self.config_manager.save_config()
        self.logger.info("Logging out.")
        try:
            await self.logout()
        except discord.errors.ConnectionClosed:
            pass
        raise SystemExit

    async def on_error(self, event_method, *args, **kwargs):
        exc = exc_info()
        self.last_error = exc
        self.logger.exception(f"Unhandled {exc[0].__name__} occurred in {event_method}: ", exc_info=True)

    async def on_resumed(self):
        await self.plugin_manager.hook_event("on_resumed")

    async def on_typing(self, channel, user, when):
        if self.channel_manager.channel_in_category(channel.guild, "noread", channel):
            return
        await self.plugin_manager.hook_event("on_typing", channel, user, when)

    async def on_message(self, msg):
        if self.channel_manager.channel_in_category(msg.guild, "noread", msg.channel):
            return
        await self.command_dispatcher.command_check(msg)
        await self.plugin_manager.hook_event("on_message", msg)

    async def on_message_delete(self, msg):
        if self.channel_manager.channel_in_category(msg.guild, "noread", msg.channel):
            return
        await self.plugin_manager.hook_event("on_message_delete", msg)

    async def on_message_edit(self, before, after):
        if self.channel_manager.channel_in_category(after.guild, "noread", after.channel):
            return
        await self.plugin_manager.hook_event("on_message_edit", before, after)

    async def on_reaction_add(self, reaction, user):
        if self.channel_manager.channel_in_category(reaction.message.guild, "noread", reaction.message.channel):
            return
        await self.plugin_manager.hook_event("on_reaction_add", reaction, user)

    async def on_reaction_remove(self, reaction, user):
        if self.channel_manager.channel_in_category(reaction.message.guild, "noread", reaction.message.channel):
            return
        await self.plugin_manager.hook_event("on_reaction_remove", reaction, user)

    async def on_reaction_clear(self, message, reactions):
        if self.channel_manager.channel_in_category(message.guild, "noread", message.channel):
            return
        await self.plugin_manager.hook_event("on_reaction_clear", message, reactions)

    async def on_private_channel_create(self, channel):
        await self.plugin_manager.hook_event("on_private_channel_create", channel)

    async def on_private_channel_delete(self, channel):
        await self.plugin_manager.hook_event("on_private_channel_delete", channel)

    async def on_private_channel_update(self, before, after):
        await self.plugin_manager.hook_event("on_private_channel_update", before, after)

    async def on_private_channel_pins_update(self, channel, last_pin):
        await self.plugin_manager.hook_event("on_private_channel_pins_update", channel, last_pin)

    async def on_guild_channel_create(self, channel):
        await self.plugin_manager.hook_event("on_guild_channel_create", channel)

    async def on_guild_channel_delete(self, channel):
        await self.plugin_manager.hook_event("on_guild_channel_delete", channel)

    async def on_guild_channel_update(self, before, after):
        await self.plugin_manager.hook_event("on_guild_channel_update", before, after)

    async def on_guild_channel_pins_update(self, channel, last_pin):
        if self.channel_manager.channel_in_category(channel.guild, "noread", channel):
            return
        await self.plugin_manager.hook_event("on_guild_channel_pins_update", channel, last_pin)

    async def on_member_join(self, member):
        await self.plugin_manager.hook_event("on_member_join", member)

    async def on_member_remove(self, member):
        await self.plugin_manager.hook_event("on_member_remove", member)

    async def on_member_update(self, before, after):
        await self.plugin_manager.hook_event("on_member_update", before, after)

    async def on_guild_join(self, guild):
        self.channel_manager.add_guild(guild)
        await self.plugin_manager.hook_event("on_guild_join", guild)

    async def on_guild_remove(self, guild):
        await self.plugin_manager.hook_event("on_guild_remove", guild)

    async def on_guild_update(self, before, after):
        await self.plugin_manager.hook_event("on_guild_update", before, after)

    async def on_guild_role_create(self, role):
        await self.plugin_manager.hook_event("on_guild_role_create", role)

    async def on_guild_role_delete(self, role):
        await self.plugin_manager.hook_event("on_guild_role_delete", role)

    async def on_guild_role_update(self, before, after):
        await self.plugin_manager.hook_event("on_guild_role_update", before, after)

    async def on_guild_emojis_update(self, guild, before, after):
        await self.plugin_manager.hook_event("on_guild_emojis_update", guild, before, after)

    async def on_guild_available(self, guild):
        self.channel_manager.add_guild(guild)
        if not self.server_ready:
            self.server_ready = True
            self.logger.info("A server is now available.")
            if self.logged_in:
                self.logger.info("Logged in with server; activating plugins.")
                await self.plugin_manager.activate_all()
        await self.plugin_manager.hook_event("on_guild_available", guild)

    async def on_guild_unavailable(self, guild):
        await self.plugin_manager.hook_event("on_guild_unavailable", guild)

    async def on_voice_state_update(self, member, before, after):
        await self.plugin_manager.hook_event("on_voice_state_update", member, before, after)

    async def on_member_ban(self, guild, member):
        await self.plugin_manager.hook_event("on_member_ban", guild, member)

    async def on_member_unban(self, guild, member):
        await self.plugin_manager.hook_event("on_member_unban", guild, member)

    async def on_group_join(self, channel, user):
        await self.plugin_manager.hook_event("on_group_join", channel, user)

    async def on_group_remove(self, channel, user):
        await self.plugin_manager.hook_event("on_group_remove", channel, user)

if __name__ == "__main__":
    path = Path(__file__).parent
    DEBUG = True
    if DEBUG:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO

    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s # %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S')
    logger = logging.getLogger()
    ch = logging.StreamHandler()
    ch.setLevel(loglevel)
    ch.setFormatter(formatter)
    fl = RotatingFileHandler("red_star.log", maxBytes=10485760, backupCount=3, encoding="utf-8")
    fl.setLevel(loglevel)
    fl.setFormatter(formatter)
    logger.addHandler(ch)
    logger.addHandler(fl)
    bot = RedStar()
    loop = asyncio.get_event_loop()
    task = loop.create_task(bot.start(bot.config.token))
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        bot.logger.info("Interrupt caught, shutting down...")
    except SystemExit:
        pass
    finally:
        pending = asyncio.Task.all_tasks()
        for task in pending:
            task.cancel()
        bot.logger.info("Exiting...")
        loop.close()
