from plugin_manager import BasePlugin
from rs_utils import respond, DotDict, find_user
from command_dispatcher import Command
from rs_errors import CommandSyntaxError


class Levelling(BasePlugin):
    name = "levelling"
    default_config = {
        "default": {
            "low_cutoff": 75,
            "xp_min": 1,
            "xp_max": 10,
            "xp_decay": 10,
            "poll_every": 3600,
            "xp_decay_every": 86400
        }
    }

    async def activate(self):
        for guild in self.client.guilds:
            self.channel_manager.register_category(guild, "no_xp")

    async def on_message(self, msg):
        if self.channel_manager.channel_in_category(msg.guild, "no_xp", msg.channel):
            return
        gid = str(msg.guild.id)
        self._initialize(gid)
        self._give_xp(msg)

    async def on_message_delete(self, msg):
        if self.channel_manager.channel_in_category(msg.guild, "no_xp", msg.channel):
            return
        gid = str(msg.guild.id)
        self._initialize(gid)
        self._take_xp(msg)

    # Commands

    @Command("listxp",
             doc="Lists all registered users from highest XP to lowest, up to amount specified or 10.",
             syntax="[number]",
             category="XP")
    async def _listxp(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        args = msg.content.split(" ")
        if len(args) > 1:
            try:
                limit = int(args[1])
            except ValueError:
                raise CommandSyntaxError(f"{args[1]} is not a valid integer.")
        else:
            limit = 10
        t_str = "**ANALYSIS: Current XP leaderboard:**\n```\n"
        t_int = 1
        for t_id in sorted(self.storage[gid], key=self.storage[gid].get, reverse=True):
            t_m = msg.guild.get_member(t_id)
            if t_m:
                t_m = t_m.display_name.ljust(32)
            else:
                t_m = str(t_id).ljust(32)
            t_s = f"{t_int:03d}|{t_m}|{self.storage[gid][t_id]}\n"
            t_int += 1
            if len(t_str)+len(t_s) > 1997:
                await respond(msg, t_str+"```")
                t_str = "```"+t_s
            else:
                t_str += t_s
            if t_int > limit:
                break
        await respond(msg, t_str+"```")

    @Command("xp",
             doc="Shows your xp or xp of specified user.",
             syntax="[user]",
             category="XP")
    async def _xp(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        args = msg.content.split(" ", 1)
        if len(args) > 1:
            t_member = find_user(msg.guild, args[1])
            if t_member:
                if t_member.id in self.storage[gid]:
                    await respond(msg, f"**ANALYSIS: User {t_member.display_name} has "
                                       f"{self.storage[gid][t_member.id]} XP.**")
                else:
                    await respond(msg, f"**WARNING: User {t_member.display_name} has no XP record.**")
            else:
                raise CommandSyntaxError("Not a user or user not found.")
        else:
            if msg.author.id in self.storage[gid]:
                await respond(msg, f"**ANALYSIS: You have {self.storage[gid][msg.author.id]} XP.**")
            else:
                await respond(msg, "**ANALYSIS: You have no XP record.**")  # I don't think this is possible

    @Command("evalxp",
             doc="Processes all message history and grants members xp.\nAccepts one argument to determine "
                 "how far into the history to search.\nWARNING - VERY SLOW.\nUSE ONLY AFTER "
                 "CLEANING XP TABLE.",
             syntax="[depth]",
             perms={"manage_guild"},
             category="XP")
    async def _evalxp(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        args = msg.content.split(" ", 1)
        if len(args) > 1:
            try:
                depth = int(args[1])
            except ValueError:
                raise CommandSyntaxError("Argument is not a valid integer.")
        else:
            depth = None
        t_msg = await respond(msg, "**AFFIRMATIVE. Processing messages.**")
        async with msg.channel.typing():
            for channel in msg.guild.text_channels:
                if not self.channel_manager.channel_in_category(msg.guild, "no_xp", channel):
                    await t_msg.edit(content=f"**AFFIRMATIVE. Processing messages in channel {channel}.**")
                    async for message in channel.history(limit=depth):
                        self._give_xp(message)
        await t_msg.delete()

    @Command("nukexp",
             doc="Permanently erases XP records, setting given user or EVERYONE to 0.",
             syntax="[user]",
             perms={"manage_guild"},
             category="XP")
    async def _nukexp(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        args = msg.content.split(" ", 1)
        if len(args) > 1:
            t_member = find_user(msg.guild, args[1])
            if t_member:
                if t_member.id in self.storage[gid]:
                    del self.storage[gid][t_member.id]
                    await respond(msg, f"**AFFIRMATIVE. User {t_member.display_name} was removed from XP table.**")
                else:
                    await respond(msg, f"**NEGATIVE. User {t_member.display_name} has no XP record.**")
            else:
                try:
                    t_member = int(args[1])
                except ValueError:
                    raise CommandSyntaxError("Not a user or no user found.")
                if t_member in self.storage[gid]:
                    del self.storage[gid][t_member]
                    await respond(msg, f"**AFFIRMATIVE. ID {t_member} was removed from XP table.**")
                else:
                    raise CommandSyntaxError("Not a user or no user found.")
        else:
            self.storage[gid] = {}
            await respond(msg, "**AFFIRMATIVE. XP table deleted.**")

    @Command("xpconfig", "xpsettings",
             doc="Edit the xp module settings, or see the current settings."
                 "\nIt is advised to do !nukexp !evalxp after adjusting settings.",
             syntax="[option] [value]",
             perms={"manage_guild"},
             category="XP")
    async def _setxp(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        args = msg.content.split(" ", 2)
        if len(args) != 3:
            if len(args) == 1:
                await respond(msg, "**ANALYSIS: Current XP settings:**```\n"
                                   f"low_cutoff: {self.plugin_config[gid]['low_cutoff']}\n"
                                   f"xp_min    : {self.plugin_config[gid]['xp_min']}\n"
                                   f"xp_max    : {self.plugin_config[gid]['xp_max']}```")
            else:
                raise CommandSyntaxError("Two arguments required.")
        else:
            try:
                val = int(args[2])
            except ValueError:
                raise CommandSyntaxError("Second argument must be an integer.")
            else:
                if args[1].lower() == "low_cutoff":
                    self.plugin_config[gid]["low_cutoff"] = val
                elif args[1].lower() == "xp_min":
                    self.plugin_config[gid]["xp_min"] = val
                elif args[1].lower() == "xp_max":
                    self.plugin_config[gid]["xp_max"] = val
                else:
                    raise CommandSyntaxError(f"No option {args[1].lower()}")


    # Utilities

    def _initialize(self, gid):
        """
        :type gid:str
        :param gid:guild ID, string
        :return:
        """
        if gid not in self.storage:
            self.storage[gid] = {}
        if gid not in self.plugin_config:
            self.plugin_config[gid] = DotDict(self.plugin_config["default"])

    def _give_xp(self, msg):
        gid = str(msg.guild.id)
        if msg.author.id in self.storage[gid]:
            self.storage[gid][msg.author.id] += self._calc_xp(msg.clean_content, gid)
        else:
            self.storage[gid][msg.author.id] = self._calc_xp(msg.clean_content, gid)

    def _take_xp(self, msg):
        gid = str(msg.guild.id)
        if msg.author.id in self.storage[gid]:
            self.storage[gid][msg.author.id] -= self._calc_xp(msg.clean_content, gid)

    def _calc_xp(self, txt, gid):
        """
        :type txt:str
        :param txt:message to calculate the xp for
        :return:
        """
        spc = self.plugin_config[gid]

        if len(txt) < spc["low_cutoff"]:
            return 0

        t_percent = (len(txt)-spc["low_cutoff"])/(2000-spc["low_cutoff"])

        t_xp = spc["xp_min"] + (spc["xp_max"]-spc["xp_min"])*t_percent

        return int(t_xp)

    # TODO implement xp decay
    def _xpdecay(self, gid):
        for k, v in self.storage[gid]:
            self.storage[gid][k] = v*(100-self.plugin_config[gid]["xp_decay"])/100
