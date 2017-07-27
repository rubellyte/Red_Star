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

    @asyncio.coroutine
    def start_bot(self):
        self.logger.info("Logging in...")
        yield from self.start(self.config["token"])

    @asyncio.coroutine
    def on_ready(self):
        if not self.logged_in:
            self.logger.info("Logged in as")
            self.logger.info(self.user.name)
            self.logger.info(self.user.id)
            self.logger.info("------------")
            self.logged_in = True
            self.plugin_manager.activate_all()

    @asyncio.coroutine
    def on_resumed(self):
        yield from self.plugin_manager.hook_event("on_resumed")

    @asyncio.coroutine
    def on_error(self, event, *args, **kwargs):
        raise

    @asyncio.coroutine
    def on_message(self, msg):
        yield from self.plugin_manager.hook_event("on_message", msg)

    @asyncio.coroutine
    def on_message_delete(self, msg):
        yield from self.plugin_manager.hook_event("on_message_delete", msg)

    @asyncio.coroutine
    def on_message_edit(self, before, after):
        yield from self.plugin_manager.hook_event("on_message_edit", msg)

    @asyncio.coroutine
    def on_reaction_add(self, reaction, user):
        yield from self.plugin_manager.hook_event("on_reaction_add", reaction, user)

    @asyncio.coroutine
    def on_reaction_remove(self, reaction, user):
        yield from self.plugin_manager.hook_event("on_reaction_remove", reaction, user)

    @asyncio.coroutine
    def on_reaction_clear(self, message, reactions):
        yield from self.plugin_manager.hook_event("on_reaction_clear", message, reactions)

    @asyncio.coroutine
    def on_channel_create(self, channel):
        yield from self.plugin_manager.hook_event("on_channel_create", channel)

    @asyncio.coroutine
    def on_channel_delete(self, channel):
        yield from self.plugin_manager.hook_event("on_channel_delete", channel)

    @asyncio.coroutine
    def on_channel_update(self, before, after):
        yield from self.plugin_manager.hook_event("on_channel_update", before, after)

    @asyncio.coroutine
    def on_member_join(self, member):
        yield from self.plugin_manager.hook_event("on_member_join", member)

    @asyncio.coroutine
    def on_member_remove(self, member):
        yield from self.plugin_manager.hook_event("on_member_remove", member)

    @asyncio.coroutine
    def on_member_update(self, before, after):
        yield from self.plugin_manager.hook_event("on_member_update", before, after)

    @asyncio.coroutine
    def on_server_join(self, server):
        yield from self.plugin_manager.hook_event("on_server_join", server)

    @asyncio.coroutine
    def on_server_remove(self, server):
        yield from self.plugin_manager.hook_event("on_server_remove", server)

    @asyncio.coroutine
    def on_server_update(self, before, after):
        yield from self.plugin_manager.hook_event("on_server_update", before, after)

    @asyncio.coroutine
    def on_server_role_create(self, role):
        yield from self.plugin_manager.hook_event("on_server_role_create", role)

    @asyncio.coroutine
    def on_server_role_delete(self, role):
        yield from self.plugin_manager.hook_event("on_server_role_delete", role)

    @asyncio.coroutine
    def on_server_role_update(self, before, after):
        yield from self.plugin_manager.hook_event("on_server_role_update", before, after)

    @asyncio.coroutine
    def on_server_emojis_update(self, before, after):
        yield from self.plugin_manager.hook_event("on_server_emojis_update", before, after)

    @asyncio.coroutine
    def on_server_available(self, server):
        yield from self.plugin_manager.hook_event("on_server_available", server)

    @asyncio.coroutine
    def on_server_unavailable(self, server):
        yield from self.plugin_manager.hook_event("on_server_unavailable", server)

    @asyncio.coroutine
    def on_voice_state_update(self, before, after):
        yield from self.plugin_manager.hook_event("on_voice_state_update", before, after)

    @asyncio.coroutine
    def on_member_ban(self, member):
        yield from self.plugin_manager.hook_event("on_member_ban", member)

    @asyncio.coroutine
    def on_member_unban(self, member):
        yield from self.plugin_manager.hook_event("on_member_unban", member)

    @asyncio.coroutine
    def on_typing(self, channel, user, when):
        yield from self.plugin_manager.hook_event("on_typing", channel, user, when)


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
    except KeyboardInterrupt:
        main_logger.info("Interrupt caught, shutting down...")
        loop.run_until_complete(bot.logout())
        bot.config_manager.save_config()
    finally:
        main_logger.info("Exiting...")
        loop.close()
