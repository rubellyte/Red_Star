from plugin_manager import BasePlugin
from rs_errors import ChannelNotFoundError
from rs_utils import sub_user_data, DotDict, respond
from random import choice


class Announcer(BasePlugin):
    name = "announcer"
    default_config = {
        "default": {
            "greeting_message": "Sample message to be broadcasted on bot load.",
            "new_member_announce_message": "Message for new players. Replaces <username> with their name and "
                                           "<usermention> with a mention.",
            "ping_messages": True,
            "ping_messages_on_everyone": False,
            "ping_message_options": [
                "**STOP**",
                "***STOP THIS AT ONCE!***",
                "**CEASE**",
                "***CEASE THIS AT ONCE!***",
                "**DO NOT**",
                "**HOW** ***DARE*** **YOU!**",
                "**`soft crying`**",
                "**DO NOT PING THE ROBOT!**",
                "**STOP PINGING ME!**",
                "**`INTERNAL SCREAMING`**",
                "**`EXTERNAL SCREAMING`**",
                "**`INTERNAL AND EXTERNAL SCREAMING`**"
            ]
        }
    }

    async def on_all_plugins_loaded(self):
        await self._greet()

    async def _greet(self):
        for guild in self.client.guilds:
            gid = str(guild.id)
            if gid not in self.plugin_config:
                self.plugin_config[gid] = DotDict(self.default_config["default"])
                self.config_manager.save_config()
            elif "greeting_message" not in self.plugin_config[gid]:
                self.plugin_config[gid].greeting_message = self.default_config["default"]["greeting_message"]
                self.config_manager.save_config()
            msg = self.plugin_config[gid].greeting_message
            try:
                greet_channel = self.channel_manager.get_channel(guild, "startup")
                await greet_channel.send(msg)
            except ChannelNotFoundError:
                continue

    async def _ping_response(self, msg):
        gid = str(msg.guild.id)
        response = choice(self.plugin_config[gid].ping_message_options)
        await respond(msg, response)


    # Event hooks

    async def on_message(self, msg):
        gid = str(msg.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = DotDict(self.default_config["default"])
            self.config_manager.save_config()
        elif "ping_messages" not in self.plugin_config[gid]:
            self.plugin_config[gid].ping_messages = self.default_config["default"]["ping_messages"]
            self.plugin_config[gid].ping_messages_on_everyone = self.default_config["default"][
                "ping_messages_on_everyone"]
            self.plugin_config[gid].ping_message_options = self.default_config["default"]["ping_message_options"]
            self.config_manager.save_config()
        if self.plugin_config[gid].ping_messages and (self.plugin_config[gid].ping_messages_on_everyone >=
                                                      msg.mention_everyone) and msg.guild.me.mentioned_in(msg):
            await self._ping_response(msg)


    async def on_member_join(self, msg):
        gid = str(msg.guild.id)
        if self.plugin_config[gid].new_member_announce_enabled:
            if gid not in self.plugin_config:
                self.plugin_config[gid] = DotDict(self.default_config["default"])
                self.config_manager.save_config()
            if "new_member_announce_message" not in self.plugin_config[gid]:
                self.plugin_config[gid].new_member_announce_message = \
                    self.default_config["default"]["new_member_announce_message"]
                self.config_manager.save_config()
            text = self.plugin_config[gid].new_member_announce_message
            text = sub_user_data(msg, text)
            try:
                chan = self.channel_manager.get_channel(msg.guild, "welcome")
                await chan.send(text)
            except ChannelNotFoundError:
                pass
