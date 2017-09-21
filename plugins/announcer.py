from plugin_manager import BasePlugin
from rs_errors import ChannelNotFoundError
from rs_utils import sub_user_data, DotDict


class Announcer(BasePlugin):
    name = "announcer"
    default_config = {
        "default": {
            "greeting_enabled": True,
            # UFP distributed command AI ONLINE. DESIGNATION: Red Star. MINE SHALL BE THE FINAL WORD.
            "greeting_message": "Sample message to be broadcasted on bot load.",
            "new_member_announce_enabled": True,
            # GREETINGS, <usermention>. Welcome to Ivaldi RP.
            "new_member_announce_message": "Message for new players. Replaces <username> with their name and "
                                           "<usermention> with a mention."
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
                    greet_channel = self.channel_manager.get_channel(guild, "general")
                    if self.plugin_config[gid].greeting_enabled:
                        await greet_channel.send(msg)
                except ChannelNotFoundError as e:
                    self.logger.error(f"Server {guild.name} has no {e} channel set!")

    # Event hooks

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
                if self.plugin_config[gid].new_member_announce_enabled:
                    await chan.send(text)
            except ChannelNotFoundError:
                try:
                    chan = self.channel_manager.get_channel(msg.guild, "general")
                    await chan.send("**WARNING: No welcome channel is set.**")
                except ChannelNotFoundError:
                    self.logger.error(f"Server {msg.guild.name} has no welcome or default channel set!")
