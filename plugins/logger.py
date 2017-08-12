import asyncio
from plugin_manager import BasePlugin
from plugins.channel_manager import ChannelNotFoundError
from utils import split_message


class DiscordLogger(BasePlugin):
    name = "logger"
    default_config = {
        "default": {
            "log_events": [
                "message_delete",
                "message_edit",
                "member_join",
                "member_remove"
            ]
        }
    }

    async def activate(self):
        self.log_items = {}
        self.active = True
        asyncio.ensure_future(self._dump_logs())

    async def deactivate(self):
        self.active = False

    async def _dump_logs(self):
        while self.active:
            await asyncio.sleep(1)
            for guild in self.client.guilds:
                gid = str(guild.id)
                try:
                    logchan = self.plugins.channel_manager.get_channel(guild, "logs")
                except ChannelNotFoundError:
                    continue
                if gid in self.log_items and self.log_items[gid]:
                    logs = "\n".join(self.log_items[gid])
                    for msg in split_message(logs, splitter="\n"):
                        await logchan.send(msg)
                    self.log_items[gid] = []



    async def on_message_delete(self, msg):
        gid = str(msg.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "message_delete" in self.plugin_config[gid].log_events and msg.author != self.client.user:
            uname = str(msg.author)
            contents = msg.clean_content
            attaches = ""
            links = ""
            if msg.attachments:
                self.logger.debug(msg.attachments)
                links = ", ".join([x.url for x in msg.attachments])
                attaches = f"\n**Attachments:** `{links}`"
            self.logger.debug(f"User {uname}'s message in {msg.channel.name} was deleted.\nContents: {contents}\n"
                              f"Attachments: {links}")
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**WARNING: User {uname}'s message in {msg.channel.mention} was deleted. "
                                       f"ANALYSIS: Contents:**\n{contents}{attaches}")

    async def on_message_edit(self, before, after):
        gid = str(after.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "message_edit" in self.plugin_config[gid].log_events and after.author != self.client.user:
            uname = str(after.author)
            old_contents = before.clean_content
            contents = after.clean_content
            if old_contents == contents:
                return
            self.logger.debug(f"User {uname} edited their message in {after.channel.name}. \n"
                              f"Old contents: {old_contents}\nNew contents: {contents}")
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**WARNING: User {uname} edited their message in {after.channel.mention}. "
                                       f"ANALYSIS:**\n**Old contents:** {old_contents}\n**New contents:** {contents}")

    async def on_member_join(self, member):
        gid = str(member.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "member_join" in self.plugin_config[gid].log_events:
            uname = str(member)
            self.logger.debug(f"User {uname} joined {member.guild.name}.")
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**NEW USER DETECTED: {uname}.**")

    async def on_member_remove(self, member):
        gid = str(member.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "member_remove" in self.plugin_config[gid].log_events:
            uname = str(member)
            self.logger.debug(f"User {uname} left {member.guild.name}.")
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**WARNING: User {uname} has left the server.**")
