import asyncio
from plugin_manager import BasePlugin


class DiscordLogger(BasePlugin):
    name = "logger"
    default_config = {
        "log_events": [
            "message_delete",
            "message_edit",
            "member_join",
            "member_remove"
        ],
        "log_channel": "CHANNEL ID HERE"
    }

    async def activate(self):
        self.log_events = self.plugin_config.log_events

    async def on_message_delete(self, msg):
        if "message_delete" in self.log_events and msg.author != self.client.user:
            log_channel = self.plugins.channel_manager.get_channel(msg.server, "logs")
            uname = str(msg.author)
            contents = msg.clean_content
            self.logger.debug(f"User {uname}'s message in {msg.channel.name} was deleted. Contents: {contents}")
            await self.client.send_message(log_channel,
                                           f"**WARNING: User {uname}'s message in {msg.channel.mention} was deleted. "
                                           f"ANALYSIS: Contents:**\n{contents}")

    async def on_message_edit(self, before, after):
        if "message_edit" in self.log_events and after.author != self.client.user:
            log_channel = self.plugins.channel_manager.get_channel(after.server, "logs")
            uname = str(after.author)
            old_contents = before.clean_content
            contents = after.clean_content
            if old_contents == contents:
                return
            self.logger.debug(f"User {uname} edited their message in {after.channel.name}. \n"
                              f"Old contents: {old_contents}\nNew contents: {contents}")
            await self.client.send_message(log_channel,
                                           f"**WARNING: User {uname} edited their message in {after.channel.mention}. "
                                           f"ANALYSIS:**\n**Old contents:** {old_contents}\n"
                                           f"**New contents:** {contents}")

    async def on_member_join(self, user):
        if "member_join" in self.log_events:
            log_channel = self.plugins.channel_manager.get_channel(user.server, "logs")
            uname = str(user)
            self.logger.debug(f"User {uname} joined {user.server.name}.")
            await self.client.send_message(log_channel, f"**NEW USER DETECTED: {uname}.**")

    async def on_member_remove(self, user):
        if "member_remove" in self.log_events:
            log_channel = self.plugins.channel_manager.get_channel(user.server, "logs")
            uname = str(user)
            self.logger.debug(f"User {uname} left {user.server.name}.")
            await self.client.send_message(log_channel, f"**User {uname} has left the server.**")
