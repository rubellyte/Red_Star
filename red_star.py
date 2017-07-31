import discord
import asyncio
import logging
from pathlib import Path
from config_manager import ConfigManager
from plugin_manager import PluginManager


class RedStar(discord.Client):

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
        self.plugin_manager = PluginManager(self, self.config_manager)
        self.plugin_manager.load_from_path(path / self.config.plugin_path)
        self.plugin_manager.final_load()
        self.logged_in = False
        asyncio.ensure_future(self.start_bot())

    async def start_bot(self):
        self.logger.info("Logging in...")
        await self.start(self.config["token"])

    async def on_ready(self):
        if not self.logged_in:
            self.logger.info("Logged in as")
            self.logger.info(self.user.name)
            self.logger.info(self.user.id)
            self.logger.info("------------")
            self.logged_in = True
            self.plugin_manager.activate_all()

    async def on_resumed(self):
        await self.plugin_manager.hook_event("on_resumed")

    async def on_message(self, msg):
        await self.plugin_manager.hook_event("on_message", msg)

    async def on_message_delete(self, msg):
        await self.plugin_manager.hook_event("on_message_delete", msg)

    async def on_message_edit(self, before, after):
        await self.plugin_manager.hook_event("on_message_edit", before, after)

    async def on_reaction_add(self, reaction, user):
        await self.plugin_manager.hook_event("on_reaction_add", reaction, user)

    async def on_reaction_remove(self, reaction, user):
        await self.plugin_manager.hook_event("on_reaction_remove", reaction, user)

    async def on_reaction_clear(self, message, reactions):
        await self.plugin_manager.hook_event("on_reaction_clear", message, reactions)

    async def on_channel_create(self, channel):
        await self.plugin_manager.hook_event("on_channel_create", channel)

    async def on_channel_delete(self, channel):
        await self.plugin_manager.hook_event("on_channel_delete", channel)

    async def on_channel_update(self, before, after):
        await self.plugin_manager.hook_event("on_channel_update", before, after)

    async def on_member_join(self, member):
        await self.plugin_manager.hook_event("on_member_join", member)

    async def on_member_remove(self, member):
        await self.plugin_manager.hook_event("on_member_remove", member)

    async def on_member_update(self, before, after):
        await self.plugin_manager.hook_event("on_member_update", before, after)

    async def on_server_join(self, server):
        await self.plugin_manager.hook_event("on_server_join", server)

    async def on_server_remove(self, server):
        await self.plugin_manager.hook_event("on_server_remove", server)

    async def on_server_update(self, before, after):
        await self.plugin_manager.hook_event("on_server_update", before, after)

    async def on_server_role_create(self, role):
        await self.plugin_manager.hook_event("on_server_role_create", role)

    async def on_server_role_delete(self, role):
        await self.plugin_manager.hook_event("on_server_role_delete", role)

    async def on_server_role_update(self, before, after):
        await self.plugin_manager.hook_event("on_server_role_update", before, after)

    async def on_server_emojis_update(self, before, after):
        await self.plugin_manager.hook_event("on_server_emojis_update", before, after)

    async def on_server_available(self, server):
        await self.plugin_manager.hook_event("on_server_available", server)

    async def on_server_unavailable(self, server):
        await self.plugin_manager.hook_event("on_server_unavailable", server)

    async def on_voice_state_update(self, before, after):
        await self.plugin_manager.hook_event("on_voice_state_update", before, after)

    async def on_member_ban(self, member):
        await self.plugin_manager.hook_event("on_member_ban", member)

    async def on_member_unban(self, member):
        await self.plugin_manager.hook_event("on_member_unban", member)

    async def on_typing(self, channel, user, when):
        await self.plugin_manager.hook_event("on_typing", channel, user, when)


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
    logger.addHandler(ch)
    bot = RedStar()
    loop = asyncio.get_event_loop()
    main_logger = logging.getLogger("MAIN")
    try:
        loop.run_until_complete(bot.start(bot.config.token))
    except (KeyboardInterrupt, SystemExit):
        main_logger.info("Interrupt caught, shutting down...")
        loop.run_until_complete(bot.logout())
        bot.config_manager.save_config()
    finally:
        main_logger.info("Exiting...")
        for task in asyncio.Task.all_tasks():
            task.cancel()
        loop.close()
