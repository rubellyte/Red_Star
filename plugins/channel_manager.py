from plugin_manager import BasePlugin
from discord import utils
from discord.enums import ChannelType
from utils import respond, Command, DotDict


class ChannelManager(BasePlugin):
    name = "channel_manager"

    async def activate(self):
        for server in self.client.servers:
            self._add_server(server)

    async def on_server_join(self, server):
        self._add_server(server)

    def _add_server(self, server):
        if server.id not in self.plugin_config:
            self.plugin_config[server.id] = DotDict({
                "default": server.default_channel.id
            })
            if server.afk_channel:
                self.plugin_config[server.id].voice_afk = server.afk_channel.id
            self.config_manager.save_config()

    def get_channel(self, server, type):
        if server.id not in self.plugin_config:
            self._add_server(server)
        if type.lower() in self.plugin_config[server.id]:
            chan = self.plugin_config[server.id][type.lower()]
            return self.client.get_channel(chan)
        else:
            self.plugin_config[server.id][type.lower()] = None
            return None

    def set_channel(self, server, type, channel):
        if server.id not in self.plugin_config:
            self._add_server(server)
        self.plugins[server.id][type.lower()] = channel.id
        self.config_manager.save_config()

    @Command("get_channel",
             doc="Gets information on the specified channel type (or all channel types if none specified) in this "
                 "server.",
             syntax="[channel type]",
             category="bot_management",
             perms={"manage_server"})
    async def _get_channel_cmd(self, data):
        chantype = " ".join(data.clean_content.split()[1:]).lower()
        if data.server.id not in self.plugin_config:
            self._add_server(data.server)
        if chantype:
            try:
                chan = self.client.get_channel(self.plugin_config[data.server.id][chantype])
                if chan:
                    await respond(self.client, data, f"**ANALYSIS: The {chantype} channel for this server is "
                                                     f"{chan.mention}.**")
                else:
                    await respond(self.client, data, f"**WARNING: The {chantype} channel for this server is "
                                                     f"invalid.**")
            except KeyError:
                await respond(self.client, data, f"**ANALYSIS: No channel of type {chantype} set for this server.**")
        else:
            self.logger.debug(self.plugin_config[data.server.id])
            chantypes = "\n".join([f"{x.capitalize()}: {self.client.get_channel(y).name}"
                                   for x, y in self.plugin_config[data.server.id].items() if y is not None])
            await respond(self.client, data, f"**ANALYSIS: Channel types for this server:**```\n{chantypes}```")

    @Command("set_channel",
             doc="Sets the specified channel type to the specified channel for this server.",
             syntax="(chantype) (channel)",
             category="bot_management",
             perms={"manage_server"},
             run_anywhere=True)
    async def _set_channel_cmd(self, data):
        try:
            chantype = data.clean_content.split()[1].lower()
        except IndexError:
            raise SyntaxError("No channel type provided.")
        if chantype.startswith("voice"):
            channel = data.clean_content.split()[2].lower()
            channel = utils.find(lambda x: x.type == ChannelType.voice and x.name.lower() == channel,
                                 data.server.channels)
            if not channel:
                raise SyntaxError(f"Voice channel {data.clean_content.split()[2].lower()} not found.")
        else:
            try:
                channel = data.channel_mentions[0]
            except IndexError:
                raise SyntaxError("No channel provided.")
        if data.server.id not in self.plugin_config:
            self._add_server(data.server)
        self.plugin_config[data.server.id][chantype] = channel.id
        self.config_manager.save_config()
        await respond(self.client, data, f"**ANALYSIS: The {chantype} channel for this server has been set to "
                                         f"{channel.mention}.**")
