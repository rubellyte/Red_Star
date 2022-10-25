from __future__ import annotations
from red_star.plugin_manager import BasePlugin
from red_star.rs_utils import respond, find_user, is_positive, group_items, prompt_for_confirmation
from red_star.command_dispatcher import Command
from red_star.rs_errors import CommandSyntaxError
import discord
import json


class Levelling(BasePlugin):
    name = "levelling"
    version = "1.1"
    author = "GTG3000"
    description = "A plugin for providing an XP system that awards members XP for messages."
    default_config = {
        "low_cutoff": 75,
        "xp_min": 1,
        "xp_max": 10,
        "skip_missing": False
    }
    channel_categories = {"no_xp"}

    async def activate(self):
        self._port_old_storage()
        self.storage.setdefault("xp", {})

    def _port_old_storage(self):
        old_storage_path = self.config_manager.config_path / "xp.json"
        if old_storage_path.exists():
            with old_storage_path.open(encoding="utf-8") as fp:
                old_storage = json.load(fp)
            for guild_id, xp_storage in old_storage.items():
                try:
                    new_storage = self.config_manager.storage_files[guild_id][self.name]
                except KeyError:
                    self.logger.warn(f"Server with ID {guild_id} not found! Is the bot still in this server?\n"
                                     f"Skipping conversion of this server's XP storage...")
                    continue
                new_storage.contents["xp"] = xp_storage
                new_storage.save()
                new_storage.load()
            old_storage_path = old_storage_path.replace(old_storage_path.with_suffix(".json.old"))
            self.logger.info(f"Old XP storage converted to new format. "
                             f"Old data now located at {old_storage_path} - you may delete this file.")

    async def on_message(self, msg: discord.Message):
        if not self.channel_manager.channel_in_category("no_xp", msg.channel):
            self._give_xp(msg)

    async def on_message_delete(self, msg: discord.Message):
        if not self.channel_manager.channel_in_category("no_xp", msg.channel):
            self._take_xp(msg)

    # Commands

    @Command("ListXP", "XPLeaderboard",
             doc="Lists all registered users from highest XP to lowest, up to amount specified or 10.",
             syntax="[number]",
             category="levelling")
    async def _listxp(self, msg: discord.Message):
        skip = self.config['skip_missing']

        args = msg.content.split()
        if len(args) > 1:
            try:
                limit = int(args[1])
            except ValueError:
                raise CommandSyntaxError(f"{args[1]} is not a valid integer.")
        else:
            limit = 10

        # Iterate over all the xp values, counting up the position and forming a nice string.
        # Not using enumerate because some positions may be skipped due to missing members.
        # Could possibly squeeze it into a list comprehension, but it would be a monstrosity.

        pos = 1
        xp_list = []
        for uid in sorted(self.storage["xp"], key=self.storage["xp"].get, reverse=True):
            user = msg.guild.get_member(int(uid))

            if user:
                user = user.display_name
            elif skip:
                continue
            else:
                user = uid

            xp_list.append(f"{pos:03d}|{user:<32}|{self.storage['xp'][uid]:>6}")
            pos += 1

            if pos > limit:
                break

        if xp_list:
            for string in group_items(xp_list, message="**ANALYSIS: Current XP leaderboard:**"):
                await respond(msg, string)

    @Command("XP", "ShowXP",
             doc="Shows your xp or xp of specified user.",
             syntax="[user]",
             category="levelling")
    async def _xp(self, msg: discord.Message):
        args = msg.content.split(None, 1)

        if len(args) > 1:
            user = find_user(msg.guild, args[1])
            if user:
                if str(user.id) in self.storage["xp"]:
                    await respond(msg, f"**ANALYSIS: User {user.display_name} has "
                                       f"{self.storage['xp'][str(user.id)]} XP.**")
                else:
                    await respond(msg, f"**WARNING: User {user.display_name} has no XP record.**")
            else:
                raise CommandSyntaxError("Not a user or user not found.")
        else:
            uid = str(msg.author.id)
            if uid in self.storage["xp"]:
                await respond(msg, f"**ANALYSIS: You have {self.storage['xp'][uid]} XP.**")
            else:
                await respond(msg, "**ANALYSIS: You have no XP record.**")  # I don't think this is possible

    @Command("EvalXP",
             doc="Processes all message history and grants members xp.\nAccepts one argument to determine "
                 "how far into the history to search.\nWARNING - VERY SLOW.\nUSE ONLY AFTER "
                 "CLEANING XP TABLE.",
             syntax="[depth]",
             perms={"manage_guild"},
             category="levelling")
    async def _evalxp(self, msg: discord.Message):
        args = msg.content.split(None, 1)
        if len(args) > 1:
            try:
                depth = int(args[1])
            except ValueError:
                raise CommandSyntaxError("Argument is not a valid integer.")
        else:
            depth = None

        display = await respond(msg, "**AFFIRMATIVE. Processing messages.**")
        async with msg.channel.typing():
            for channel in self.guild.text_channels:
                if not self.channel_manager.channel_in_category("no_xp", channel):
                    await display.edit(content=f"**AFFIRMATIVE. Processing messages in channel {channel}.**")
                    try:
                        async for message in channel.history(limit=depth):
                            self._give_xp(message)
                    except discord.Forbidden:
                        continue

        self.storage_file.save()
        await display.delete()

    @Command("NukeXP",
             doc="Permanently erases XP records, setting given user or EVERYONE to 0.",
             syntax="[user]",
             perms={"manage_guild"},
             category="levelling")
    async def _nukexp(self, msg: discord.Message):
        args = msg.content.split(None, 1)

        if len(args) > 1:
            user = find_user(msg.guild, args[1])
            if user:
                if str(user.id) in self.storage["xp"]:
                    del self.storage["xp"][str(user.id)]
                    await respond(msg, f"**AFFIRMATIVE. User {user.display_name} was removed from XP table.**")
                else:
                    await respond(msg, f"**NEGATIVE. User {user.display_name} has no XP record.**")
            elif args[1] in self.storage["xp"]:
                del self.storage["xp"][args[1]]
                await respond(msg, f"**AFFIRMATIVE. ID {args[1]} was removed from XP table.**")
            else:
                raise CommandSyntaxError("Not a user or no user found.")
        else:
            prompt_text = f"This will destroy ALL XP records for the entire server. Continue?"
            confirmed = await prompt_for_confirmation(msg, prompt_text=prompt_text)
            if not confirmed:
                return
            self.storage["xp"] = {}
            self.storage_file.save()
            await respond(msg, "**AFFIRMATIVE. XP table deleted.**")

    @Command("XPConfig", "XPSettings",
             doc="Edit the xp module settings, or see the current settings."
                 "\nIt is advised to do !nukexp !evalxp after adjusting settings.",
             syntax="[option] [value]",
             perms={"manage_guild"},
             category="levelling")
    async def _setxp(self, msg: discord.Message):
        args = msg.content.split(" ", 2)
        cfg = self.config
        if len(args) == 1:
            missing_member_str = ("skipping" if cfg["skip_missing"] else "displaying") + " missing members"
            await respond(msg, "**ANALYSIS: Current XP settings:**```\n"
                               f"low_cutoff: {cfg['low_cutoff']}\n"
                               f"xp_min    : {cfg['xp_min']}\n"
                               f"xp_max    : {cfg['xp_max']}\n"
                               f"missing   : {missing_member_str}```")
        elif len(args) == 3:
            if args[1].lower() == "missing":
                cfg["skip_missing"] = is_positive(args[2])
            else:
                try:
                    val = int(args[2])
                except ValueError:
                    raise CommandSyntaxError("Second argument must be an integer.")
                else:
                    if args[1].lower() == "low_cutoff":
                        cfg["low_cutoff"] = val
                    elif args[1].lower() == "xp_min":
                        cfg["xp_min"] = val
                    elif args[1].lower() == "xp_max":
                        cfg["xp_max"] = val
                    else:
                        raise CommandSyntaxError(f"No option {args[1].lower()}")
        else:
            raise CommandSyntaxError("Two arguments required.")

    # Utilities

    def _give_xp(self, msg: discord.Message):
        uid = str(msg.author.id)
        if uid in self.storage["xp"]:
            self.storage["xp"][uid] += self._calc_xp(msg.clean_content)
        else:
            self.storage["xp"][uid] = self._calc_xp(msg.clean_content)

    def _take_xp(self, msg: discord.Message):
        uid = str(msg.author.id)
        if uid in self.storage["xp"]:
            self.storage["xp"][uid] -= self._calc_xp(msg.clean_content)

    def _calc_xp(self, txt: str):
        """
        :type txt:str
        :param txt:message to calculate the xp for
        :return:
        """
        spc = self.config

        if len(txt) < spc["low_cutoff"]:
            return 0

        t_percent = (len(txt)-spc["low_cutoff"])/(2000-spc["low_cutoff"])

        t_xp = spc["xp_min"] + (spc["xp_max"]-spc["xp_min"])*t_percent

        return int(t_xp)
