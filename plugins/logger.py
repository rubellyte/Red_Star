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

    @asyncio.coroutine
    def get_channels(self):
        while not self.log_channel:
            self.log_channel = self.client.get_channel(self.plugin_config.log_channel)
            yield from asyncio.sleep(0.5)

    def on_message_delete(self, msg):
        if "message_delete" in self.log_events and msg.author != self.client.user:
            uname = "{}#{}".format(msg.author.name, msg.author.discriminator)
            contents = msg.clean_content
            self.logger.debug("User {}'s message was deleted. Contents: {}".format(uname, contents))
            yield from self.client.send_message(self.log_channel,
                                                "**WARNING: User {}s message was deleted. ANALYSIS: Contents:**\n{}"
                                                .format(uname, contents))

    def on_message_edit(self, before, after):
        if "message_edit" in self.log_events and after.author != self.client.user:
            uname = "{}#{}".format(after.author.name, after.author.discriminator)
            old_contents = before.clean_content
            contents = after.clean_content
            self.logger.debug("User {} edited their message.\nOld contents: {}\nNew contents: {}"
                              .format(uname, old_contents, contents))
            yield from self.client.send_message(self.log_channel,
                                                "**WARNING: User {} edited their message. ANALYSIS:**\n**Old contents:** {}\n"
                                                "**New contents:** {}".format(uname, old_contents, contents))

    def on_member_join(self, user):
        if "member_join" in self.log_events:
            uname = "{}#{}".format(user.name, user.discriminator)
            self.logger.debug("User {} joined the server.".format(uname))
            yield from self.client.send_message(self.log_channel, "**NEW USER DETECTED: {}.**".format(uname))

    def on_member_remove(self, user):
        if "member_remove" in self.log_events:
            uname = "{}#{}".format(user.name, user.discriminator)
            self.logger.debug("User {} left the server.".format(uname))
            yield from self.client.send_message(self.log_channel, "**User {} has left the server.**".format(uname))
