import asyncio
from string import capwords
from plugin_manager import BasePlugin
from rs_errors import UserPermissionError
from rs_utils import respond
from command_dispatcher import Command
from discord import Embed


class Info(BasePlugin):
    name = "info"

    async def activate(self):
        self.commands = {}
        self.categories = {}

    async def on_all_plugins_loaded(self):
        await asyncio.sleep(1)
        await self.build_help()

    async def on_plugin_activated(self, _):
        await asyncio.sleep(1)
        await self.build_help()

    async def on_plugin_deactivated(self, _):
        await asyncio.sleep(1)
        await self.build_help()

    async def build_help(self):
        self.commands = self.client.command_dispatcher.commands
        self.categories = {}
        for command in self.commands.values():
            name = command.name
            cate = command.category.lower()
            if cate not in self.categories:
                self.categories[cate] = {}
            self.categories[cate][name] = command

    @Command("Help",
             doc="Displays information on commands.",
             syntax="[category/command]",
             category="info")
    async def _help(self, msg):
        if not self.categories:
            await self.build_help()
        try:
            search = msg.clean_content.split(" ")[1].lower()
        except IndexError:
            cates = "\n".join(sorted([capwords(x, "_") for x in self.categories.keys()]))
            await respond(msg, f"**ANALYSIS: Command categories:**```\n{cates}\n```")
            return
        if search in [x.lower() for x in self.commands.keys()]:
            cmd = self.commands[search]
            name = cmd.name
            syn = cmd.syntax
            if not syn:
                syn = "N/A"
            doc = cmd.__doc__
            perms = cmd.perms
            cate = capwords(cmd.category, "_")
            aliases = f"(Aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
            if not {x for x, y in msg.author.guild_permissions if y} >= perms:
                raise UserPermissionError
            text = f"**ANALYSIS: Command {name}:**```\n{name} (Category {cate}) {aliases}\n\n{doc}\n\n" \
                   f"Syntax: {syn}\n```"
            await respond(msg, text)
        elif search in self.categories.keys():
            name = capwords(search, "_")
            userperms = {x for x, y in msg.author.guild_permissions if y}
            cmds = {x.name for x in self.categories[search].values() if userperms >= x.perms}
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
    async def _about(self, msg):
        deco = self.client.command_dispatcher.conf[str(msg.guild.id)].command_prefix
        desc = f"Red Star: General purpose command AI for Discord.\nUse {deco}help for command information."
        em = Embed(title="About Red Star", color=0xFF0000, description=desc)
        em.set_thumbnail(url="https://raw.githubusercontent.com/medeor413/Red_Star/master/default_avatar.png")
        em.add_field(name="GitHub", value="https://github.com/medeor413/Red_Star")
        await respond(msg, None, embed=em)
