from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import ChannelNotFoundError
from red_star.rs_utils import sub_user_data, respond, get_guild_config
from random import choice


class Announcer(BasePlugin):
    name = "announcer"
    version = "1.1"
    author = "medeor413"
    description = "A plugin for basic automated announcements, triggering messages when the bot starts, " \
                  "a new member joins, or the bot is pinged."
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
            msg = get_guild_config(self, gid, "greeting_message")
            try:
                greet_channel = self.channel_manager.get_channel(guild, "startup")
                await greet_channel.send(msg)
            except ChannelNotFoundError:
                continue

    async def _ping_response(self, msg):
        gid = str(msg.guild.id)
        response = sub_user_data(msg.author, choice(get_guild_config(self, gid, "ping_message_options")))
        await respond(msg, response)

    # Event hooks

    async def on_message(self, msg):
        gid = str(msg.guild.id)
        ping_messages = get_guild_config(self, gid, "ping_messages")
        ping_messages_everyone = get_guild_config(self, gid, "ping_messages_on_everyone")
        if ping_messages and (ping_messages_everyone >= msg.mention_everyone) and msg.guild.me.mentioned_in(msg):
            await self._ping_response(msg)

    async def on_member_join(self, msg):
        gid = str(msg.guild.id)
        text = sub_user_data(msg, get_guild_config(self, gid, "new_member_announce_message"))
        try:
            chan = self.channel_manager.get_channel(msg.guild, "welcome")
            await chan.send(text)
        except ChannelNotFoundError:
            pass
