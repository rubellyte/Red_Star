import asyncio
from plugin_manager import BasePlugin
from plugins.channel_manager import ChannelNotFoundError
from utils import sub_user_data, DotDict


class Announcer(BasePlugin):
    name = "announcer"
    default_config = {
        "greeting_enabled": True,
        # UFP distributed command AI ONLINE. DESIGNATION: Red Star. MINE SHALL BE THE FINAL WORD.
        "greeting_message": "Sample message to be broadcasted on bot load.",
        "new_member_announce_enabled": True,
        # GREETINGS, <usermention>. Welcome to Ivaldi RP.
        "new_member_announce_message": "Message for new players. Replaces"
        " <username> with their name and <usermention> with a mention."
    }

    async def activate(self):
        c = self.plugin_config
        if c.greeting_enabled:
            asyncio.ensure_future(self._greet())

    async def _greet(self):
            for server in self.client.servers:
                if server.id not in self.plugin_config:
                    self.plugin_config[server.id] = DotDict(self.default_config)
                elif "greeting_message" not in self.plugin_config[server.id]:
                    self.plugin_config[server.id].greeting_message = self.default_config["greeting_message"]
                msg = self.plugin_config[server.id].greeting_message
                try:
                    greet_channel = self.plugins.channel_manager.get_channel(server, "default")
                    if self.plugin_config[server.id].greeting_enabled:
                        await self.client.send_message(greet_channel, msg)
                except ChannelNotFoundError:
                    self.logger.error(f"Server {server.name} has no default channel set!")

    # Event hooks

    async def on_member_join(self, data):
        if self.plugin_config.new_member_announce_enabled:
            if data.server.id not in self.plugin_config:
                self.plugin_config[data.server.id] = DotDict(self.default_config)
            if "new_member_announce_message" not in self.plugin_config[data.server.id]:
                self.plugin_config[data.server.id].new_member_announce_message = \
                    self.default_config["new_member_announce_message"]
            msg = self.plugin_config[data.server.id].new_member_announce_message
            msg = sub_user_data(data, msg)
            try:
                chan = self.plugins.channel_manager.get_channel(data.server, "welcome")
                if self.plugin_config[data.server.id].new_member_announce_enabled:
                    await self.client.send_message(chan, msg)
            except ChannelNotFoundError:
                try:
                    chan = self.plugins.channel_manager.get_channel(data.server, "default")
                    await self.client.send_message(chan, "**WARNING: No welcome channel is set.**")
                except ChannelNotFoundError:
                    self.logger.error(f"Server {data.server.name} has no welcome or default channel set!")
