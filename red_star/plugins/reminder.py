from red_star.plugin_manager import BasePlugin
from red_star.command_dispatcher import Command
from red_star.rs_utils import respond, RSArgumentParser, split_output
from red_star.rs_errors import CommandSyntaxError, ChannelNotFoundError
import datetime
import shlex
import re
from discord import Message, HTTPException
from dataclasses import dataclass
from asyncio import create_task


class ReminderPlugin(BasePlugin):
    name = "reminder"
    version = "1.0"
    author = "GTG3000"
    description = "A plugin for setting messages that the bot will send you at a configurable time."

    run_timer = False
    timer = None
    reminder_file_path = None

    # Searches for a DD/MM/YYYY@hh:mm:ss pattern.
    # All the options are optional (searching for 0 to 2/4 digits), and are in named groups for ease of use of results.
    # It *has* to be formatted // for date and :: for time though.
    # The bit between the two just has to be non-numeric, but since shlex kills whitespace it also has to be a thing.
    pattern = re.compile(
        r"(?:(?P<D>\d{0,2})/(?P<M>\d{0,2})/(?P<Y>\d{0,4}))?[^\d]*(?:(?P<h>\d{0,2}):(?P<m>\d{0,2}):(?P<s>\d{0,2}))?")

    @dataclass
    class Reminder:
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

        def as_dict(self):
            return {"__classhint__": "reminder",
                    "reminder": (self.uid, self.cid, self.time.isoformat(), self.text, self.dm, self.recurring)}

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
        def _load(cls: ReminderPlugin, obj: dict):
            if obj.pop('__classhint__', None) == 'reminder':
                return cls.Reminder(*obj['reminder'])
            else:
                return obj

        self.storage = self.config_manager.get_plugin_config_file(
                "reminders.json", json_load_args={'object_hook': lambda o: _load(self, o)},
                json_save_args={'default': lambda x: x.as_dict()})
        for guild in self.client.guilds:
            if str(guild.id) not in self.storage:
                self.storage[str(guild.id)] = []

    @Command("Remind",
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
        default_time = {
            'D': 0 if args['delay'] else utcnow.day,
            'M': utcnow.month,
            'Y': utcnow.year,
            'h': 0,
            'm': 0,
            's': 0
        }

        time = {k: int(v or default_time[k]) for k, v in self.pattern.match(time).groupdict().items()}

        if args['private']:
            try:
                await msg.delete()
            except HTTPException:
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
            raise CommandSyntaxError("Red Star cannot presently alter the past.")

        self.storage[str(msg.guild.id)].append(self.Reminder(msg.author.id, msg.channel.id, time,
                                                             ' '.join(args['reminder']), args['private'], _recur))
        self.storage.save()
        await respond(msg, f"**AFFIRMATIVE: reminder set for {time.strftime('%Y-%m-%d @ %H:%M:%S')} UTC.**")

    @Command("RemindList",
             syntax="[-/del/delete index]",
             doc="Prints out a list of all reminders of the user.\nUse del argument and an index from said list to "
                 "remove reminders.",
             category="reminder")
    async def _remindlist(self, msg: Message):
        uid = msg.author.id
        gid = str(msg.guild.id)
        args = msg.clean_content.split(None, 2)
        reminder_list = [r for r in self.storage[gid] if r.uid == uid]
        reminder_str_list = [f"{i:2}|{r.time.strftime('%Y-%m-%d @ %H:%M:%S')} : {r.text:50} in "
                             f"{'Direct Messages' if r.dm else msg.guild.get_channel(r.cid)}"
                             for i, r in enumerate(reminder_list)]
        if len(args) == 1:
            await split_output(msg, "**Following reminders found:**", reminder_str_list)
        elif len(args) == 3 and args[1].lower() in ("del", "-", "delete"):
            try:
                index = int(args[2])
            except ValueError:
                raise CommandSyntaxError("Non-integer syntax provided")
            if 0 <= index < len(reminder_list):
                self.storage[gid] = [x for x in self.storage[gid] if x != reminder_list[index]]
                await respond(msg, "**AFFIRMATIVE. Reminder removed.**")
            else:
                raise CommandSyntaxError("Index out of range")
        else:
            raise CommandSyntaxError("No arguments or del/-/delete index required")

    async def on_global_tick(self, now, _):
        save_flag = False
        for guild in filter(lambda x: str(x.id) in self.storage, self.client.guilds):
            gid = str(guild.id)
            for reminder in filter(lambda x: x.time <= now, self.storage[gid]):
                save_flag = True
                try:
                    channel = None if reminder.dm else self.channel_manager.get_channel(guild, "reminders")
                except ChannelNotFoundError:
                    channel = guild.get_channel(reminder.cid)

                if channel:
                    create_task(channel.send(f"**<@{reminder.uid}>:**\n{reminder.text}"))
                else:
                    usr = guild.get_member(reminder.uid)
                    if usr:
                        create_task(usr.send(f"**Reminder from {guild}:**\n{reminder.text}"))

                if reminder.recurring:
                    self.storage[gid].append(self.Reminder(reminder.uid, reminder.cid, reminder.get_recurring(),
                                                           reminder.text, reminder.dm, reminder.recurring))
            # it's easier to create a new list where everything fits rather than delete from old
            self.storage[gid] = [x for x in self.storage[gid] if x.time > now]
        if save_flag:
            self.storage.save()
