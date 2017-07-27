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
    def on_message(self, msg):
        yield from self.plugin_manager.hook_event("on_message", msg)

    @asyncio.coroutine
    def on_member_join(self, member):
        yield from self.plugin_manager.hook_event("on_member_join", member)


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
