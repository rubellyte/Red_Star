import asyncio
import datetime
import json
import schedule
from random import choice
from plugin_manager import BasePlugin
from utils import Command, respond


class MOTD(BasePlugin):
    name = "motd"
    default_config = {
        "motd_file": "config/motds.json",
        "motd_channel": "CHANNEL ID HERE"
    }

    def activate(self):
        try:
            with open(self.plugin_config.motd_file, "r") as f:
                self.motds = json.load(f)
                schedule.every().day.at("00:00").do(self._display_motd)
                asyncio.ensure_future(self._run_motd())
        except FileNotFoundError:
            with open(self.plugin_config.motd_file, "w") as f:
                self.motds = {}
                f.write("{}")
        except json.decoder.JSONDecodeError:
            self.logger.exception(f"Could not decode {self.plugin_config.motd_file}! ", exc_info=True)
        # This is stupid
        self.valid_months = {
            "January", "February", "March", "April", "May", "June", "July",
            "August", "September", "October", "November", "December", "Any"
        }
        self.valid_days = {
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Any",
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16",
            "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31"
        }

    async def _run_motd(self):
        while True:
            schedule.run_pending()
            await asyncio.sleep(60)

    def _save_motds(self):
        with open(self.plugin_config.motd_file, "w") as f:
            json.dump(self.motds, f, indent=2)

    def _display_motd(self):
        today = datetime.date.today()
        month = today.strftime("%B")
        day = str(today.day)
        weekday = today.strftime("%A")
        holiday_lines = self._get_holiday(month, day, weekday)
        chan = self.client.get_channel(self.plugin_config.motd_channel)
        if holiday_lines:
            asyncio.ensure_future(self.client.send_message(chan, choice(holiday_lines)))
        else:
            lines = []
            lines += self.motds.get("Any", {}).get("Any", [])
            lines += self.motds.get("Any", {}).get(day, [])
            lines += self.motds.get("Any", {}).get(weekday, [])
            lines += self.motds.get(month, {}).get("Any", [])
            lines += self.motds.get(month, {}).get(day, [])
            lines += self.motds.get(month, {}).get(weekday, [])
            asyncio.ensure_future(self.client.send_message(chan, choice(lines)))

    def _get_holiday(self, month, day, weekday):
        holidays = self.motds["holidays"]
        if f"{month}/{day}" in holidays:
            return self.motds[month][day]
        elif f"{month}/{weekday}" in holidays:
            return self.motds[month][weekday]
        elif f"{month}/Any" in holidays:
            return self.motds[month]["Any"]
        elif f"Any/{day}" in holidays:
            return self.motds["Any"][day]
        elif f"Any/{weekday}" in holidays:
            return self.motds["Any"][weekday]
        else:
            return

    @Command("addmotd",
             doc="Adds a MotD message.",
             perms={"manage_server"},
             syntax="(month/Any) (day/weekday/Any) (message)")
    async def _addmotd(self, data):
        args = data.clean_content.split()[1:]
        try:
            month = args[0].capitalize()
            day = args[1].capitalize()
            msg = " ".join(args[2:])
        except IndexError:
            raise SyntaxError
        if month not in self.valid_months or day not in self.valid_days:
            self.logger.debug(month)
            self.logger.debug(day)
            raise SyntaxError("Month or day is invalid. Please use full names.")
        try:
            if month not in self.motds:
                self.motds[month] = {}
            if day not in self.motds[month]:
                self.motds[month][day] = []
            self.motds[month][day].append(msg)
            self._save_motds()
            await respond(self.client, data, f"**ANALYSIS: MotD for {month} {day} added successfully.**")
        except KeyError:
            self.logger.debug(month)
            self.logger.debug(day)
            raise SyntaxError("Month or day is invalid. Please use full names.")

    @Command("testmotds",
             doc="Used for testing MOTD lines.",
             perms={"manage_server"},
             syntax="(month/Any) (day/weekday/Any)")
    async def _testmotd(self, data):
        try:
            args = data.clean_content.split()[1:]
            month = args[0]
            day = args[1]
            weekday = args[2]
        except IndexError:
            raise SyntaxError
        holiday_lines = self._get_holiday(month, day, weekday)
        if holiday_lines:
            await respond(self.client, data, choice(holiday_lines))
        else:
            lines = []
            lines += self.motds.get("Any", {}).get("Any", [])
            lines += self.motds.get("Any", {}).get(day, [])
            lines += self.motds.get("Any", {}).get(weekday, [])
            lines += self.motds.get(month, {}).get("Any", [])
            lines += self.motds.get(month, {}).get(day, [])
            lines += self.motds.get(month, {}).get(weekday, [])
            await respond(self.client, data, "\n".join(lines))
