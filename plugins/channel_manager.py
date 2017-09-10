from plugin_manager import BasePlugin
from discord import utils, VoiceChannel
from rs_utils import respond, Command, DotDict
from rs_errors import ChannelNotFoundError, CommandSyntaxError
import shlex


class ChannelManager(BasePlugin):
    name = "channel_manager"
    default_config = {
        "default": {
            "channels": {},
            "categories": {}
        }
    }

    async def activate(self):
        for guild in self.client.guilds:
            self._add_guild(guild)
        if "_version" not in self.plugin_config:
            self._update_config()

    async def on_guild_join(self, guild):
        self._add_guild(guild)

    def _update_config(self):
        for gid, conf in self.plugin_config.items():
            old_conf = dict(conf)
            conf["channels"] = {}
            conf["categories"] = {}
            for i, v in old_conf.items():
                if i not in ("channels", "categories"):
                    conf["channels"][i] = v
                    del conf[i]
        self.logger.debug(self.plugin_config)
        self.plugin_config._version = 2
        self.config_manager.save_config()

    def _add_guild(self, guild):
        gid = str(guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = DotDict(self.default_config["default"])
            if guild.afk_channel:
                self.plugin_config[gid].channels.voice_afk = guild.afk_channel.id
            self.config_manager.save_config()

    def get_channel(self, guild, chantype):
        gid = str(guild.id)
        chantype = chantype.lower()
        if gid not in self.plugin_config:
            self._add_guild(guild)
        if chantype in self.plugin_config[gid].channels:
            chan = self.plugin_config[gid].channels[chantype]
            chan = self.client.get_channel(chan)
            if not chan:
                raise ChannelNotFoundError(chantype)
            return chan
        else:
            raise ChannelNotFoundError(chantype)

    def set_channel(self, guild, chantype, channel):
        gid = str(guild.id)
        chantype = chantype.lower()
        if gid not in self.plugin_config:
            self._add_guild(guild)
        if channel:
            self.plugin_config[gid].channels[chantype] = channel.id
            self.config_manager.save_config()
        elif chantype in self.plugin_config[gid].channels:
            self.plugin_config[gid].channels.pop(chantype)
            self.config_manager.save_config()

    def register_category(self, guild, category):
        gid = str(guild.id)
        category = category.lower()
        if category not in self.plugin_config[gid].categories:
            self.plugin_config[gid]["categories"][category] = []

    def channel_in_category(self, guild, category, channel):
        gid = str(guild.id)
        category = category.lower()
        if category not in self.plugin_config[gid].categories:
            return False
        if channel.id not in self.plugin_config[gid]["categories"][category]:
            return False
        return True

    def add_channel_to_category(self, guild, category, channel):
        gid = str(guild.id)
        category = category.lower()
        if category not in self.plugin_config[gid].categories:
            self.plugin_config[gid].categories[category] = [channel.id]
        elif category not in self.plugin_config[gid].categories[category]:
            self.plugin_config[gid].categories[category].append(channel.id)

    def remove_channel_from_category(self, guild, category, channel):
        gid = str(guild.id)
        category = category.lower()
        if category not in self.plugin_config[gid].categories:
            return False
        elif channel.id not in self.plugin_config[gid].categories[category]:
            return False
        else:
            self.plugin_config[gid].categories[category].remove(channel.id)
            return True

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
                chan = self.client.get_channel(self.plugin_config[gid].channels[chantype])
                if chan:
                    await respond(msg, f"**ANALYSIS: The {chantype} channel for this server is {chan.mention}.**")
                else:
                    await respond(msg, f"**WARNING: The {chantype} channel for this server is invalid.**")
            except KeyError:
                await respond(msg, f"**ANALYSIS: No channel of type {chantype} set for this server.**")
        else:
            chantypes = "\n".join([f"{x.capitalize()}: {self.client.get_channel(y).name}"
                                   for x, y in self.plugin_config[gid].channels.items() if y is not None])
            await respond(msg, f"**ANALYSIS: Channel types for this server:**```\n{chantypes}```")

    @Command("set_channel",
             doc="Sets the specified channel type to the specified channel for this server or disables it.\n"
                 "Use channel mention for text channels or channel name for voice channels.\n"
                 "Voice channel types must be prefixed by \"Voice\".",
             syntax="(chantype) [channel]",
             category="bot_management",
             perms={"manage_guild"},
             run_anywhere=True)
    async def _set_channel_cmd(self, msg):
        args = shlex.split(msg.content)

        if len(args) > 1:
            chantype = args[1].lower()
        else:
            raise CommandSyntaxError("No channel type provided.")

        if len(args) > 2:
            if chantype.startswith("voice"):
                channel = args[2].lower()
                channel = utils.find(lambda x: isinstance(x, VoiceChannel) and x.name.lower() == channel,
                                     msg.guild.channels)
                if not channel:
                    raise CommandSyntaxError(f"Voice channel {args[2].lower()} not found.")
            else:
                if msg.channel_mentions:
                    channel = msg.channel_mentions[0]
                else:
                    raise CommandSyntaxError("No channel provided.")
        else:
            channel = None

        self.set_channel(msg.guild, chantype, channel)

        if channel:
            await respond(msg, f"**ANALYSIS: The {chantype} channel for this server has been set to "
                               f"{channel.mention}.**")
        else:
            await respond(msg, f"ANALYSIS: The {chantype} channel for this server has been disabled.")

    @Command("get_category",
             doc="Gets the members of the specified channel category on this server.",
             syntax="[category]",
             category="bot_management",
             perms={"manage_guild"})
    async def _get_category(self, msg):
        gid = str(msg.guild.id)
        category = " ".join(msg.clean_content.split()[1:]).lower()
        if gid not in self.plugin_config:
            self._add_guild(msg.guild)
        if category:
            if category in self.plugin_config[gid].categories:
                catestr = ", ".join([msg.guild.get_channel(x).name for x in self.plugin_config[gid].categories[
                    category]])
                await respond(msg, f"**ANALYSIS: Category {category} contains the following channels:**\n"
                                   f"```{catestr}```")
            else:
                await respond(msg, f"**ANALYSIS: No such category {category}.**")
        else:
            catestr = "\n".join(self.plugin_config[gid].categories.keys())
            await respond(msg, f"**ANALYSIS: Available categories:**\n```{catestr}```")

    @Command("add_to_category",
             doc="Adds the given channel to the specified category for this server.\n"
                 "Use channel mention for text channels or channel name for voice channels.\n"
                 "Voice channel categories must be prefixed by \"voice\".",
             syntax="(category) (channel)",
             category="bot_management",
             perms={"manage_guild"})
    async def _add_to_category(self, msg):
        args = shlex.split(msg.content)
        if len(args) > 1:
            category = args[1].lower()
        else:
            raise CommandSyntaxError("No category provided.")

        if len(args) > 2:
            if category.startswith("voice"):
                channel = args[2].lower()
                channel = utils.find(lambda x: isinstance(x, VoiceChannel) and x.name.lower() == channel,
                                     msg.guild.channels)
                if not channel:
                    raise CommandSyntaxError(f"Voice channel {args[2].lower()} not found.")
            else:
                if msg.channel_mentions:
                    channel = msg.channel_mentions[0]
                else:
                    raise CommandSyntaxError("No channel provided.")

            self.add_channel_to_category(msg.guild, category, channel)

            await respond(msg, f"**ANALYSIS: Channel {channel.mention} was added to category {category}.**")
        else:
            raise CommandSyntaxError("No channel provided.")

    @Command("rm_from_category",
             doc="Removes the given channel from the specified category from the server.\n"
                 "Use channel mention for text channels or channel name for voice channels.\n"
                 "Voice channel categories must be prefixed by \"voice\".",
             syntax="(category) (channel)",
             category="bot_management",
             perms={"manage_guild"})
    async def _rm_from_category(self, msg):
        args = shlex.split(msg.content)
        if len(args) > 1:
            category = args[1].lower()
        else:
            raise CommandSyntaxError("No category provided.")

        if len(args) > 2:
            if category.startswith("voice"):
                channel = args[2].lower()
                channel = utils.find(lambda x: isinstance(x, VoiceChannel) and x.name.lower() == channel,
                                     msg.guild.channels)
                if not channel:
                    raise CommandSyntaxError(f"Voice channel {args[2].lower()} not found.")
            else:
                if msg.channel_mentions:
                    channel = msg.channel_mentions[0]
                else:
                    raise CommandSyntaxError("No channel provided.")

            success = self.remove_channel_from_category(msg.guild, category, channel)
            if success:
                await respond(msg, f"**ANALYSIS: Channel {channel.mention} was removed from category {category}.**")
            else:
                await respond(msg, f"**ANALYSIS: Channel {channel.mention} is not in category {category}.**")
        else:
            raise CommandSyntaxError("No channel provided.")
