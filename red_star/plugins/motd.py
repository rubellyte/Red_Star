from __future__ import annotations
import datetime
import json
import discord.utils
from discord.ext import tasks
from random import choice
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import CommandSyntaxError, ChannelNotFoundError, DataCarrier
from red_star.rs_utils import respond, RSArgumentParser
from red_star.command_dispatcher import Command

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import discord


class MOTD(BasePlugin):
    name = "motd"
    version = "1.4"
    author = "medeor413"
    description = "A plugin for flexibly displaying messages at date change."
    default_config = {
        "default": {
            "motd_file": "motds.json"
        }
    }
    channel_types = {"motd"}

    valid_months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    month_names_to_abbr = {"january": "jan", "february": "feb", "march": "mar", "april": "apr", "may": "may",
                           "june": "jun", "july": "jul", "august": "aug", "september": "sep", "october": "oct",
                           "november": "nov", "december": "dec"}
    valid_weekdays = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    valid_days = {str(i) for i in range(1, 32)}
    valid_month_weeks = {"week-1", "week-2", "week-3", "week-4", "week-5", "week-6", "last-week"}
    valid_dates = set(valid_months) | valid_month_weeks | valid_weekdays | valid_days

    async def activate(self):
        self._port_old_storage()
        self._display_motd.start()

    def _port_old_storage(self):
        motds_folder = self.client.storage_dir / "motds"
        if "motd_file" not in self.config:
            return
        old_motd_file = motds_folder / self.config["motd_file"]
        if old_motd_file.exists():
            with old_motd_file.open() as fp:
                old_motds = json.load(fp)
            self.storage["motds"] = old_motds
            del self.config["motd_file"]
            self.config_manager.save_config()
            self.storage_file.save()
            self.storage_file.load()
            self.logger.info("Ported MotD file to new storage system.")

    @tasks.loop(time=discord.utils.utcnow().replace(hour=0, minute=0, second=0).timetz())
    async def _display_motd(self, date: datetime.date):
        try:
            chan = self.channel_manager.get_channel("motd")
        except ChannelNotFoundError:
            return
        try:
            lines = self._get_motds(date)
        except DataCarrier as dc:
            lines = dc.data
        try:
            line = choice(lines)
            line = date.strftime(line)
        except IndexError:
            return
        except ValueError:
            line = choice(lines)
        await chan.send(line)

    def _get_motds(self, date: datetime.date | None, options: dict = None, valid: set = None):
        if options is None:
            options = self.storage["motds"]
        if not valid:
            valid = {date.strftime("%b").lower(), date.strftime("%a").lower(),
                     str(date.day), "week-" + str(week_of_month(date))}
            if is_last_week_of_month(date):
                valid.add("last-week")
        results = []
        if options.get("holiday", False):
            raise DataCarrier(options["options"])
        for k, v in options.items():
            if k.lower() in valid:
                results.extend(self._get_motds(date, options=v, valid=valid))
        if "options" in options:
            results.extend(options["options"])
        return results

    @Command("AddMotD",
             doc="Adds a MotD message. Each element of the path must match the date for an MotD to display.\n"
                 "Use --holiday to declare a holiday; when a holiday MotD list is checked, it will only use MotDs "
                 "from that specific list.",
             perms={"manage_guild"},
             category="bot_management",
             syntax="[-h/--holiday] (/path/of/date) (message)")
    async def _add_motd(self, msg: discord.Message):
        holiday = False
        try:
            path, new_motd = msg.clean_content.split(None, 2)[1:]
            self.logger.debug(f"New MOTD for {path}: {new_motd}")
            if path in ("-h", "--holiday"):
                holiday = True
                path, new_motd = new_motd.split(None, 1)
        except ValueError:
            raise CommandSyntaxError("Not enough arguments.")

        path = [self.month_names_to_abbr.get(x, x) for x in path.lower().split("/") if x]
        if not all(x in self.valid_dates for x in path):
            invalid = ", ".join(x for x in path if x not in self.valid_dates)
            raise CommandSyntaxError(f"The following path identifiers are invalid: `{invalid}`")
        motd_path = self.storage["motds"]
        for k in path:
            motd_path = motd_path.setdefault(k, {})
        motd_path.setdefault("options", []).append(new_motd)
        if holiday:
            motd_path["holiday"] = True

        self.storage_file.save()
        await respond(msg, f"**ANALYSIS: MotD for {'/'.join(path)} added successfully"
                           f"{' and set as holiday' if holiday else ''}.**")

    @Command("TestMotDs",
             doc="Used for testing MOTD lines. If a date is not provided, today's date will be used. Month may be "
                 "specified by full English name, three-letter abbreviation, or number. If --dt is used, "
                 "don't use any other flags.",
             perms={"manage_guild"},
             category="debug",
             syntax="[-d/--day number] [-wd/--weekday weekday] [-mw/--monthweek week-x] [-m/--month month] "
                    "OR [-dt/--dt ISO-format date]")
    async def _test_motd(self, msg: discord.Message):
        today = discord.utils.utcnow()
        parser = RSArgumentParser()
        parser.add_argument("-d",  "--day", default=str(today.day))
        parser.add_argument("-wd", "--weekday", default=today.strftime("%a").lower())
        parser.add_argument("-mw", "--monthweek", default="week-" + str(week_of_month(today)))
        parser.add_argument("-m",  "--month", default=today.strftime("%b").lower(), type=self.coerce_month_value)
        parser.add_argument("-dt", "--date", default=None, type=datetime.datetime.fromisoformat)
        args = parser.parse_args(msg.clean_content.lower().split()[1:])

        try:
            if args.date:
                lines = self._get_motds(args.date)
            else:
                if args.month not in self.valid_months \
                        or args.day not in self.valid_days \
                        or args.weekday not in self.valid_weekdays \
                        or args.monthweek not in self.valid_month_weeks:
                    raise CommandSyntaxError("One of the arguments is not valid.")
                lines = self._get_motds(None, valid={args.month, args.day, args.weekday, args.monthweek})
        except DataCarrier as dc:
            lines = dc.data
        lines = "\n".join(lines)
        if not lines:
            lines = "None."
        await respond(msg, f"```\n{lines}```")

    def coerce_month_value(self, month):
        if month in self.valid_months:
            return month
        elif month in self.month_names_to_abbr:
            return self.month_names_to_abbr[month]
        elif month.isdigit() and 1 <= int(month) <= 12:
            return self.valid_months[int(month) - 1]
        raise ValueError(f"{month} is not a valid month.")


def week_of_month(date: datetime.date):
    first_of_month = date.replace(day=1).weekday()
    if first_of_month == 6:
        first_of_month -= 7
    return (date.day + first_of_month) // 7 + 1
    

def is_last_week_of_month(date: datetime.date):
    last_of_month = date.replace(month=(date.month % 12 + 1), day=1) - datetime.timedelta(days=1)
    return week_of_month(date) == week_of_month(last_of_month)
