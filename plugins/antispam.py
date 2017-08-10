from plugin_manager import BasePlugin
from utils import Command, respond
from discord import HTTPException
import time
import re

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
        }
    }

    async def activate(self):
        self.run_timer = True
        self.members = {}
        if "muted_members" not in self.storage:
            self.storage["muted_members"] = {}
        for guild in self.client.guilds:
            self.members[guild.id] = {}
            if str(guild.id) not in self.storage["muted_members"]:
                self.storage["muted_members"][str(guild.id)] = {}
            if str(guild.id) not in self.plugin_config:
                self.plugin_config[str(guild.id)] = self.plugin_config["default"]


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

        if msg.author.id in self.members[msg.guild.id]:
            t_member = self.members[msg.guild.id][msg.author.id]
            t_config = self.plugin_config[str(msg.guild.id)]
            if time.time() - t_member[0] < t_config["timeout"]:
                t_member[1] += 1
                if t_member[1] > t_config["message_count"]:
                    if t_config["spam_reaction"]:
                        if len(t_config["spam_reaction"]) != 18:
                            try:
                                await msg.add_reaction(t_config["spam_reaction"])
                            except HTTPException:
                                self.logger.error(f"Non-emoji character set as spam reaction on server {msg.guild.id}")
                        else:
                            await msg.add_reaction(self.client.get_emoji(int(t_config["spam_reaction"])))
                    if t_config["spam_delete"]:
                        await msg.delete(reason="Spam filtering.")
                    t_member[0] = time.time()
            else:
                t_member[1] = 1
                t_member[0] = time.time()
        else:
            self.members[msg.guild.id][msg.author.id] = [time.time(), 1]

    # Commands

    @Command("getmoji")
    async def _getmoji(self, msg):
        args = msg.content.split()
        if len(args) > 1:
            if len(args[1]) == 1:
                self.plugin_config[str(msg.guild.id)]["spam_reaction"] = args[1]
            elif re.fullmatch("<:\w{1,32}:\d{18}>", args[1]):
                t_emoji = re.search("\d{18}", args[1])[0]
                if self.client.get_emoji(int(t_emoji)):
                    self.plugin_config[str(msg.guild.id)]["spam_reaction"] = t_emoji
        else:
            raise SyntaxError("Expected an emoji as argument.")
