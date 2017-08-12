from plugin_manager import BasePlugin
from utils import Command, respond
from discord import HTTPException, Forbidden
from discord.object import Object as DObj
from math import ceil
import re
import time
import threading
import asyncio


class AntiSpam(BasePlugin):
    name = "anti_spam"
    default_config = {
        'default': {
            'timeout': 10,
            'message_count': 5,
            'spam_ban':      False,      # XTREEEEEEEEME
            'spam_delete':   False,      # Delete the messages treated as spam
            'spam_role':     False,      # Role to add to a spammer. ID or False
            'spam_role_timeout': 60,     # Remove role after x seconds
            'spam_reaction': False,      # Add a reaction to messages treated as spam. ID or False #232885229352779776
            'thresholds': [1, 1, 2, 2],  # react - delet - mute - ban
            'infraction_timeout': 300    # get another infraction if you're stupid enough to spam repeatedly
        },
        'poll_every': 5
    }

    class UserStorage:
        member = False
        guild = False
        parent = False
        infractions = 0
        update_time = 0
        messages = 0
        needs_reinit = False
        muted = False

        def __init__(self, member, guild, parent):
            """

            :type parent: AntiSpam
            """
            self.member = member
            self.guild = guild
            self.parent = parent
            self.infractions = 0
            self.update_time = time.time()

        def __getstate__(self):
            result = {
                'member': self.member.id,
                'guild': self.guild.id,
                'infractions': self.infractions,
                'update_time': self.update_time,
                'messages': self.messages,
                'muted': self.muted
            }
            return result

        def __setstate__(self, state):
            self.member = state["member"]
            self.guild = state["guild"]
            self.infractions = state["infractions"]
            self.update_time = state["update_time"]
            self.messages = state["messages"]
            self.muted = state.get("muted", False)
            self.needs_reinit = True

        def reinit(self, parent):
            self.parent = parent
            self.guild = parent.client.get_guild(self.guild)
            self.member = self.guild.get_member(self.member)
            self.needs_reinit = False

        async def infract(self):
            if self.needs_reinit:
                return
            if self.guild.id not in self.parent.s_thresholds:
                return
            if len(self.parent.s_thresholds[self.guild.id]) != 4:
                return
            t_thold = self.parent.s_thresholds[self.guild.id]
            self.infractions += 1
            print(f"Infractions of {self.member.display_name} : {self.infractions}")
            self.update_time = time.time()
            t_config = self.parent.plugin_config[str(self.guild.id)]
            if self.infractions >= t_thold[3] and t_config["spam_ban"]:
                try:
                    self.parent.logger.info(f"Banned member {self.member.display_name}")
                    await self.guild.ban(self.member, reason="Banned for repeated spamming.", delete_message_days=0)
                except Forbidden:
                    self.parent.logger.warning(f"Can't edit member {self.member.display_name}")
            elif self.infractions >= t_thold[2] and t_config["spam_role"]:
                try:
                    await self.member.add_roles(DObj(t_config["spam_role"]),
                                                reason="Muting for spam. (applying a specified role.)")
                except Forbidden:
                    self.parent.logger.warning(f"Can't edit member {self.member.display_name}")
                except HTTPException:
                    self.parent.logger.warning(f"Member {self.member.display_name} already has mute role.")
                else:
                    self.parent.logger.info(f"Muted member {self.member.display_name}")
                    self.muted = True

        async def update(self):
            if self.needs_reinit:
                return
            t_config = self.parent.plugin_config[str(self.guild.id)]
            if t_config["spam_role"] and time.time() - self.update_time > t_config['spam_role_timeout'] and self.muted:
                for t_role in self.member.roles:
                    if t_role.id == int(t_config["spam_role"]):
                        try:
                            await self.member.remove_roles(t_role, reason="Mute time ran out.")
                        except Forbidden:
                            self.parent.logger.warning(f"Can't edit member {self.member.display_name}")
                        else:
                            self.muted = False
                        break
            if time.time() - self.update_time > t_config['infraction_timeout']:
                self.infractions = max(0, self.infractions-1)
                self.update_time = time.time()

    async def activate(self):
        self.run_timer = True
        self.s_thresholds = {}
        if "members" not in self.storage:
            self.storage["members"] = {}
        for guild in self.client.guilds:
            if guild.id not in self.storage["members"]:
                self.storage["members"][guild.id] = {}
            else:
                for k, t_member in self.storage["members"][guild.id].items():
                    t_member.reinit(self)
            if str(guild.id) not in self.plugin_config:
                self.plugin_config[str(guild.id)] = self.plugin_config["default"]
            self.calc_thresholds(guild)

        loop = asyncio.new_event_loop()
        t_loop = asyncio.get_event_loop()
        self.timer = threading.Thread(target=self.start_timer, args=[loop, t_loop])
        self.timer.setDaemon(True)
        self.timer.start()

    async def deactivate(self):
        self.run_timer = False

    # Event handlers

    async def on_guild_join(self, guild):
        self.storage["muted_members"][str(guild.id)] = {}
        self.plugin_config[str(guild.id)] = self.plugin_config["default"]

    async def on_guild_remove(self, guild):
        self.storage["muted_members"].pop(str(guild.id))
        self.plugin_config.pop(str(guild.id))

    async def on_message(self, msg):
        """
        Counts the messages in the time period.
        First element is time.time(), second is the count
        """
        if msg.author == msg.guild.me:
            return

        if msg.author.id in self.storage["members"][msg.guild.id]:
            t_member = self.storage["members"][msg.guild.id][msg.author.id]
            t_config = self.plugin_config[str(msg.guild.id)]
            if time.time() - t_member.update_time < t_config["timeout"]:
                t_member.messages += 1
                if t_member.messages >= t_config["message_count"]:
                    if t_member.messages % t_config["message_count"] == 0:
                        await t_member.infract()
                    else:
                        t_member.update_time = time.time()
                    if t_member.infractions >= self.s_thresholds[msg.guild.id][1] and t_config["spam_delete"]:
                        await msg.delete(reason="Spam filtering.")
                    elif t_member.infractions >= self.s_thresholds[msg.guild.id][0] and t_config["spam_reaction"]:
                        if len(t_config["spam_reaction"]) != 18:
                            try:
                                await msg.add_reaction(t_config["spam_reaction"])
                            except HTTPException:
                                self.logger.error(f"Non-emoji character set as spam reaction on server {msg.guild.id}")
                        else:
                            await msg.add_reaction(self.client.get_emoji(int(t_config["spam_reaction"])))
            else:
                t_member.messages = 1
                t_member.update_time = time.time()
        else:
            self.storage["members"][msg.guild.id][msg.author.id] = self.UserStorage(msg.author, msg.guild, self)

    # Commands

    @Command("spam_emoji",
             perms={"manage_guild"},
             doc="Sets the emoji to react to early spam with, or turns that off.",
             syntax="[emoji]")
    async def _getmoji(self, msg):
        args = msg.content.split()
        if len(args) > 1:
            if len(args[1]) == 1:
                try:
                    await msg.add_reaction(args[1])
                except HTTPException:
                    raise SyntaxError(f"Non-emoji character set as spam reaction on server.")
                else:
                    self.plugin_config[str(msg.guild.id)]["spam_reaction"] = args[1]
                    await respond(msg, f"**AFFIRMATIVE. ANALYSIS: New spam reaction emoji: {args[1]}.**")
                    await msg.remove_reaction(args[1], msg.guild.me)
            elif re.fullmatch("<:\w{1,32}:\d{18}>", args[1]):
                t_emoji = re.search("\d{18}", args[1])[0]
                if self.client.get_emoji(int(t_emoji)):
                    self.plugin_config[str(msg.guild.id)]["spam_reaction"] = t_emoji
                    await respond(msg, f"**AFFIRMATIVE. ANALYSIS: New spam reaction emoji: {args[1]}.**")
            else:
                raise SyntaxError("Expected a single emoji as argument.")
        else:
            self.plugin_config[str(msg.guild.id)]["spam_reaction"] = False
            await respond(msg, f"**AFFIRMATIVE. Spam reaction disabled.**")

    @Command("spam_role",
             perms={"manage_guild"},
             doc="Sets the role to apply on sufficient infractions, or turns that off.",
             syntax="[role ID or Name]")
    async def _getrole(self, msg):
        args = msg.content.split()
        if len(args) > 1:
            if re.fullmatch("\d{18}", args[1]):
                for role in msg.guild.roles:
                    if role.id == int(args[1]):
                        self.plugin_config[str(msg.guild.id)]["spam_role"] = args[1]
                        await respond(msg, f"**AFFIRMATIVE. ANALYSIS: New anti-spam role: {role.name}**")
                        break
                else:
                    await respond(msg, "**NEGATIVE. Invalid role ID.**")
            else:
                for role in msg.guild.roles:
                    if role.name.lower() == args[1].lower():
                        self.plugin_config[str(msg.guild.id)]["spam_role"] = str(role.id)
                        await respond(msg, f"**AFFIRMATIVE. ANALYSIS: New anti-spam role: {role.name}**")
                        break
                else:
                    await respond(msg, "**NEGATIVE. Invalid role Name.**")
        else:
            await respond(msg, "**AFFIRMATIVE. Spam role disabled.**")

    @Command("spam_ban",
             perms={"manage_guild"},
             doc="Enables or disables banning for excessive spamming.",
             syntax="[Enable/Disable]")
    async def _spamban(self, msg):
        args = msg.content.split()
        if len(args) > 1 and args[1].lower() == "enable":
            self.plugin_config[str(msg.guild.id)]["spam_ban"] = True
            await respond(msg, "**AFFIRMATIVE. Spam banning enabled.**")
        else:
            self.plugin_config[str(msg.guild.id)]["spam_ban"] = False
            await respond(msg, "**AFFIRMATIVE. Spam banning disabled.**")

    @Command("spam_list",
             doc="Prints a list of all people with non-zero infractions currently.")
    async def _spamlist(self, msg):
        t_string = ""
        for _, t_member in self.storage["members"][msg.guild.id].items():
            if t_member.infractions > 0:
                t_m, t_s = divmod(ceil(time.time()-t_member.update_time), 60)
                t_string = f"{t_string} {t_member.member.display_name.ljust(32)} : " \
                           f"{t_member.infractions:02d} [{t_m:02d}:{t_s:02d}]\n"
        await respond(msg, f"**ANALYSIS: Members in spam list:**\n```{t_string}```")

    # Miscellaneous

    def calc_thresholds(self, guild):
        """
        Turns the additive numbers in the config into progressive numbers for the system to use.
        :param guild:
        :return:
        """
        if guild.id not in self.s_thresholds:
            self.s_thresholds[guild.id] = [0, 0, 0, 0]
        t_lst = self.s_thresholds[guild.id]
        t_config = self.plugin_config[str(guild.id)]
        for i in range(4):
            if i == 0 and t_config["spam_reaction"]:
                t_lst[i] = t_config["thresholds"][i]
            if i >= 1:
                t_lst[i] = t_lst[i-1]
            if i == 1 and t_config["spam_delete"]:
                t_lst[i] += t_config["thresholds"][i]
            if i == 2 and t_config["spam_role"]:
                t_lst[i] += t_config["thresholds"][i]
            if i == 3 and t_config["spam_ban"]:
                t_lst[i] += t_config["thresholds"][i]

    def start_timer(self, loop, t_loop):
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.update_regular(t_loop))
        except Exception:
            self.logger.exception("Error starting timer. ", exc_info=True)

    async def update_regular(self, loop):
        """
        A regularly ran function that takes care of periodic tasks.
        Such as making cooldowns run out and checking if members still exist.
        :param loop:
        :return:
        """
        while self.run_timer:
            await asyncio.sleep(self.plugin_config["poll_every"])
            for k, t_guild in self.storage["members"].items():
                t_lst = []
                for k1, t_member in t_guild.items():
                    if t_member.member and t_member.guild.get_member(t_member.member.id):
                        t_future = asyncio.run_coroutine_threadsafe(t_member.update(), loop=loop)
                        try:
                            t_future.result()
                        except Exception as e:
                            print(e)
                    else:
                        t_lst.append(k1)
                for k1 in t_lst:
                    t_guild.pop(k1)

