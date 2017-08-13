import urllib
from plugin_manager import BasePlugin
from utils import Command, respond
from discord import InvalidArgument

class BotManagement(BasePlugin):
    name = "bot_management"

    @Command("shutdown",
             doc="Shuts down the bot.",
             syntax="N/A",
             category="bot_management",
             perms={"manage_guild"})
    async def _shutdown(self, msg):
        await respond(msg, "**AFFIRMATIVE. SHUTTING DOWN.**")
        await self.client.stop_bot()

    @Command("update_avatar",
             doc="Updates the bot's avatar.",
             syntax="(URL)",
             category="bot_management",
             perms={"manage_guild"})
    async def _update_avatar(self, msg):
        if "bot_maintainers" not in self.config_manager.config:
            raise PermissionError("No bot maintainers are set!")
        elif msg.author.id not in self.config_manager.config.bot_maintainers:
            raise PermissionError
        url = " ".join(msg.content.split()[1:])
        if url:
            try:
                img = urllib.request.urlopen(url).read()
                await self.client.user.edit(avatar=img)
                await respond(msg, "**AVATAR UPDATED.**")
            except (urllib.request.URLError, ValueError) as e:
                await respond(msg, "**WARNING: Invalid URL provided.**")
            except InvalidArgument:
                await respond(msg, "**NEGATIVE. Image must be a PNG or JPG.**")
        else:
            raise SyntaxError("No URL provided.")

    @Command("activate",
             doc="Activates an inactive plugin.",
             syntax="(plugin) [permanent]",
             category="bot_management",
             perms={"manage_guild"})
    async def _activate(self, msg):
        if "bot_maintainers" not in self.config_manager.config:
            raise PermissionError("No bot maintainers are set!")
        elif msg.author.id not in self.config_manager.config.bot_maintainers:
            raise PermissionError
        plgname = msg.content.split()[1]
        try:
            permanent = msg.content.split()[2].lower() == "true"
        except IndexError:
            permanent = False
        all_plugins = self.plugin_manager.plugins
        if plgname in all_plugins:
            if plgname not in self.plugins:
                if plgname in self.config_manager.config.disabled_plugins and permanent:
                    self.config_manager.config.disabled_plugins.remove(plgname)
                    self.config_manager.save_config()
                await self.plugin_manager.activate(plgname)
                await respond(msg, f"**ANALYSIS: Plugin {plgname} was activated successfully.**")
            else:
                await respond(msg, f"**ANALYSIS: Plugin {plgname} is already activated.**")
        else:
            await respond(msg, f"**WARNING: Could not find plugin {plgname}.**")

    @Command("deactivate",
             doc="Deactivates an active plugin.",
             syntax="(plugin) [permanent]",
             category="bot_management",
             perms={"manage_guild"})
    async def _deactivate(self, msg):
        if "bot_maintainers" not in self.config_manager.config:
            raise PermissionError("No bot maintainers are set!")
        elif msg.author.id not in self.config_manager.config.bot_maintainers:
            raise PermissionError
        plgname = msg.content.split()[1].lower()
        try:
            permanent = msg.content.split()[2].lower() == "true"
        except IndexError:
            permanent = False
        if plgname == self.name:
            await respond(msg, f"**WARNING: Cannot deactivate {self.name}.**")
        elif plgname in self.plugins:
            if plgname not in self.config_manager.config.disabled_plugins and permanent:
                self.config_manager.config.disabled_plugins.append(plgname)
                self.config_manager.save_config()
            await self.plugin_manager.deactivate(plgname)
            await respond(msg, f"**ANALYSIS: Plugin {plgname} was deactivated successfully.**")
        else:
            await respond(msg, f"**ANALYSIS: Plugin {plgname} is not active.**")

    @Command("list_plugins",
             doc="Lists all plugins and their activation status.",
             syntax="(plugin)",
             category="bot_management",
             perms={"manage_guild"})
    async def _list_plugins(self, msg):
        if "bot_maintainers" not in self.config_manager.config:
            raise PermissionError("No bot maintainers are set!")
        elif msg.author.id not in self.config_manager.config.bot_maintainers:
            raise PermissionError
        active_plgs = ", ".join(self.plugins.keys())
        if not active_plgs:
            active_plgs = "None."
        all_plgs = list(self.plugin_manager.plugins.keys())
        inactive_plgs = ", ".join([x for x in all_plgs if x not in self.plugins])
        if not inactive_plgs:
            inactive_plgs = "None."
        await respond(msg, f"**ANALYSIS: Plugins are as follows:**```\nActive: {active_plgs}\n"
                           f"Inactive: {inactive_plgs}\n```")

    @Command("get_config",
             doc="Gets the config value at the specified path. Use <server> to fill in the server ID.",
             syntax="(path/to/value)",
             category="bot_management",
             perms={"manage_guild"})
    async def _get_config(self, msg):
        if "bot_maintainers" not in self.config_manager.config:
            raise PermissionError("No bot maintainers are set!")
        elif msg.author.id not in self.config_manager.config.bot_maintainers:
            raise PermissionError
        conf = self.config_manager.config
        args = msg.clean_content.split()[1:]
        try:
            path = args[0]
        except IndexError:
            raise SyntaxError("Missing path to config value.")
        path = path.replace("<server>", str(msg.guild.id))
        if path.startswith("/"):
            path = path[1:]
        path = path.split("/")
        val = conf
        for k in path:
            try:
                val = val[k]
            except TypeError:
                try:
                    i = int(k)
                    val = val[i]
                except ValueError:
                    raise SyntaxError(f"{k} is not a valid integer.")
                except IndexError:
                    raise SyntaxError(f"Path {args[0]} is invalid.")
            except KeyError:
                raise SyntaxError(f"Path {args[0]} is invalid.")
        await respond(msg, f"**ANALYSIS: Value of {args[0]}:** `{val}`")

    @Command("set_config",
             doc="Edits the config key at the specified path. Use <server> to fill in the server ID.",
             syntax="(path/to/edit) (value)",
             category="bot_management",
             perms={"manage_guild"})
    async def _set_config(self, msg):
        if "bot_maintainers" not in self.config_manager.config:
            raise PermissionError("No bot maintainers are set!")
        elif msg.author.id not in self.config_manager.config.bot_maintainers:
            raise PermissionError
        conf = self.config_manager.config
        args = msg.clean_content.split()[1:]
        try:
            path = args[0]
            path = path.replace("<server>", str(msg.guild.id))
            if path.startswith("/"):
                path = path[1:]
            path = path.split("/")
            key = path.pop()
            value = " ".join(args[1:])
            if not value:
                raise SyntaxError("Missing new config value.")
        except IndexError:
            raise SyntaxError("Missing path to config value.")
        val = conf
        for k in path:
            try:
                val = val[k]
            except TypeError:
                try:
                    i = int(k)
                    val = val[i]
                except ValueError:
                    raise SyntaxError(f"{k} is not a valid integer.")
                except IndexError:
                    raise SyntaxError(f"Path {args[0]} is invalid.")
            except KeyError:
                raise SyntaxError(f"Path {args[0]} is invalid.")
        try:
            orig = val[key]
        except TypeError:
            try:
                key = int(key)
                orig = val[key]
            except ValueError:
                raise SyntaxError(f"{k} is not a valid integer.")
            except IndexError:
                raise SyntaxError(f"Path {args[0]} is invalid.")
        except KeyError:
            raise SyntaxError(f"Path {args[0]} is invalid.")
        if isinstance(orig, str):
            val[key] = value
        elif isinstance(orig, bool):
            if value.lower() == "true":
                val[key] = True
            elif value.lower() == "false":
                val[key] = False
            else:
                raise SyntaxError(f"{value} is not a valid boolean value (true/false).")
        elif isinstance(orig, int):
            try:
                value = int(value)
                val[key] = value
            except ValueError:
                raise SyntaxError(f"{value} is not a valid integer.")
        elif isinstance(orig, float):
            try:
                value = float(value)
                val[key] = value
            except ValueError:
                raise SyntaxError(f"{value} is not a valid floating-point number.")
        else:
            raise SyntaxError(f"{args[0]} is an object or array.")
        self.config_manager.save_config()
        await respond(msg, f"**ANALYSIS: Config value {args[0]} edited to** `{value}` **successfully.**")