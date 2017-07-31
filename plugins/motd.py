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
        except json.decoder.JSONDecodeError:
            self.logger.exception(f"Could not decode {self.plugin_config.motd_file}! ", exc_info=True)

    async def _run_motd(self):
        while True:
            schedule.run_pending()
            await asyncio.sleep(60)

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

    @Command("testmotd",
             doc="Used for testing MOTD lines.",
             syntax="(month/Any) (day/weekday/Any)")
    async def _testmotd(self, data):
        args = data.clean_content.split()[1:]
        month = args[0]
        day = args[1]
        weekday = args[2]
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

    @Command("displaymotd",
             doc="Display a MOTD based on the current date.")
    async def _displaymotdcmd(self, data):
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
