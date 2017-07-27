import discord
import asyncio
import json
import logging
import urllib.request
import re


class RedStar(discord.Client):

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("RedStar")
        if DEBUG:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)
        self.logger.debug("Initializing...")
        try:
            with open("config.json", "r") as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.logger.error("config.json not found! Copying default...")
            from shutil import copyfile
            try:
                copyfile("config.json.default", "config.json")
            except FileNotFoundError:
                self.logger.error("config.json.default not found! Exiting...")
                raise SystemExit
            with open("config.json", "r") as f:
                self.config = json.load(f)
        except json.decoder.JSONDecodeError:
            self.logger.error("config.json is invalid! Exiting...")
            raise SystemExit
        self.commands = {func[4:]: getattr(self, func) for func in dir(self) if
                         callable(getattr(self, func)) and
                         func.startswith("cmd_")}
        self.logged_in = False
        asyncio.ensure_future(self.start_bot())

    @asyncio.coroutine
    def start_bot(self):
        self.logger.info("Logging in...")
        yield from self.start(self.config["token"])

    def save_config(self):
        self.logger.info("Saving configuration...")
        with open("config.json", "w") as f:
            json.dump(self.config, f, indent=2, sort_keys=True)

    @asyncio.coroutine
    def on_ready(self):
        if not self.logged_in:
            self.logger.info("Logged in as")
            self.logger.info(self.user.name)
            self.logger.info(self.user.id)
            self.logger.info("------------")
            self.logged_in = True
            self.primary_channel = self.get_channel(
                self.config["primary_channel"])
            yield from self.send_message(self.primary_channel,
                                         self.config["greeting_message"])

    @asyncio.coroutine
    def on_message(self, msg):
        self.logger.info("{} - {}: {}".format(
            msg.timestamp, msg.author, msg.content))
        if msg.author != self.user:
            cnt = msg.content
            if cnt.startswith(self.config["command_decorator"]):
                cmd = cnt[len(self.config["command_decorator"]):].split()[0]
                if cmd in self.commands:
                    yield from self.commands[cmd](msg)
                    
    @asyncio.coroutine
    def on_member_join(self, member):
        msg = self.config["new_member_message"].replace("<joinername>", member.mention)
        yield from self.send_message(self.primary_channel, msg)

    @asyncio.coroutine
    def cmd_update_avatar(self, data):
        url = " ".join(data.content.split()[1:])
        if url:
            try:
                img = urllib.request.urlopen(url).read()
                yield from self.edit_profile(avatar=img)
                yield from self.send_message(data.channel,
                                             "**Avatar updated.**")
            except (urllib.request.URLError, ValueError) as e:
                self.logger.debug(e)
                yield from self.send_message(data.channel,
                                             "**Invalid URL provided.**")
            except discord.InvalidArgument:
                yield from self.send_message(data.channel,
                                             "**Image must be a PNG or JPG.**")
        else:
            yield from self.send_message(data.channel, "**No URL provided.**")

    @asyncio.coroutine
    def cmd_set_primary_channel(self, data):
        if data.channel_mentions:
            self.config["primary_channel"] = data.channel_mentions[0].id
            self.save_config()
            yield from self.send_message(data.channel,
                                         "**Updated primary channel.**")
        else:
            yield from self.send_message(data.channel,
                                         "**No channel specified.**")

    @asyncio.coroutine
    def cmd_purge(self, data):
        perms = data.author.permissions_in(data.channel)
        if perms.manage_messages:
            cnt = data.content.split()
            try:
                count = int(cnt[1])
                if count > 250:
                    count = 250
            except ValueError:
                count = 100
            yield from self.delete_message(data)
            if len(cnt) > 2:
                self.searchstr = " ".join(cnt[2:])
            else:
                self.searchstr = ""
            deleted = yield from self.purge_from(
                data.channel, limit=count, check=self.search)
            self.searchstr = ""
            fb = yield from self.send_message(
                data.channel, "**PURGE COMPLETE: purged {} messages.**"
                .format(len(deleted)))
            yield from asyncio.sleep(5)
            yield from self.delete_message(fb)
        else:
            yield from self.delete_message(data)
            fb = yield from self.send_message(data.channel,
                "**WARNING: Insufficient access: purge command.**")
            yield from asyncio.sleep(5)
            yield from self.delete_message(fb)

    def search(self, data):
        if self.searchstr:
            if self.searchstr.startswith("re:"):
                search = self.searchstr[3:]
                self.logger.debug(search)
                return re.match(search, data.content)
            else:
                return self.searchstr in data.content
        else:
            return True


if __name__ == "__main__":
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
        loop.run_until_complete(bot.start(bot.config["token"]))
    except KeyboardInterrupt:
        main_logger.info("Interrupt caught, shutting down...")
        loop.run_until_complete(bot.logout())
        bot.save_config()
    finally:
        main_logger.info("Exiting...")
        loop.close()
