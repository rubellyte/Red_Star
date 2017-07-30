import asyncio
from plugin_manager import BasePlugin
from utils import respond, Command


class Help(BasePlugin):
    name = "help"

    def activate(self):
        asyncio.ensure_future(self.get_commands())

    async def get_commands(self):
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
            cates = "\n".join([x.capitalize() for x in self.categories.keys()])
            await respond(self.client, data, f"**ANALYSIS: Command categories:**```\n{cates}\n```")
            return
        if search in [x.lower() for x in self.commands.keys()]:
            cmd = self.commands[search]
            name = search.capitalize()
            syn = cmd.syntax
            if not syn:
                syn = "N/A"
            doc = cmd.__doc__
            perms = cmd.perms
            cate = cmd.category.capitalize()
            if not {x for x, y in data.author.server_permissions if y} >= perms:
                raise PermissionError
            text = f"**ANALYSIS: Command {name}:**```\n{name} (Category {cate})\n{doc}\nSyntax: {syn}\n```"
            await respond(self.client, data, text)
        elif search in self.categories.keys():
            name = search.capitalize()
            text = "\n".join([x["name"].capitalize() for x in self.categories[search].values()])
            await respond(self.client, data, f"**ANALYSIS: Category {name}:**```\n{text}\n```")
        else:
            await respond(self.client, data, f"**WARNING: No such category or command {search}**")
