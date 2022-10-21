from red_star.plugin_manager import BasePlugin
from red_star.command_dispatcher import Command
from red_star.rs_utils import respond, RSArgumentParser, group_items
from red_star.rs_errors import CommandSyntaxError, ChannelNotFoundError
import datetime
import shlex
import re
import discord
import discord.utils
from discord.ext import tasks
from dataclasses import dataclass
from asyncio import create_task

RECUR_DECODE = {
    "h": ('hour', 'hours'),
    "d": ('day', 'days'),
    "m": ('month', 'months'),
    "y": ('year', 'years')
}


class ReminderPlugin(BasePlugin):
    name = "reminder"
    version = "1.2"
    author = "GTG3000"
    description = "A plugin for setting messages that the bot will send you at a configurable time."
    channel_types = {"reminders"}

    run_timer = False
    timer = None
    reminder_file_path = None

    # Searches for a DD/MM/YYYY@hh:mm:ss pattern.
    # All the options are optional (searching for 0 to 2/4 digits), and are in named groups for ease of use of results.
    # It *has* to be formatted // for date and :: for time though.
    # The bit between the two just has to be non-numeric, but since shlex kills whitespace it also has to be a thing.
    pattern = re.compile(
        r"(?:(?P<D>\d{0,2})/(?P<M>\d{0,2})/(?P<Y>\d{0,4}))?[^\d:/]*(?:(?P<h>\d{0,2}):(?P<m>\d{0,2}):(?P<s>\d{0,2}))?")

    @dataclass
    class Reminder:
        uid: int
        cid: int
        time: datetime.datetime
        text: str
        dm: bool
        recurring: list

        # number of days in each month, for checking
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
                elif self.recurring[0] == 'd':
                    return self.time + datetime.timedelta(days=self.recurring[1])
                else:
                    return self.time + datetime.timedelta(hours=self.recurring[1])
            else:
                return False

    async def activate(self):
        def _load(cls: ReminderPlugin, obj: dict):
            if obj.pop('__classhint__', None) == 'reminder':
                return cls.Reminder(*obj['reminder'])
            else:
                return obj

        self.storage = self.config_manager.get_plugin_config_file(
                "reminders.json", self.guild, json_load_args={'object_hook': lambda o: _load(self, o)},
                json_save_args={'default': lambda x: x.as_dict()})

        if isinstance(self.storage, list):
            # Convert old
            self.config_manager.plugin_config_files["reminders.json"][str(self.guild.id)] = {"reminders": self.storage}

        self.storage.setdefault("reminders", [])

    @Command("Remind",
             syntax="(message) [-d/--delay DD//@HH:MM:SS] [-t/--time DD/MM/YYYY@HH:MM:SS] [-p/--private] ["
                    "-r/--recurring y/m/d###]",
             doc="Store a reminder for the future. Message needs to come before the time options.\n"
                 "-d/--delay    : remind after a set delay. Does NOT support months or years due to varying time.\n"
                 "-t/--time     : remind on a given date. Date must be in the future.\n"
                 "-r/--recurring: repeat the reminder every day/month/year, format is d/m/y## with ## being an "
                 "integer number.\n"
                 "-e/--everyone : mention everyone with the reminder. Requires user having the permission.\n"
                 "-h/--here     : mention here with the reminder. Requires user having the permission.\n"
                 "Time format   : DD/MM/YYYY@hh:mm:ss. Numbers may be skipped, but a date needs two slashes and a "
                 "time needs two colons, with some non-whitespace symbol separating the two.\n"
                 "Valid input includes '23//', ':30:' and '1/1/@12::'",
             category="reminder",
             run_anywhere=True,
             optional_perms={"mention_everyone": {"mention_everyone"}})
    async def _remind(self, msg: discord.Message):
        parser = RSArgumentParser()
        parser.add_argument("command")
        parser.add_argument("reminder", default=[], nargs="*")
        parser.add_argument("-d", "--delay", default='')
        parser.add_argument("-t", "--time", default='')
        parser.add_argument("-p", "--private", action='store_true')
        parser.add_argument("-e", "--everyone", action='store_true')
        parser.add_argument("-h", "--here", action='store_true')
        parser.add_argument("-r", "--recurring", default='')

        try:
            args = shlex.split(msg.content)
        except ValueError as e:
            self.logger.warning("Unable to split {data.content}. {e}")
            raise CommandSyntaxError(e)

        args = parser.parse_args(args)

        if not (args['time'] or args['delay']):
            raise CommandSyntaxError("Expected a reminder time")
        else:
            time = args['time'] if args['time'] else args['delay']

        utcnow = discord.utils.utcnow()

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
            args['everyone'] = args['here'] = False
            try:
                await msg.delete()
            except discord.HTTPException:
                pass

        # just because the bot can mention everyone, doesn't mean that anyone with command access should be able to.
        if self._remind.perms.check_optional_permissions("mention_everyone", msg.author, msg.channel) and \
                (args['everyone'] or args['here']):
            args['reminder'].insert(0, "@everyone:" if args['everyone'] else "@here:")

        if args['recurring'] and args['recurring'][0].lower() in 'ymdh':
            try:
                _recur = (args['recurring'][0].lower(), int(args['recurring'][1:]))
                # TODO: format this
                _recurstr = f" Recurring every {RECUR_DECODE[_recur[0]][0] if _recur[1] == 1 else str(_recur[1]) + ' ' + RECUR_DECODE[_recur[0]][1]}."
                if _recur[1] <= 0:
                    raise ValueError
            except ValueError:
                raise CommandSyntaxError('invalid recurring time format')
        else:
            _recur = []
            _recurstr = ""

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

        self.storage["reminders"].append(self.Reminder(msg.author.id, msg.channel.id, time,
                                                       ' '.join(args['reminder']), args['private'], _recur))

        await respond(msg, f"**AFFIRMATIVE: reminder set for {time.strftime('%Y-%m-%d @ %H:%M:%S')} UTC.{_recurstr}**")

    @Command("RemindList",
             syntax="[-/del/delete index]",
             doc="Prints out a list of all reminders of the user.\nUse del argument and an index from said list to "
                 "remove reminders.",
             category="reminder")
    async def _remindlist(self, msg: discord.Message):
        uid = msg.author.id
        gid = str(msg.guild.id)
        args = msg.clean_content.split(None, 2)
        reminder_list = [r for r in self.storage["reminders"] if r.uid == uid]

        if len(args) == 1:
            for split_msg in group_items((f"{i:2}|{r.time.strftime('%Y-%m-%d @ %H:%M:%S')} : {r.text:50} in "
                                          f"{'Direct Messages' if r.dm else msg.guild.get_channel(r.cid)}"
                                          for i, r in enumerate(reminder_list)),
                                         message="**Following reminders found:**"):
                await respond(msg, split_msg)
        elif len(args) == 3 and args[1].lower() in ("del", "-", "delete"):
            try:
                index = int(args[2])
            except ValueError:
                raise CommandSyntaxError("Non-integer index provided")
            if 0 <= index < len(reminder_list):
                self.storage["reminders"].remove(reminder_list[index])
                await respond(msg, "**AFFIRMATIVE. Reminder removed.**")
            else:
                raise CommandSyntaxError("Index out of range")
        else:
            raise CommandSyntaxError("No arguments or del/-/delete index required")

    @Command("RemindListAll",
             syntax="[-/del/delete index]",
             doc="Prints out a list of all reminders.\nUse del argument and an index from said list to "
                 "remove reminders.",
             category="reminder",
             perms={"manage_messages"})
    async def _remindlistall(self, msg: discord.Message):
        gid = str(msg.guild.id)
        args = msg.clean_content.split(None, 2)

        users = {r.uid: str(msg.guild.get_member(r.uid)) for r in self.storage["reminders"]}

        if len(args) == 1:
            reminders = (f"{i:2}|{users[r.uid]:^32}|{r.time.strftime('%Y-%m-%d @ %H:%M:%S')} : "
                         f"{r.text[:50]:50} in {'Direct Messages' if r.dm else msg.guild.get_channel(r.cid)}"
                         for i, r in enumerate(self.storage["reminders"]))
            for split_msg in group_items(reminders, message="**Following reminders found:**"):
                await respond(msg, split_msg)
        if len(args) == 3 and args[1].lower() in ("del", "-", "delete"):
            try:
                index = int(args[2])
            except ValueError:
                raise CommandSyntaxError("Non-integer syntax provided")
            if 0 <= index < len(self.storage["reminders"]):
                del self.storage["reminders"][index]
                await respond(msg, "**AFFIRMATIVE. Reminder removed.**")
            else:
                raise CommandSyntaxError("Index out of range")
        else:
            raise CommandSyntaxError

    @tasks.loop(minutes=1)
    async def check_reminders(self):
        now = discord.utils.utcnow()
        for reminder in [x for x in self.storage["reminders"] if x.time <= now]:
            try:
                if reminder.dm:
                    channel = self.guild.get_member(reminder.uid)
                else:
                    channel = self.channel_manager.get_channel("reminders")
            except ChannelNotFoundError:
                channel = self.guild.get_channel(reminder.cid)

            await channel.send(f"**<@{reminder.uid}>:**\n{reminder.text}")
            self.storage["reminders"].remove(reminder)

            if reminder.recurring:
                self.storage["reminders"].append(self.Reminder(reminder.uid, reminder.cid, reminder.get_recurring(),
                                                               reminder.text, reminder.dm, reminder.recurring))
