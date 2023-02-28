import discord
from asyncio import sleep
from string import capwords
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import UserPermissionError
from red_star.rs_utils import respond
from red_star.rs_version import version
from red_star.command_dispatcher import Command

# Yes, I know about multiline strings. That breaks the max line length rule.
BASIC_HELP_TEXT = (
    "```\n"
    "This command can be used to get more information on the various commands the bot has to offer. Type {deco}Help "
    "categories to get a list of command categories. Then, type {deco}Help followed by one of the category names "
    "listed to get a list of commands in that category, and type {deco}Help followed by a command name for detailed "
    "information on that command.\n\n"

    "Some basic usage information:\n"
    "- In command syntax, a parameter in (parentheses) is required, and a parameter in [brackets] is optional. "
    "Don't type the parentheses or brackets!\n"
    "- If you see a parameter written like [-o/--option], this is a flag. You can use either -o or --option to "
    "specify it. If you see this written [-o/--option something], then the flag needs a parameter as well: "
    "[-n/--name name] might be used by typing \"-n John\", for example.\n"
    "- If you need to write a parameter with spaces, say a user named \"Some Thing\", you should put quotes around "
    "it in the command. Single or double quotes will work. To type quotes inside a quoted name, type a \\ before the "
    "quote, ex. \"Some \\\"Thing\\\"\".\n"
    "- If a command asks for a user, you can specify the user by their username, server nickname, username with "
    "discriminator, user ID, or by mentioning them. Be specific - if two users have the same name, the bot will pick "
    "one of them, and it might not be the one you wanted!\n"
    "- If a command asks for a role, you can similarly specify it using the role's name or ID, or by mentioning it.\n"
    "- Several commands ask for a yes/no type input. Many words will work for these, including true, yes, on, "
    "and enable for yes, and false, no, off, and disable for no."
    "```"
)


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
        except IndexError:  # No category or command specified. Give some general help text.
            deco = self.command_dispatcher.config["command_prefix"]
            await respond(msg, BASIC_HELP_TEXT.format(deco=deco))
            return
        if search == "categories":
            categories = "\n".join(sorted([capwords(x, "_") for x in self.categories.keys()]))
            await respond(msg, f"**ANALYSIS: Command categories:**```\n{categories}\n```")
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
        elif search in [x.lower() for x in self.commands.keys()]:
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
