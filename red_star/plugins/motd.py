import asyncio
import datetime
import json
from random import choice
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import CommandSyntaxError, ChannelNotFoundError
from red_star.rs_utils import respond, get_guild_config
from red_star.command_dispatcher import Command


class MOTD(BasePlugin):
    name = "motd"
    default_config = {
        "default": {
            "motd_file": "motds.json"
        }
    }

    async def activate(self):
        self.run_timer = True
        self.motds = {}
        self.motds_folder = self.client.storage_dir / "motds"
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
        asyncio.ensure_future(self._run_motd())
        self.valid_months = {
            "January", "February", "March", "April", "May", "June", "July",
            "August", "September", "October", "November", "December", "Any"
        }
        self.valid_days = {
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Any",
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16",
            "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31"
        }

    async def deactivate(self):
        self.run_timer = False

    async def _run_motd(self):
        now = datetime.datetime.utcnow().time()
        await asyncio.sleep(60 - now.second)
        while self.run_timer:
            now = datetime.datetime.utcnow().time()
            if now.hour is 0 and now.minute is 0:
                await self._display_motd()
            await asyncio.sleep(60 - now.second)

    async def _display_motd(self):
        today = datetime.date.today()
        month = today.strftime("%B")
        day = str(today.day)
        weekday = today.strftime("%A")
        for guild in self.client.guilds:
            try:
                chan = self.channel_manager.get_channel(guild, "motd")
                motd_path = get_guild_config(self, str(guild.id), "motd_file")
                motds = self.motds[motd_path]
            except ChannelNotFoundError:
                continue
            holiday_lines = self._get_holiday(motds, month, day, weekday)
            if holiday_lines:
                    line = choice(holiday_lines)
                    try:
                        line = today.strftime(line)
                    except ValueError:
                        pass
                    await chan.send(line)
            else:
                lines = []
                lines += motds.get("Any", {}).get("Any", [])
                lines += motds.get("Any", {}).get(day, [])
                lines += motds.get("Any", {}).get(weekday, [])
                lines += motds.get(month, {}).get("Any", [])
                lines += motds.get(month, {}).get(day, [])
                lines += motds.get(month, {}).get(weekday, [])
                try:
                    line = choice(lines)
                    line = today.strftime(line)
                except IndexError:
                    continue
                except ValueError:
                    pass
                # noinspection PyUnboundLocalVariable
                await chan.send(line)

    @staticmethod
    def _get_holiday(motds, month, day, weekday):
        holidays = motds.get("holidays", [])
        if f"{month}/{day}" in holidays:
            return motds[month][day]
        elif f"{month}/{weekday}" in holidays:
            return motds[month][weekday]
        elif f"{month}/Any" in holidays:
            return motds[month]["Any"]
        elif f"Any/{day}" in holidays:
            return motds["Any"][day]
        elif f"Any/{weekday}" in holidays:
            return motds["Any"][weekday]
        else:
            return

    @Command("AddMotD",
             doc="Adds a MotD message.",
             perms={"manage_guild"},
             category="bot_management",
             syntax="(month/Any) (day/weekday/Any) (message)")
    async def _addmotd(self, msg):
        args = msg.clean_content.split(" ")[1:]
        try:
            month = args[0].capitalize()
            day = args[1].capitalize()
            newmotd = " ".join(args[2:])
        except IndexError:
            raise CommandSyntaxError
        if month not in self.valid_months or day not in self.valid_days:
            raise CommandSyntaxError("Month or day is invalid. Please use full names.")
        try:
            motd_file = get_guild_config(self, str(msg.guild.id), "motd_file")
            motds = self.motds[motd_file]
            motd_file = self.motds_folder / motd_file
            if month not in motds:
                motds[month] = {}
            if day not in motds[month]:
                motds[month][day] = []
            motds[month][day].append(newmotd)
            with motd_file.open("w", encoding="utf8") as fd:
                json.dump(motds, fd, indent=2, ensure_ascii=False)
            await respond(msg, f"**ANALYSIS: MotD for {month} {day} added successfully.**")
        except KeyError:
            raise CommandSyntaxError("Month or day is invalid. Please use full names.")

    @Command("AddHoliday",
             doc="Adds a holiday. Holidays do not draw from the \"any-day\" MotD pools.",
             perms={"manage_guild"},
             category="bot_management",
             syntax="(month/Any) (day/weekday/Any)")
    async def _addholiday(self, msg):
        args = msg.clean_content.split()[1:]
        try:
            month = args[0].capitalize()
            day = args[1].capitalize()
        except IndexError:
            raise CommandSyntaxError
        if month not in self.valid_months or day not in self.valid_days:
            raise CommandSyntaxError("Month or day is invalid. Please use full names.")
        holidaystr = month + "/" + day
        motd_file = get_guild_config(self, str(msg.guild.id), "motd_file")
        motds = self.motds[motd_file]
        motd_file = self.motds_folder / motd_file
        if holidaystr not in motds["holidays"]:
            motds["holidays"].append(holidaystr)
            with motd_file.open("w", encoding="utf8") as fd:
                json.dump(motds, fd, indent=2, ensure_ascii=False)
            await respond(msg, f"**ANALYSIS: Holiday {holidaystr} added successfully.**")
        else:
            await respond(msg, f"**ANALYSIS: {holidaystr} is already a holiday.**")

    @Command("TestMotDs",
             doc="Used for testing MOTD lines.",
             perms={"manage_guild"},
             category="debug",
             syntax="(month/Any) (day/Any) (weekday/Any)")
    async def _testmotd(self, msg):
        try:
            args = msg.clean_content.split()[1:]
            month = args[0].capitalize()
            day = args[1].capitalize()
            weekday = args[2].capitalize()
            if month not in self.valid_months or day not in self.valid_days or weekday not in self.valid_days:
                raise CommandSyntaxError("One of the arguments is not valid.")
            month = "" if month == "Any" else month
            day = "" if day == "Any" else day
            weekday = "" if weekday == "Any" else weekday
        except IndexError:
            raise CommandSyntaxError("Missing arguments.")
        motd_path = get_guild_config(self, str(msg.guild.id), "motd_file")
        motds = self.motds[motd_path]
        holiday_lines = self._get_holiday(motds, month, day, weekday)
        if holiday_lines:
            await respond(msg, "\n".join(holiday_lines))
        else:
            lines = []
            lines += motds.get("Any", {}).get("Any", [])
            lines += motds.get("Any", {}).get(day, [])
            lines += motds.get("Any", {}).get(weekday, [])
            lines += motds.get(month, {}).get("Any", [])
            lines += motds.get(month, {}).get(day, [])
            lines += motds.get(month, {}).get(weekday, [])
            await respond(msg, "\n".join(lines))
