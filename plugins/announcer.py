import asyncio
from plugin_manager import BasePlugin
from utils import sub_user_data


class Announcer(BasePlugin):
    name = "announcer"
    default_config = {
        "greeting_enabled": True,
        #UFP distributed command AI ONLINE. DESIGNATION: Red Star. MINE SHALL BE THE FINAL WORD.
        "greeting_message": "Sample message to be broadcasted on bot load.", 
        "greeting_channel": "CHANNEL ID AS STRING",
        "new_member_announce_enabled": True,
        #GREETINGS, <usermention>. Welcome to Ivaldi RP.
        "new_member_announce_message": "Message for new players. Replaces"
        " <username> with their name and <usermention> with a mention.",
        "new_member_announce_channel": "CHANNEL ID AS STRING"
    }

    def activate(self):
        c = self.plugin_config
        if c.greeting_enabled:
            self.greet_channel = self.client.get_channel(c.greeting_channel)
            asyncio.ensure_future(self._greet())
        if c.new_member_announce_enabled:
            self.new_member_announce_channel = self.client.get_channel(c.new_member_announce_channel)

    @asyncio.coroutine
    def _greet(self):
            try:
                c = self.plugin_config
                yield from self.client.send_message(self.greet_channel, c.greeting_message)
            except TypeError:
                self.logger.error("Greeting channel invalid!")

    # Event hooks

    def on_member_join(self, data):
        if self.plugin_config.new_member_announce_enabled:
            c = self.plugin_config
            msg = c.new_member_announce_message
            msg = sub_user_data(data, msg)
            yield from self.client.send_message(self.new_member_announce_channel, msg)
