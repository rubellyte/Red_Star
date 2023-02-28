import discord
from asyncio import sleep
from string import capwords
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import UserPermissionError
from red_star.rs_utils import respond
from red_star.rs_version import version
from red_star.command_dispatcher import Command


class Info(BasePlugin):
    name = "info"
    version = "1.1"
    author = "medeor413"
    description = "A plugin that provides commands for fetching information about other commands, or the bot itself."

    async def activate(self):
        self.commands = {}
        self.categories = {}

    async def on_all_plugins_loaded(self):
        await sleep(1)
        await self.build_help()

    async def on_plugin_activated(self, _):
        await sleep(1)
        await self.build_help()

    async def on_plugin_deactivated(self, _):
        await sleep(1)
        await self.build_help()

    async def build_help(self):
        self.commands = self.command_dispatcher.commands
        self.categories = {}
        for command in self.commands.values():
            name = command.name
            cmd_category = command.category.lower()
            if cmd_category not in self.categories:
                self.categories[cmd_category] = {}
            self.categories[cmd_category][name] = command

    @Command("Help",
             doc="Displays information on commands.",
             syntax="[category/command]",
             category="info")
    async def _help(self, msg: discord.Message):
        if not self.categories:
            await self.build_help()
        try:
            search = msg.clean_content.split(None, 1)[1].lower()
        except IndexError:
            categories = "\n".join(sorted([capwords(x, "_") for x in self.categories.keys()]))
            await respond(msg, f"**ANALYSIS: Command categories:**```\n{categories}\n```")
            return
        if search in [x.lower() for x in self.commands.keys()]:
            cmd = self.commands[search]
            name = cmd.name
            syntax = cmd.syntax
            if not syntax:
                syntax = "N/A"
            doc = cmd.__doc__
            perms = cmd.perms
            category = capwords(cmd.category, "_")
            aliases = f"(Aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
            if not perms.check_permissions(msg.author, msg.channel):
                raise UserPermissionError
            text = f"**ANALYSIS: Command {name}:**```\n{name} (Category {category}) {aliases}\n\n{doc}\n\n" \
                   f"Syntax: {syntax}\n```"
            await respond(msg, text)
        elif search in self.categories.keys():
            name = capwords(search, "_")
            cmds = {x.name for x in self.categories[search].values()
                    if x.perms.check_permissions(msg.author, msg.channel)}
            cmds = sorted(list(cmds))
            if cmds:
                text = "\n".join(cmds)
                await respond(msg, f"**ANALYSIS: Category {name}:**```\n{text}\n```")
            else:
                await respond(msg, "**WARNING: You do not have permission for any command in this category.**")
        else:
            await respond(msg, f"**WARNING: No such category or command {search}**")

    @Command("About",
             doc="Displays information about the bot.",
             category="info")
    async def _about(self, msg: discord.Message):
        deco = self.command_dispatcher.config["command_prefix"]
        desc = f"Red Star: General purpose command AI for Discord.\n" \
               f"Use {deco}help for command information."
        em = discord.Embed(title="About Red Star", color=0xFF0000, description=desc)
        em.set_thumbnail(url="https://raw.githubusercontent.com/medeor413/Red_Star/master/default_avatar.png")
        em.add_field(name="GitHub", value="https://github.com/medeor413/Red_Star")
        em.add_field(name="Version", value=version)
        await respond(msg, embed=em)
