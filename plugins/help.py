import asyncio
from string import capwords
from plugin_manager import BasePlugin
from utils import respond, Command


class Help(BasePlugin):
    name = "help"

    async def activate(self):
        self.commands = {}
        self.categories = {}

    async def on_all_plugins_loaded(self):
        await asyncio.sleep(1)
        self.commands = self.plugins.command_dispatcher.commands
        self.categories = {}
        for name, command in self.commands.items():
            cate = command.category.lower()
            doc = command.__doc__
            syn = command.syntax
            perms = command.perms
            if cate not in self.categories:
                self.categories[cate] = {}
            self.categories[cate][name] = {"name": name, "doc": doc, "syntax": syn, "perms": perms}

    @Command("help",
             doc="Displays information on commands.",
             syntax="[category/command]",
             category="info")
    async def _help(self, data):
        try:
            search = data.clean_content.split(" ")[1].lower()
        except IndexError:
            cates = "\n".join([capwords(x, "_") for x in self.categories.keys()])
            await respond(self.client, data, f"**ANALYSIS: Command categories:**```\n{cates}\n```")
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
            if not {x for x, y in data.author.server_permissions if y} >= perms:
                raise PermissionError
            text = f"**ANALYSIS: Command {name}:**```\n{name} (Category {cate})\n{doc}\nSyntax: {syn}\n```"
            await respond(self.client, data, text)
        elif search in self.categories.keys():
            name = capwords(search, "_")
            text = "\n".join([capwords(x["name"], "_") for x in self.categories[search].values()])
            await respond(self.client, data, f"**ANALYSIS: Category {name}:**```\n{text}\n```")
        else:
            await respond(self.client, data, f"**WARNING: No such category or command {search}**")
