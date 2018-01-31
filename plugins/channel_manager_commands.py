from plugin_manager import BasePlugin
from discord import utils, VoiceChannel
from rs_utils import respond, DotDict
from command_dispatcher import Command
from rs_errors import ChannelNotFoundError, CommandSyntaxError
import shlex


class ChannelManagerCommands(BasePlugin):
    name = "channel_manager_commands"
    default_config = {}

    async def activate(self):
        self.chan_conf = self.config_manager.config.channel_manager

    @Command("GetChannel",
             doc="Gets information on the specified channel type (or all channel types if none specified) in this "
                 "server.",
             syntax="[channel type]",
             category="channel_management",
             perms={"manage_guild"})
    async def _get_channel_cmd(self, msg):
        gid = str(msg.guild.id)
        chantype = " ".join(msg.clean_content.split()[1:]).lower()
        if chantype:
            try:
                chan = self.channel_manager.get_channel(msg.guild, chantype)
                await respond(msg, f"**ANALYSIS: The {chantype} channel for this server is {chan.mention}.**")
            except ChannelNotFoundError:
                await respond(msg, f"**ANALYSIS: No channel of type {chantype} set for this server.**")
        else:
            chantypes = "\n".join([f"{x.capitalize()}: {self.client.get_channel(y).name}"
                                   for x, y in self.chan_conf[gid].channels.items() if y is not None])
            await respond(msg, f"**ANALYSIS: Channel types for this server:**```\n{chantypes}```")

    @Command("SetChannel",
             doc="Sets the specified channel type to the specified channel for this server or disables it.\n"
                 "Use channel mention for text channels or channel name for voice channels.\n"
                 "Voice channel types must be prefixed by \"Voice\".",
             syntax="(chantype) [channel]",
             category="channel_management",
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

        self.channel_manager.set_channel(msg.guild, chantype, channel)

        if channel:
            await respond(msg, f"**ANALYSIS: The {chantype} channel for this server has been set to "
                               f"{channel.mention}.**")
        else:
            await respond(msg, f"**ANALYSIS: The {chantype} channel for this server has been disabled.**")

    @Command("GetCategory",
             doc="Gets the members of the specified channel category on this server.",
             syntax="[category]",
             category="channel_management",
             perms={"manage_guild"})
    async def _get_category(self, msg):
        gid = str(msg.guild.id)
        category = " ".join(msg.clean_content.split()[1:]).lower()
        if category:
            if category in self.chan_conf[gid].categories:
                catestr = ", ".join([msg.guild.get_channel(x).name for x in self.chan_conf[gid].categories[
                    category]])
                await respond(msg, f"**ANALYSIS: Category {category} contains the following channels:**\n"
                                   f"```\n{catestr}```")
            else:
                await respond(msg, f"**ANALYSIS: No such category {category}.**")
        else:
            catestr = "\n".join(self.chan_conf[gid].categories.keys())
            await respond(msg, f"**ANALYSIS: Available categories:**\n```\n{catestr}```")

    @Command("AddToCategory",
             doc="Adds the given channel to the specified category for this server.\n"
                 "Use channel mention for text channels or channel name for voice channels.\n"
                 "Voice channel categories must be prefixed by \"voice\".",
             syntax="(category) (channel)",
             category="channel_management",
             perms={"manage_guild"})
    async def _add_to_category(self, msg):
        args = shlex.split(msg.content)
        if len(args) > 1:
            category = args[1].lower()
        else:
            raise CommandSyntaxError("No category provided.")

        if len(args) > 2:
            res = ""
            if category.startswith("voice"):
                for arg in args[2:]:
                    channel = arg.lower()
                    channel = utils.find(lambda x: x.name.lower() == channel, msg.guild.voice_channels)
                    if not channel:
                        raise CommandSyntaxError(f"Voice channel {args[2].lower()} not found.")
                    if self.channel_manager.add_channel_to_category(msg.guild, category, channel):
                        res = f"{res}{str(channel)}\n"
            else:
                if msg.channel_mentions:
                    for channel in msg.channel_mentions:
                        if self.channel_manager.add_channel_to_category(msg.guild, category, channel):
                            res = f"{res}{str(channel)}\n"
                else:
                    raise CommandSyntaxError("No channel provided.")

            await respond(msg, f"**ANALYSIS: Following channels were added to category {category}:**```\n{res}```")
        else:
            raise CommandSyntaxError("No channel provided.")

    @Command("RMFromCategory",
             doc="Removes the given channel from the specified category from the server.\n"
                 "Use channel mention for text channels or channel name for voice channels.\n"
                 "Voice channel categories must be prefixed by \"voice\".",
             syntax="(category) (channel)",
             category="channel_management",
             perms={"manage_guild"})
    async def _rm_from_category(self, msg):
        args = shlex.split(msg.content)
        if len(args) > 1:
            category = args[1].lower()
        else:
            raise CommandSyntaxError("No category provided.")

        if len(args) > 2:
            res = ""
            if category.startswith("voice"):
                for arg in args[2:]:
                    channel = arg.lower()
                    channel = utils.find(lambda x: x.name.lower() == channel, msg.guild.voice_channels)
                    if not channel:
                        raise CommandSyntaxError(f"Voice channel {args[2].lower()} not found.")
                    if self.channel_manager.remove_channel_from_category(msg.guild, category, channel):
                        res += f"✓ - {str(channel)}\n"
                    else:
                        res += f"✗ - {str(channel)}\n"
            else:
                if msg.channel_mentions:
                    for channel in msg.channel_mentions:
                        if self.channel_manager.remove_channel_from_category(msg.guild, category, channel):
                            res += f"✓ - {str(channel)}\n"
                        else:
                            res += f"✗ - {str(channel)}\n"
                else:
                    raise CommandSyntaxError("No channel provided.")

            await respond(msg, f"**ANALYSIS: Processed channel removals from category {category}:**\n```\n{res}```")
        else:
            raise CommandSyntaxError("No channel provided.")
