from red_star.plugin_manager import BasePlugin
from red_star.rs_utils import respond
from red_star.command_dispatcher import Command
from red_star.rs_errors import ChannelNotFoundError, CommandSyntaxError
import discord
import shlex


class ChannelManagerCommands(BasePlugin):
    name = "channel_manager_commands"
    version = "1.0.3"
    author = "medeor413"
    description = "A plugin that provides commands for interfacing with Red Star's channel_manager."

    @Command("GetChannel",
             doc="Gets information on the specified channel type (or all channel types if none specified) in this "
                 "server.",
             syntax="[channel type]",
             category="channel_management",
             perms={"manage_guild"})
    async def _get_channel_cmd(self, msg: discord.Message):
        gid = str(msg.guild.id)
        try:
            chantype = msg.clean_content.split(None, 1)[1].lower()
            try:
                chan = self.channel_manager.get_channel(chantype)
                await respond(msg, f"**ANALYSIS: The {chantype} channel for this server is {chan.mention}.**")
            except ChannelNotFoundError:
                await respond(msg, f"**ANALYSIS: No channel of type {chantype} set for this server.**")
        except IndexError:
            chantypes = "\n".join([f"{x.capitalize()}: {self.client.get_channel(y).name if y else 'Unset'}"
                                   for x, y in self.channel_manager.conf[gid]['channels'].items()])
            await respond(msg, f"**ANALYSIS: Channel types for this server:**```\n{chantypes}```")

    @Command("SetChannel",
             doc="Sets the specified channel type to the specified channel for this server or disables it.\n"
                 "Use channel mention for text channels or channel name for voice channels.\n"
                 "Voice channel types must be prefixed by \"Voice\".",
             syntax="(chantype) [channel]",
             category="channel_management",
             perms={"manage_guild"},
             run_anywhere=True)
    async def _set_channel_cmd(self, msg: discord.Message):
        args = shlex.split(msg.content)

        if len(args) > 1:
            chantype = args[1].lower()
        else:
            raise CommandSyntaxError("No channel type provided.")

        if chantype not in self.channel_manager.channel_types:
            type_list = "\n".join(x.capitalize() for x in self.channel_manager.channel_types)
            await respond(msg, f"**WARNING: No such channel type {chantype}. Channel types:**\n"
                               f"```\n{type_list}\n```")
            return

        if len(args) > 2:
            if chantype.startswith("voice"):
                channel = args[2].lower()
                channel = discord.utils.find(
                        lambda x: isinstance(x, discord.VoiceChannel) and x.name.lower() == channel,
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

        self.channel_manager.set_channel(chantype, channel)

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
    async def _get_category(self, msg: discord.Message):
        gid = str(msg.guild.id)
        try:
            category = msg.clean_content.split(None, 1)[1].lower()
            if category in self.channel_manager.conf[gid]['categories']:
                catestr = ", ".join([msg.guild.get_channel(x).name for
                                     x in self.channel_manager.conf[gid]['categories'][category]])
                await respond(msg, f"**ANALYSIS: Category {category} contains the following channels:**\n"
                                   f"```\n{catestr}```")
            else:
                await respond(msg, f"**ANALYSIS: No such category {category}.**")
        except IndexError:
            catestr = "\n".join(self.channel_manager.conf[gid]['categories'].keys())
            await respond(msg, f"**ANALYSIS: Available categories:**\n```\n{catestr}```")

    @Command("AddToCategory",
             doc="Adds the given channel to the specified category for this server.\n"
                 "Use channel mention for text channels or channel name for voice channels.\n"
                 "Voice channel categories must be prefixed by \"voice\".\n"
                 "Use --create to force addition of a new category.",
             syntax="[-c/--create](category) (channel)",
             category="channel_management",
             perms={"manage_guild"})
    async def _add_to_category(self, msg: discord.Message):
        args = shlex.split(msg.content)
        ignore_missing = False
        try:
            category = args[1].lower()
            if category in ("-c", "--create"):
                ignore_missing = True
                category = args[2].lower()
        except IndexError:
            raise CommandSyntaxError("No category provided.")

        if category not in self.channel_manager.conf[str(msg.guild.id)]["categories"] and not ignore_missing:
            raise CommandSyntaxError(f"No such channel category {category}.")

        if len(args) > 2:
            res = ""
            if category.startswith("voice"):
                for arg in args[2:]:
                    channel = arg.lower()
                    channel = discord.utils.find(lambda x: x.name.lower() == channel, msg.guild.voice_channels)
                    if not channel:
                        raise CommandSyntaxError(f"Voice channel {args[2].lower()} not found.")
                    if self.channel_manager.add_channel_to_category(category, channel):
                        res = f"{res}{str(channel)}\n"
            else:
                if msg.channel_mentions:
                    for channel in msg.channel_mentions:
                        if self.channel_manager.add_channel_to_category(category, channel):
                            res = f"{res}{str(channel)}\n"
                else:
                    raise CommandSyntaxError("No channel provided")

            await respond(msg, f"**ANALYSIS: The following channels were added to category {category}:**```\n{res}```")
        else:
            raise CommandSyntaxError("No channel provided")

    @Command("RMFromCategory",
             doc="Removes the given channel from the specified category from the server.\n"
                 "Use channel mention for text channels or channel name for voice channels.\n"
                 "Voice channel categories must be prefixed by \"voice\".",
             syntax="(category) (channel)",
             category="channel_management",
             perms={"manage_guild"})
    async def _rm_from_category(self, msg: discord.Message):
        args = shlex.split(msg.content)
        if len(args) > 1:
            category = args[1].lower()
        else:
            raise CommandSyntaxError("No category provided.")

        if category not in self.channel_manager.conf[str(msg.guild.id)]["categories"]:
            raise CommandSyntaxError(f"No such channel category {category}.")

        if len(args) > 2:
            res = ""
            if category.startswith("voice"):
                for arg in args[2:]:
                    channel = arg.lower()
                    channel = discord.utils.find(lambda x: x.name.lower() == channel, msg.guild.voice_channels)
                    if not channel:
                        raise CommandSyntaxError(f"Voice channel {args[2].lower()} not found")
                    if self.channel_manager.remove_channel_from_category(category, channel):
                        res += f"✓ - {str(channel)}\n"
                    else:
                        res += f"✗ - {str(channel)}\n"
            else:
                if msg.channel_mentions:
                    for channel in msg.channel_mentions:
                        if self.channel_manager.remove_channel_from_category(category, channel):
                            res += f"✓ - {str(channel)}\n"
                        else:
                            res += f"✗ - {str(channel)}\n"
                else:
                    raise CommandSyntaxError("No channel provided")

            await respond(msg, f"**ANALYSIS: Processed channel removals from category {category}:**\n```\n{res}```")
        else:
            raise CommandSyntaxError("No channel provided")
