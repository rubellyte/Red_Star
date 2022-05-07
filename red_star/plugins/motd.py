from __future__ import annotations
import datetime
import json
import discord.utils
from random import choice
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import CommandSyntaxError, ChannelNotFoundError, DataCarrier
from red_star.rs_utils import respond, get_guild_config, RSArgumentParser
from red_star.command_dispatcher import Command

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import discord


class MOTD(BasePlugin):
    name = "motd"
    version = "1.3"
    author = "medeor413"
    description = "A plugin for flexibly displaying messages at date change."
    default_config = {
        "default": {
            "motd_file": "motds.json"
        }
    }
    channel_types = {"motd"}

    motds: dict
    last_run: int

    valid_months = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"}
    valid_weekdays = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    valid_days = {str(i) for i in range(1, 32)}
    valid_monthweeks = {"week-1", "week-2", "week-3", "week-4", "week-5", "week-6", "last-week"}
    valid_dates = valid_months | valid_monthweeks | valid_weekdays | valid_days

    async def activate(self):
        self.motds = {}
        self.motds_folder = self.client.storage_dir / "motds"
        self.motds_folder.mkdir(parents=True, exist_ok=True)
        self.last_run = discord.utils.utcnow().day
        for guild in self.client.guilds:
            motd_file = get_guild_config(self, str(guild.id), "motd_file")
            if motd_file not in self.motds:
                try:
                    file_path = self.motds_folder / motd_file
                    with file_path.open() as fp:
                        self.motds[motd_file] = json.load(fp)
                except FileNotFoundError:
                    self.logger.error(f"MotD file {motd_file} for guild {guild.name} not found! Skipping...")
                    continue
                except json.decoder.JSONDecodeError:
                    self.logger.error(f"MotD file {motd_file} for guild {guild.name} couldn't be decoded! Skipping...")
                    continue

    async def on_global_tick(self, time: datetime.datetime, _):
        if time.day != self.last_run:
            self.last_run = time.day
            await self._display_motd(time.date())

    async def _display_motd(self, date: datetime.date):
        for guild in self.client.guilds:
            try:
                chan = self.channel_manager.get_channel(guild, "motd")
                motd_path = get_guild_config(self, str(guild.id), "motd_file")
                motds = self.motds[motd_path]
            except ChannelNotFoundError:
                continue
            try:
                lines = self._get_motds(motds, date)
            except DataCarrier as dc:
                lines = dc.data
            try:
                line = choice(lines)
                line = date.strftime(line)
            except IndexError:
                continue
            except ValueError:
                line = choice(lines)
            await chan.send(line)

    def _get_motds(self, options: dict, date: datetime.date | None, valid: set = None):
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
                results.extend(self._get_motds(v, date, valid=valid))
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
    async def _addmotd(self, msg: discord.Message):
        holiday = False
        try:
            path, new_motd = msg.clean_content.split(None, 2)[1:]
            self.logger.debug(f"New MOTD for {path}: {new_motd}")
            if path in ("-h", "--holiday"):
                holiday = True
                path, new_motd = new_motd.split(None, 1)
        except ValueError:
            raise CommandSyntaxError("Not enough arguments.")
        motd_file = get_guild_config(self, str(msg.guild.id), "motd_file")
        motds = self.motds[motd_file]
        motd_file = self.motds_folder / motd_file

        path = [x for x in path.lower().split("/") if x]
        if not all(x in self.valid_dates for x in path):
            invalid = ", ".join(x for x in path if x not in self.valid_dates)
            raise CommandSyntaxError(f"The following path identifiers are invalid: `{invalid}`")
        motd_path = motds
        for k in path:
            motd_path = motd_path.setdefault(k, {})
        motd_path.setdefault("options", []).append(new_motd)
        if holiday:
            motd_path["holiday"] = True

        with motd_file.open("w", encoding="utf8") as fd:
            json.dump(motds, fd, indent=2, ensure_ascii=False)
        await respond(msg, f"**ANALYSIS: MotD for {'/'.join(path)} added successfully"
                           f"{' and set as holiday' if holiday else ''}.**")

    @Command("TestMotDs",
             doc="Used for testing MOTD lines. If a date is not provided, today's date will be used.",
             perms={"manage_guild"},
             category="debug",
             syntax="[-d/--day number] [-wd/--weekday weekday] [-mw/--monthweek week-x] [-m/--month month]"
                    "OR [-dt/--dt ISO-format date]")
    async def _testmotd(self, msg: discord.Message):
        today = datetime.datetime.now()
        parser = RSArgumentParser()
        parser.add_argument("-d",  "--day", default=str(today.day))
        parser.add_argument("-wd", "--weekday", default=today.strftime("%a").lower())
        parser.add_argument("-mw", "--monthweek", default="week-" + str(week_of_month(today)))
        parser.add_argument("-m",  "--month", default=today.strftime("%b").lower())
        parser.add_argument("-dt", "--date", default=None, type=datetime.datetime.fromisoformat)
        args = parser.parse_args(msg.clean_content.split()[1:])
        motd_path = get_guild_config(self, str(msg.guild.id), "motd_file")
        motds = self.motds[motd_path]
        try:
            if args.date:
                lines = self._get_motds(motds, args.date)
            else:
                if args.month not in self.valid_months \
                        or args.day not in self.valid_days \
                        or args.weekday not in self.valid_weekdays \
                        or args.monthweek not in self.valid_monthweeks:
                    raise CommandSyntaxError("One of the arguments is not valid.")
                lines = self._get_motds(motds, None, valid={args.month, args.day, args.weekday, args.monthweek})
        except DataCarrier as dc:
            lines = dc.data
        lines = "\n".join(lines)
        if not lines:
            lines = "None."
        await respond(msg, f"```\n{lines}```")


def week_of_month(date: datetime.date):
    first_of_month = date.replace(day=1).weekday()
    if first_of_month == 6:
        first_of_month -= 7
    return (date.day + first_of_month) // 7 + 1
    

def is_last_week_of_month(date: datetime.date):
    last_of_month = date.replace(month=(date.month % 12 + 1), day=1) - datetime.timedelta(days=1)
    return week_of_month(date) == week_of_month(last_of_month)
