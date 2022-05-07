from red_star.plugin_manager import BasePlugin
from red_star.rs_utils import respond, find_user, is_positive, JsonFileDict, group_items
from red_star.command_dispatcher import Command
from red_star.rs_errors import CommandSyntaxError
from discord.errors import Forbidden


class Levelling(BasePlugin):
    name = "levelling"
    version = "1.1"
    author = "GTG3000"
    description = "A plugin for providing an XP system that awards members XP for messages."
    default_config = {
        "default": {
            "low_cutoff": 75,
            "xp_min": 1,
            "xp_max": 10,
            "skip_missing": False
        }
    }
    channel_categories = {"no_xp"}

    storage: JsonFileDict

    async def activate(self):
        self.storage = self.config_manager.get_plugin_config_file("xp.json")

    async def on_message(self, msg):
        if not self.channel_manager.channel_in_category(msg.guild, "no_xp", msg.channel):
            self._give_xp(msg)

    async def on_message_delete(self, msg):
        if not self.channel_manager.channel_in_category(msg.guild, "no_xp", msg.channel):
            self._take_xp(msg)

    # Commands

    @Command("ListXP", "XPLeaderboard",
             doc="Lists all registered users from highest XP to lowest, up to amount specified or 10.",
             syntax="[number]",
             category="levelling")
    async def _listxp(self, msg):
        gid = str(msg.guild.id)

        xp_dict = self.storage.setdefault(gid, dict())
        skip = self.plugin_config.setdefault(gid, self.plugin_config['default'].copy())['skip_missing']

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
        for uid in sorted(xp_dict, key=xp_dict.get, reverse=True):
            user = msg.guild.get_member(int(uid))

            if user:
                user = user.display_name
            elif skip:
                continue
            else:
                user = uid

            xp_list.append(f"{pos:03d}|{user:<32}|{xp_dict[uid]:>6}")
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
    async def _xp(self, msg):
        gid = str(msg.guild.id)

        args = msg.content.split(None, 1)

        xp_dict = self.storage.setdefault(gid, dict())

        if len(args) > 1:
            user = find_user(msg.guild, args[1])
            if user:
                if str(user.id) in xp_dict:
                    await respond(msg, f"**ANALYSIS: User {user.display_name} has "
                                       f"{xp_dict[str(user.id)]} XP.**")
                else:
                    await respond(msg, f"**WARNING: User {user.display_name} has no XP record.**")
            else:
                raise CommandSyntaxError("Not a user or user not found.")
        else:
            uid = str(msg.author.id)
            if uid in xp_dict:
                await respond(msg, f"**ANALYSIS: You have {xp_dict[uid]} XP.**")
            else:
                await respond(msg, "**ANALYSIS: You have no XP record.**")  # I don't think this is possible

    @Command("EvalXP",
             doc="Processes all message history and grants members xp.\nAccepts one argument to determine "
                 "how far into the history to search.\nWARNING - VERY SLOW.\nUSE ONLY AFTER "
                 "CLEANING XP TABLE.",
             syntax="[depth]",
             perms={"manage_guild"},
             category="levelling")
    async def _evalxp(self, msg):
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
            for channel in msg.guild.text_channels:
                if not self.channel_manager.channel_in_category(msg.guild, "no_xp", channel):
                    await display.edit(content=f"**AFFIRMATIVE. Processing messages in channel {channel}.**")
                    try:
                        async for message in channel.history(limit=depth):
                            self._give_xp(message)
                    except Forbidden:
                        continue

        self.storage.save()
        await display.delete()

    @Command("NukeXP",
             doc="Permanently erases XP records, setting given user or EVERYONE to 0.",
             syntax="[user]",
             perms={"manage_guild"},
             category="levelling")
    async def _nukexp(self, msg):
        gid = str(msg.guild.id)
        args = msg.content.split(None, 1)

        if len(args) > 1:
            user = find_user(msg.guild, args[1])
            xp_dict = self.storage.setdefault(gid, dict())
            if user:
                if str(user.id) in xp_dict:
                    del xp_dict[str(user.id)]
                    await respond(msg, f"**AFFIRMATIVE. User {user.display_name} was removed from XP table.**")
                else:
                    await respond(msg, f"**NEGATIVE. User {user.display_name} has no XP record.**")
            elif args[1] in xp_dict:
                del xp_dict[args[1]]
                await respond(msg, f"**AFFIRMATIVE. ID {args[1]} was removed from XP table.**")
            else:
                raise CommandSyntaxError("Not a user or no user found.")
        else:
            self.storage[gid] = {}
            await respond(msg, "**AFFIRMATIVE. XP table deleted.**")

    @Command("XPConfig", "XPSettings",
             doc="Edit the xp module settings, or see the current settings."
                 "\nIt is advised to do !nukexp !evalxp after adjusting settings.",
             syntax="[option] [value]",
             perms={"manage_guild"},
             category="levelling")
    async def _setxp(self, msg):
        gid = str(msg.guild.id)
        args = msg.content.split(" ", 2)
        cfg = self.plugin_config.setdefault(gid, self.plugin_config['default'].copy())
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

    def _give_xp(self, msg):
        gid = str(msg.guild.id)
        uid = str(msg.author.id)
        if uid in self.storage.setdefault(gid, dict()):
            self.storage[gid][uid] += self._calc_xp(msg.clean_content, gid)
        else:
            self.storage[gid][uid] = self._calc_xp(msg.clean_content, gid)

    def _take_xp(self, msg):
        gid = str(msg.guild.id)
        uid = str(msg.author.id)
        if uid in self.storage.setdefault(gid, dict()):
            self.storage[gid][uid] -= self._calc_xp(msg.clean_content, gid)

    def _calc_xp(self, txt, gid):
        """
        :type txt:str
        :param txt:message to calculate the xp for
        :return:
        """
        spc = self.plugin_config.setdefault(gid, self.plugin_config['default'].copy())

        if len(txt) < spc["low_cutoff"]:
            return 0

        t_percent = (len(txt)-spc["low_cutoff"])/(2000-spc["low_cutoff"])

        t_xp = spc["xp_min"] + (spc["xp_max"]-spc["xp_min"])*t_percent

        return int(t_xp)
