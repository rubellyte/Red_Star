from red_star.plugin_manager import BasePlugin
from red_star.command_dispatcher import Command
from red_star.rs_utils import respond, RSArgumentParser, split_output
from red_star.rs_errors import CommandSyntaxError, ChannelNotFoundError
import datetime
import shlex
import asyncio
import threading
import re
from discord import Message
from collections import namedtuple


class Reminder(BasePlugin):
    name = "reminder"
    run_timer = False
    timer = None

    pattern = re.compile(r"(?:(?P<D>\d{1,2})/(?P<M>\d{1,2})/(?P<Y>\d{1,4}))?[^\d]*(?:(?P<h>\d{0,2}):(?P<m>\d{0,2}):(?P<s>\d{0,2}))")

    # storage for the reminders
    rem = namedtuple("reminder", ["uid", "cid", "time", "text", "dm"])

    async def activate(self):
        for guild in self.client.guilds:
            if guild.id not in self.storage:
                self.storage[guild.id] = []
        self.run_timer = True

        loop = asyncio.new_event_loop()
        t_loop = asyncio.get_event_loop()
        self.timer = threading.Thread(target=self.start_timer, args=[loop, t_loop])
        self.timer.setDaemon(True)
        self.timer.start()

    async def deactivate(self):
        self.run_timer = False

    @Command("remind",
             syntax="(message) [-d/--delay DD/-/-@HH:MM:SS] [-t/--time DD/MM/YYYY@HH:MM:SS] [-p/--private]",
             doc="Store a reminder for the future. Message needs to come before the time options.\n"
                 "-d/--delay: remind after a set delay. Does NOT support months or years due to varying time.\n"
                 "-t/--time : remind on a given date. Date must be in the future.\n"
                 "Time format: DD/MM/YYYY@hh:mm:ss. Numbers may be skipped, but a date needs two slashes and a time "
                 "needs two colons, with some non-whitespace symbol separating the two.\n"
                 "Valid input includes '23//'",
             category="reminder")
    async def _remind(self, msg: Message):
        parser = RSArgumentParser()
        parser.add_argument("command")
        parser.add_argument("reminder", default=[], nargs="*")
        parser.add_argument("-d", "--delay", default='')
        parser.add_argument("-t", "--time", default='')
        parser.add_argument("-p", "--private", action='store_true')

        args = parser.parse_args(shlex.split(msg.clean_content))

        if not (args['time'] or args['delay']):
            raise CommandSyntaxError("Expected a reminder time")
        else:
            time = args['time'] if args['time'] else args['delay']

        time = {k: int(v or 0) for k, v in self.pattern.match(time).groupdict(0).items()}

        if args['private']:
            try:
                await msg.delete()
            except Exception:
                pass

        try:
            if args['time']:
                time = datetime.datetime(min(time['Y'], 1), min(time['M'], 1), min(time['D'], 1),
                                         time['h'], time['m'], time['s'])
            else:
                time = datetime.datetime.utcnow() + datetime.timedelta(time['D'], hours=time['h'],
                                                                       minutes=time['m'], seconds=time['s'])
        except ValueError as e:
            raise CommandSyntaxError(e)

        if time < datetime.datetime.utcnow():
            raise CommandSyntaxError("Can not alter past")

        self.storage[msg.guild.id].append(self.rem._make((msg.author.id,
                                                          msg.channel.id,
                                                          time,
                                                          ' '.join(args['reminder']),
                                                          args['private'])))
        await respond(msg, f"**AFFIRMATIVE: reminder set for {time.strftime('%Y-%m-%d @ %H:%M:%S')} UTC.**")

    @Command("remindlist",
             syntax="[-/del/delete index]",
             doc="Prints out a list of all reminders of the user.\nUse del argument and an index from said list to "
                 "remove reminders.",
             category="reminder")
    async def _remindlist(self, msg: Message):
        uid = msg.author.id
        args = msg.clean_content.split(None, 2)
        r_list = [r for r in self.storage[msg.guild.id] if r.uid == uid]
        if len(args) == 1:
            await split_output(msg, "**Following reminders found:**", enumerate(r_list),
                               f=lambda r: f"{r[0]:2}|{r[1].time.strftime('%Y-%m-%d @ %H:%M:%S')} : {r[1].text:50} in "
                                           f"{'Direct Messages' if r[1].dm else msg.guild.get_channel(r[1].cid)}\n")
        elif len(args) == 3 and args[1].lower() in ("del", "-", "delete"):
            try:
                index = int(args[2])
            except ValueError:
                raise CommandSyntaxError("Non-integer syntax provided")
            if 0 <= index < len(r_list):
                self.storage[msg.guild.id] =\
                    [x for x in self.storage[msg.guild.id] if x != r_list[index]]
                await respond(msg, "**AFFIRMATIVE. Reminder removed.**")
            else:
                raise CommandSyntaxError("Index out of range")
        else:
            raise CommandSyntaxError("No arguments or del/-/delete index required")

    def start_timer(self, loop, t_loop):
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.tick_time(t_loop))
        except Exception:
            self.logger.exception("Error starting timer. ", exc_info=True)

    async def tick_time(self, t_loop):
        """
        Updates client status every ten seconds based on music status.
        Also runs the every-few-second stuff
        """

        while self.run_timer:
            await asyncio.sleep(10)
            dtnow = datetime.datetime.utcnow()
            for guild in filter(lambda x: x.id in self.storage, self.client.guilds):
                for reminder in filter(lambda x: x.time <= dtnow, self.storage[guild.id]):
                    if reminder.dm:
                        usr = guild.get_member(reminder.uid)
                        if usr:
                            asyncio.ensure_future(usr.send(f"**Reminder from {guild}:**\n{reminder.text}"),
                                                  loop=t_loop)
                    else:
                        try:
                            channel = self.channel_manager.get_channel(guild, "reminders")
                        except ChannelNotFoundError:
                            channel = guild.get_channel(reminder.cid)
                        if channel:
                            asyncio.ensure_future(channel.send(f"**<@{reminder.uid}>:**\n{reminder.text}"),
                                                  loop=t_loop)
                        else:
                            usr = guild.get_member(reminder.uid)
                            if usr:
                                asyncio.ensure_future(usr.send(f"**Reminder from {guild}:**\n{reminder.text}"),
                                                      loop=t_loop)
                # it's easier to create a new list where everything fits rather than delete from old
                self.storage[guild.id] = [x for x in self.storage[guild.id] if x.time > dtnow]



