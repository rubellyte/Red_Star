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

    def activate(self):
        self.log_events = self.plugin_config.log_events
        self.log_channel = None
        asyncio.ensure_future(self.get_channels())

    async def get_channels(self):
        while not self.log_channel:
            self.log_channel = self.client.get_channel(self.plugin_config.log_channel)
            await asyncio.sleep(0.5)

    async def on_message_delete(self, msg):
        if "message_delete" in self.log_events and msg.author != self.client.user:
            uname = f"{msg.author.name}#{msg.author.discriminator}"
            contents = msg.clean_content
            self.logger.debug(f"User {uname}'s message was deleted. Contents: {contents}")
            await self.client.send_message(self.log_channel,
                                           f"**WARNING: User {uname}'s message was deleted. ANALYSIS: "
                                           f"Contents:**\n{contents}")

    async def on_message_edit(self, before, after):
        if "message_edit" in self.log_events and after.author != self.client.user:
            uname = f"{after.author.name}#{after.author.discriminator}"
            old_contents = before.clean_content
            contents = after.clean_content
            if old_contents == contents:
                return
            self.logger.debug(f"User {uname} edited their message.\nOld contents: {old_contents}\nNew contents: "
                              f"{contents}")
            await self.client.send_message(self.log_channel,
                                           f"**WARNING: User {uname} edited their message. ANALYSIS:**\n**Old "
                                           f"contents:** {old_contents}\n**New contents:** {contents}")

    async def on_member_join(self, user):
        if "member_join" in self.log_events:
            uname = f"{user.name}#{user.discriminator}"
            self.logger.debug(f"User {uname} joined the server.")
            await self.client.send_message(self.log_channel, f"**NEW USER DETECTED: {uname}.**")

    async def on_member_remove(self, user):
        if "member_remove" in self.log_events:
            uname = f"{user.name}#{user.discriminator}"
            self.logger.debug(f"User {uname} left the server.")
            await self.client.send_message(self.log_channel, f"**User {uname} has left the server.**")
