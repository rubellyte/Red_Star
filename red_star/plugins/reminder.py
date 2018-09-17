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
from dataclasses import dataclass


class Reminder(BasePlugin):
    name = "reminder"
    run_timer = False
    timer = None
    reminder_file_path = None

    pattern = re.compile(
        r"(?:(?P<D>\d{0,2})/(?P<M>\d{0,2})/(?P<Y>\d{0,4}))?[^\d]*(?:(?P<h>\d{0,2}):(?P<m>\d{0,2}):(?P<s>\d{0,2}))")

    @dataclass
    class Rem:
        uid: int
        cid: int
        time: datetime.datetime
        text: str
        dm: bool
        recurring: list

        # number of days in each months, for checking
        _mdays = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

        def __post_init__(self):
            if isinstance(self.time, str):
                self.time = datetime.datetime.fromisoformat(self.time)

        def dump(self):
            return {"remind": (self.uid, self.cid, self.time.isoformat(), self.text, self.dm, self.recurring)}

        def get_recurring(self):
            if self.recurring:
                if self.recurring[0] == 'y':
                    return datetime.datetime(year=self.time.year + self.recurring[1],
                                             month=self.time.month,
                                             day=self.time.day,
                                             hour=self.time.hour,
                                             minute=self.time.minute,
                                             second=self.time.second)
                elif self.recurring[0] == 'm':
                    month = self.time.month + self.recurring[1] - 1
                    year = self.time.year + month // 12
                    month = month % 12 + 1
                    day = min(self.time.day, self._mdays[month - 1])
                    return datetime.datetime(year=year,
                                             month=month,
                                             day=day,
                                             hour=self.time.hour,
                                             minute=self.time.minute,
                                             second=self.time.second)
                else:
                    _d = datetime.timedelta(days=self.recurring[1])
                    return self.time + _d
            else:
                return False

    async def activate(self):
        self.storage = self.config_manager.get_plugin_config_file("reminders.json",
                                                                  json_load_args={
                                                                      'object_hook': lambda x: self.Rem(
                                                                          *x["remind"]) if "remind" in x else x
                                                                  },
                                                                  json_save_args={'default': lambda x: x.dump()})
        for guild in self.client.guilds:
            if str(guild.id) not in self.storage:
                self.storage[str(guild.id)] = []

        self.run_timer = True
        loop = asyncio.new_event_loop()
        t_loop = asyncio.get_event_loop()
        self.timer = threading.Thread(target=self.start_timer, args=[loop, t_loop])
        self.timer.setDaemon(True)
        self.timer.start()

    async def deactivate(self):
        self.run_timer = False

    @Command("remind",
             syntax="(message) [-d/--delay DD//@HH:MM:SS] [-t/--time DD/MM/YYYY@HH:MM:SS] [-p/--private] ["
                    "-r/--recurring y/m/d###]",
             doc="Store a reminder for the future. Message needs to come before the time options.\n"
                 "-d/--delay    : remind after a set delay. Does NOT support months or years due to varying time.\n"
                 "-t/--time     : remind on a given date. Date must be in the future.\n"
                 "-r/--recurring: repeat the reminder every day/month/year, format is d/m/y## with ## being an "
                 "integer number."
                 "Time format   : DD/MM/YYYY@hh:mm:ss. Numbers may be skipped, but a date needs two slashes and a "
                 "time "
                 "needs two colons, with some non-whitespace symbol separating the two.\n"
                 "Valid input includes '23//', ':30:' and '1/1/@12::'",
             category="reminder")
    async def _remind(self, msg: Message):
        parser = RSArgumentParser()
        parser.add_argument("command")
        parser.add_argument("reminder", default=[], nargs="*")
        parser.add_argument("-d", "--delay", default='')
        parser.add_argument("-t", "--time", default='')
        parser.add_argument("-p", "--private", action='store_true')
        parser.add_argument("-r", "--recurring", default='')

        args = parser.parse_args(shlex.split(msg.clean_content))

        if not (args['time'] or args['delay']):
            raise CommandSyntaxError("Expected a reminder time")
        else:
            time = args['time'] if args['time'] else args['delay']

        utcnow = datetime.datetime.utcnow()

        # just a way to default skipped values to "today"
        _t = {
            'D': 0 if args['delay'] else utcnow.day,
            'M': utcnow.month,
            'Y': utcnow.year,
            'h': 0,
            'm': 0,
            's': 0
        }

        time = {k: int(v or _t[k]) for k, v in self.pattern.match(time).groupdict(0).items()}

        if args['private']:
            try:
                await msg.delete()
            except Exception:
                pass

        if args['recurring'] and args['recurring'][0].lower() in 'ymd':
            try:
                _recur = (args['recurring'][0].lower(), int(args['recurring'][1:]))
                if _recur[1] <= 0:
                    raise ValueError
            except ValueError:
                raise CommandSyntaxError('invalid recurring time format')
        else:
            _recur = []

        try:
            if args['time']:
                time = datetime.datetime(max(time['Y'], 1), max(time['M'], 1), max(time['D'], 1),
                                         time['h'], time['m'], time['s'])
            else:
                time = utcnow + datetime.timedelta(time['D'], hours=time['h'], minutes=time['m'], seconds=time['s'])
        except ValueError as e:
            raise CommandSyntaxError(e)

        if time < utcnow:
            raise CommandSyntaxError("Can not alter past")

        self.storage[str(msg.guild.id)].append(self.Rem(msg.author.id,
                                                        msg.channel.id,
                                                        time,
                                                        ' '.join(args['reminder']),
                                                        args['private'],
                                                        _recur))
        self.storage.save()
        await respond(msg, f"**AFFIRMATIVE: reminder set for {time.strftime('%Y-%m-%d @ %H:%M:%S')} UTC.**")

    @Command("remindlist",
             syntax="[-/del/delete index]",
             doc="Prints out a list of all reminders of the user.\nUse del argument and an index from said list to "
                 "remove reminders.",
             category="reminder")
    async def _remindlist(self, msg: Message):
        uid = msg.author.id
        gid = str(msg.guild.id)
        args = msg.clean_content.split(None, 2)
        r_list = [r for r in self.storage[gid] if r.uid == uid]
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
                self.storage[gid] = [x for x in self.storage[gid] if x != r_list[index]]
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
            save_flag = False
            for guild in filter(lambda x: str(x.id) in self.storage, self.client.guilds):
                gid = str(guild.id)
                for reminder in filter(lambda x: x.time <= dtnow, self.storage[gid]):
                    save_flag = True
                    try:
                        channel = None if reminder.dm else self.channel_manager.get_channel(guild, "reminders")
                    except ChannelNotFoundError:
                        channel = guild.get_channel(reminder.cid)

                    if channel:
                        asyncio.ensure_future(channel.send(f"**<@{reminder.uid}>:**\n{reminder.text}"), loop=t_loop)
                    else:
                        usr = guild.get_member(reminder.uid)
                        if usr:
                            asyncio.ensure_future(usr.send(f"**Reminder from {guild}:**\n{reminder.text}"),
                                                  loop=t_loop)

                    if reminder.recurring:
                        self.storage[gid].append(self.Rem(
                                reminder.uid,
                                reminder.cid,
                                reminder.get_recurring(),
                                reminder.text,
                                reminder.dm,
                                reminder.recurring
                        ))
                # it's easier to create a new list where everything fits rather than delete from old
                self.storage[gid] = [x for x in self.storage[gid] if x.time > dtnow]
            if save_flag:
                self.storage.save()
