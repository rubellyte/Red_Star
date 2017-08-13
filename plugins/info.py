import asyncio
from string import capwords
from plugin_manager import BasePlugin
from utils import respond, Command
from discord import Embed


class Info(BasePlugin):
    name = "info"

    async def activate(self):
        self.commands = {}
        self.categories = {}

    async def on_all_plugins_loaded(self):
        await asyncio.sleep(1)
        await self.build_help()

    async def on_plugin_activated(self, plgname):
        await asyncio.sleep(1)
        await self.build_help()

    async def on_plugin_deactivated(self, plgname):
        await asyncio.sleep(1)
        await self.build_help()

    async def build_help(self):
        self.commands = self.plugins.command_dispatcher.commands
        self.categories = {}
        for name, command in self.commands.items():
            cate = command.category.lower()
            if cate not in self.categories:
                self.categories[cate] = {}
            self.categories[cate][name] = command

    @Command("help",
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
            name = capwords(search, "_")
            syn = cmd.syntax
            if not syn:
                syn = "N/A"
            doc = cmd.__doc__
            perms = cmd.perms
            cate = capwords(cmd.category, "_")
            aliases = f"(Aliases: {', '.join([capwords(x, '_') for x in cmd._aliases])})" if cmd._aliases else ""
            if not {x for x, y in msg.author.guild_permissions if y} >= perms:
                raise PermissionError
            text = f"**ANALYSIS: Command {name}:**```\n{name} (Category {cate}) {aliases}\n\n{doc}\n\n" \
                   f"Syntax: {syn}\n```"
            await respond(msg, text)
        elif search in self.categories.keys():
            name = capwords(search, "_")
            userperms = {x for x, y in msg.author.guild_permissions if y}
            cmds = [capwords(x.name, "_") for x in self.categories[search].values() if userperms >= x.perms]
            cmds = sorted(list(set(cmds)))
            if cmds:
                text = "\n".join(cmds)
                await respond(msg, f"**ANALYSIS: Category {name}:**```\n{text}\n```")
            else:
                await respond(msg, "**WARNING: You do not have permission for any command in this category.**")
        else:
            await respond(msg, f"**WARNING: No such category or command {search}**")

    @Command("about",
             doc="Displays information about the bot.",
             category="info")
    async def _about(self, msg):
        deco = self.plugins.command_dispatcher.plugin_config[msg.guild.id].command_prefix
        desc = f"Red Star: General purpose command AI for Discord.\nUse {deco}help for command information."
        em = Embed(title="About Red Star", color=0xFF0000, description=desc)
        em.set_thumbnail(url="https://raw.githubusercontent.com/medeor413/Red_Star/master/default_avatar.png")
        em.add_field(name="GitHub", value="https://github.com/medeor413/Red_Star")
        await respond(msg, None, embed=em)