import asyncio
from plugin_manager import BasePlugin
from utils import sub_user_data


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
            msg = self.plugin_config.greeting_message
            for server in self.client.servers:
                greet_channel = self.plugins.channel_manager.get_channel(server, "default")
                await self.client.send_message(greet_channel, msg)

    # Event hooks

    async def on_member_join(self, data):
        if self.plugin_config.new_member_announce_enabled:
            msg = self.plugin_config.new_member_announce_message
            msg = sub_user_data(data, msg)
            chan = self.plugins.channel_manager.get_channel(data.server, "welcome")
            await self.client.send_message(chan, msg)
