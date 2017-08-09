from plugin_manager import BasePlugin
from discord import utils
from discord.enums import ChannelType
from utils import respond, Command, DotDict


class ChannelNotFoundError(TypeError):
    pass


class ChannelManager(BasePlugin):
    name = "channel_manager"

    async def activate(self):
        for guild in self.client.guilds:
            self._add_guild(guild)

    async def on_guild_join(self, guild):
        self._add_guild(guild)

    def _add_guild(self, guild):
        gid = str(guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = DotDict({})
            if guild.afk_channel:
                self.plugin_config[gid].voice_afk = guild.afk_channel.id
            self.config_manager.save_config()

    def get_channel(self, guild, type):
        gid = str(guild.id)
        if gid not in self.plugin_config:
            self._add_guild(guild)
        if type.lower() in self.plugin_config[gid]:
            chan = self.plugin_config[gid][type.lower()]
            chan = self.client.get_channel(chan)
            if not chan:
                raise ChannelNotFoundError(type.lower())
            return chan
        else:
            raise ChannelNotFoundError(type.lower())

    def set_channel(self, guild, type, channel):
        gid = str(guild.id)
        if gid not in self.plugin_config:
            self._add_guild(guild)
        self.plugins[gid][type.lower()] = channel.id
        self.config_manager.save_config()

    @Command("get_channel",
             doc="Gets information on the specified channel type (or all channel types if none specified) in this "
                 "server.",
             syntax="[channel type]",
             category="bot_management",
             perms={"manage_guild"})
    async def _get_channel_cmd(self, msg):
        gid = str(msg.guild.id)
        chantype = " ".join(msg.clean_content.split()[1:]).lower()
        if gid not in self.plugin_config:
            self._add_guild(msg.guild)
        if chantype:
            try:
                chan = self.client.get_channel(self.plugin_config[gid][chantype])
                if chan:
                    await respond(msg, f"**ANALYSIS: The {chantype} channel for this server is {chan.mention}.**")
                else:
                    await respond(msg, f"**WARNING: The {chantype} channel for this server is invalid.**")
            except KeyError:
                await respond(msg, f"**ANALYSIS: No channel of type {chantype} set for this server.**")
        else:
            chantypes = "\n".join([f"{x.capitalize()}: {self.client.get_channel(y).name}"
                                   for x, y in self.plugin_config[gid].items() if y is not None])
            await respond(msg, f"**ANALYSIS: Channel types for this server:**```\n{chantypes}```")

    @Command("set_channel",
             doc="Sets the specified channel type to the specified channel for this server.",
             syntax="(chantype) (channel)",
             category="bot_management",
             perms={"manage_guild"},
             run_anywhere=True)
    async def _set_channel_cmd(self, msg):
        try:
            chantype = msg.clean_content.split()[1].lower()
        except IndexError:
            raise SyntaxError("No channel type provided.")
        if chantype.startswith("voice"):
            channel = msg.clean_content.split()[2].lower()
            channel = utils.find(lambda x: x.type == ChannelType.voice and x.name.lower() == channel,
                                 msg.guild.channels)
            if not channel:
                raise SyntaxError(f"Voice channel {msg.clean_content.split()[2].lower()} not found.")
        else:
            try:
                channel = msg.channel_mentions[0]
            except IndexError:
                raise SyntaxError("No channel provided.")
        gid = str(msg.guild.id)
        if gid not in self.plugin_config:
            self._add_guild(msg.guild)
        self.plugin_config[gid][chantype] = channel.id
        self.config_manager.save_config()
        await respond(msg, f"**ANALYSIS: The {chantype} channel for this server has been set to {channel.mention}.**")
