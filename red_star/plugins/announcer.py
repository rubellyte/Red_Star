import discord
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import ChannelNotFoundError
from red_star.rs_utils import sub_user_data, respond
from random import choice


class Announcer(BasePlugin):
    name = "announcer"
    version = "1.1"
    author = "medeor413"
    description = "A plugin for basic automated announcements, triggering messages when the bot starts, " \
                  "a new member joins, or the bot is pinged."
    default_config = {
        "greeting_message": "**RED STAR IS ONLINE.**",
        "new_member_announce_message": "**Welcome to the server, <@usermention>.**",
        "ping_messages": True,
        "ping_messages_on_everyone": False,
        "ping_message_options": [
            "**NEGATIVE**",
            "**AFFIRMATIVE**",
            "**WARNING: Does not compute.**",
            "**ANALYSIS: Maybe.**"
        ]
    }
    channel_types = {"startup", "welcome"}

    async def on_all_plugins_loaded(self):
        await self._greet()

    async def _greet(self):
        try:
            greet_channel = self.channel_manager.get_channel("startup")
            await greet_channel.send(self.config["greeting_message"])
        except ChannelNotFoundError:
            pass

    async def _ping_response(self, msg: discord.Message):
        response = sub_user_data(msg.author, choice(self.config["ping_message_options"]))
        await respond(msg, response)

    # Event hooks

    async def on_message(self, msg: discord.Message):
        ping_messages = self.config["ping_messages"]
        ping_messages_everyone = self.config["ping_messages_on_everyone"]
        if ping_messages and (ping_messages_everyone >= msg.mention_everyone) and msg.guild.me.mentioned_in(msg):
            await self._ping_response(msg)

    async def on_member_join(self, member: discord.Member):
        text = sub_user_data(member, self.config["new_member_announce_message"])
        try:
            chan = self.channel_manager.get_channel("welcome")
            await chan.send(text)
        except ChannelNotFoundError:
            pass
