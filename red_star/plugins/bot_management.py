import asyncio
import json
import re
import shlex
import urllib.request
import urllib.error
from io import BytesIO
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import CommandSyntaxError, UserPermissionError
from red_star.rs_utils import respond, is_positive, RSArgumentParser, split_message
from red_star.command_dispatcher import Command
from discord import InvalidArgument, HTTPException
from traceback import format_exception, format_exc


class BotManagement(BasePlugin):
    name = "bot_management"
    version = "1.3"
    author = "medeor413"
    description = "A plugin that allows bot maintainers to interface with core bot options through Discord."

    async def on_dm_message(self, msg):
        if msg.author == self.client.user:
            return
        maintainers = [self.client.get_user(x) for x in self.config_manager.config.get("bot_maintainers", [])]
        maintainers = filter(None, maintainers)
        if msg.content.startswith("!") and msg.author in maintainers:
            return
        for user in maintainers:
            await user.send(f"`{msg.author}:` {msg.system_content}\n"
                            f"`Attachments: {', '.join(a.url for a in msg.attachments)}`")

    @Command("Ping",
             doc="Returns the current message latency of the bot.",
             syntax="N/A",
             dm_command=True)
    async def _ping(self, msg):
        await respond(msg, f"**ANALYSIS: Current latency is {round(self.client.latency * 1000)} ms.**")

    @Command("Shutdown",
             doc="Shuts down the bot.",
             category="bot_management",
             dm_command=True,
             bot_maintainers_only=True)
    async def _shutdown(self, msg):
        await respond(msg, "**AFFIRMATIVE. SHUTTING DOWN.**")
        raise SystemExit

    @Command("UpdateAvatar",
             doc="Updates the bot's avatar.",
             syntax="(URL or file)",
             category="bot_management",
             bot_maintainers_only=True,
             dm_command=True)
    async def _update_avatar(self, msg):
        try:
            url = msg.content.split(None, 1)[1]
            img = urllib.request.urlopen(url).read()
        except IndexError:
            if msg.attachments:
                fp = BytesIO()
                await msg.attachments[0].save(fp)
                img = fp.getvalue()
            else:
                raise CommandSyntaxError("No URL or file provided.")
        except (urllib.error.URLError, ValueError):
            raise CommandSyntaxError("Invalid URL provided.")
        try:
            await self.client.user.edit(avatar=img)
            await respond(msg, "**AVATAR UPDATED.**")
        except InvalidArgument:
            raise CommandSyntaxError("Image must be a PNG or JPG")
        except HTTPException:
            raise UserPermissionError("Cannot change avatar at this time.")

    @Command("UpdateName",
             doc="Updates the bot's (nick)name.",
             syntax="[-p/--permanent] (name)",
             category="bot_management",
             bot_maintainers_only=True,
             dm_command=True)
    async def _update_name(self, msg):
        args = msg.clean_content.split()[1:]
        edit_username = False
        if args[0].lower() in ("-p", "--permanent"):
            args.pop(0)
            edit_username = True
        elif args[0].lower() == "reset":
            await msg.guild.me.edit(nick=None)
            await respond(msg, "**ANALYSIS: Nickname reset.**")
            return
        newname = " ".join(args)
        if edit_username:
            if "bot_maintainers" not in self.config_manager.config:
                raise UserPermissionError("No bot maintainers are set!")
            if msg.author.id not in self.config_manager.config["bot_maintainers"]:
                raise UserPermissionError
            await self.client.user.edit(username=newname)
            await respond(msg, f"**ANALYSIS: Username changed to {newname} successfully.**")
        else:
            await msg.guild.me.edit(nick=newname)
            await respond(msg, f"**ANALYSIS: Nickname changed to {newname} successfully.**")

    @Command("Activate",
             doc="Activates an inactive plugin.",
             syntax="(plugin) [permanent]",
             category="bot_management",
             bot_maintainers_only=True,
             dm_command=True)
    async def _activate(self, msg):
        plgname = msg.content.split()[1]
        try:
            permanent = is_positive(msg.content.split()[2])
        except IndexError:
            permanent = False
        all_plugins = self.plugin_manager.plugins
        if plgname in all_plugins:
            if plgname not in self.plugins:
                if plgname in self.config_manager.config["disabled_plugins"] and permanent:
                    self.config_manager.config["disabled_plugins"].remove(plgname)
                    self.config_manager.save_config()
                await self.plugin_manager.activate(plgname)
                await respond(msg, f"**ANALYSIS: Plugin {plgname} was activated successfully.**")
            else:
                await respond(msg, f"**ANALYSIS: Plugin {plgname} is already activated.**")
        else:
            await respond(msg, f"**WARNING: Could not find plugin {plgname}.**")

    @Command("Deactivate",
             doc="Deactivates an active plugin.",
             syntax="(plugin) [permanent]",
             category="bot_management",
             bot_maintainers_only=True,
             dm_command=True)
    async def _deactivate(self, msg):
        plgname = msg.content.split()[1].lower()
        try:
            permanent = is_positive(msg.content.split()[2])
        except IndexError:
            permanent = False
        if plgname == self.name:
            await respond(msg, f"**WARNING: Cannot deactivate {self.name}.**")
        elif plgname in self.plugins:
            if plgname not in self.config_manager.config["disabled_plugins"] and permanent:
                self.config_manager.config["disabled_plugins"].append(plgname)
                self.config_manager.save_config()
            await self.plugin_manager.deactivate(plgname)
            await respond(msg, f"**ANALYSIS: Plugin {plgname} was deactivated successfully.**")
        else:
            await respond(msg, f"**ANALYSIS: Plugin {plgname} is not active.**")

    @Command("ReloadPlugin",
             doc="Reloads a plugin module, refreshing code changes.",
             syntax="(plugin)",
             category="bot_management",
             bot_maintainers_only=True,
             dm_command=True)
    async def _reload_plugin(self, msg):
        plgname = msg.content.split()[1].lower()
        if plgname == self.name:
            await respond(msg, f"**WARNING: Cannot deactivate {self.name}.**")
        elif plgname in self.plugins:
            await self.plugin_manager.reload_plugin(plgname)
            await respond(msg, f"**ANALYSIS: Plugin {plgname} was reloaded successfully.**")

    @Command("ListPlugins",
             doc="Lists all plugins and their activation status.",
             syntax="(plugin)",
             category="bot_management",
             bot_maintainers_only=True,
             dm_command=True)
    async def _list_plugins(self, msg):
        active_plgs = ", ".join(self.plugins.keys())
        if not active_plgs:
            active_plgs = "None."
        all_plgs = list(self.plugin_manager.plugins)
        inactive_plgs = ", ".join([x for x in all_plgs if x not in self.plugins])
        if not inactive_plgs:
            inactive_plgs = "None."
        await respond(msg, f"**ANALYSIS: Plugins are as follows:**```\nActive: {active_plgs}\n"
                           f"Inactive: {inactive_plgs}\n```")

    @Command("GetConfig",
             doc="Gets the config value at the specified path. Use <server> to fill in the server ID.\n"
                 "Use --file to view a different configuration file, such as music_player.json.",
             syntax="(path/to/value) [-f/--file file]",
             category="bot_management",
             bot_maintainers_only=True,
             dm_command=True)
    async def _get_config(self, msg):
        args = msg.clean_content.split()[1:]
        if args[0] in ("-f", "--file"):
            args.pop(0)
            filename = args.pop(0)
            try:
                conf_dict = self.config_manager.plugin_config_files[filename]
            except KeyError:
                raise CommandSyntaxError(f"Config file {filename} does not exist.")
        else:
            conf_dict = self.config_manager.config.copy()

        try:
            path = args[0]
        except IndexError:
            path = ""
        try:
            path = path.replace("<server>", str(msg.guild.id))
        except AttributeError:
            path = path.replace("<server>", "default")
        if path.startswith("/"):
            path = path[1:]
        path_list = path.split("/")
        conf_dict.pop("token", None)  # Don't want to leak that by accident!

        for k in path_list:
            if not k:
                break
            try:
                conf_dict = self._list_or_dict_subscript(conf_dict, k)
            except KeyError:
                raise CommandSyntaxError(f"Key {k} does not exist.")
            except IndexError:
                raise CommandSyntaxError(f"Index {k} does not exist.")
            except ValueError:
                raise CommandSyntaxError(f"{k} is not a valid integer index.")
            except TypeError:
                raise CommandSyntaxError(f"{args.path} is not a valid path!")

        res = json.dumps(conf_dict, indent=2, sort_keys=True)
        for split_msg in split_message(f"**ANALYSIS: Contents of {path}:**```JSON{res}```"):
            await respond(msg, split_msg)

    @Command("SetConfig",
             doc="Edits the config value at the specified path. Use <server> to fill in the server ID. Doesn't allow "
                 "types to be changed unless forced.\n"
                 "Use --file to edit a different configuration file, such as music_player.json.\n"
                 "Use --remove to delete a value, --append to add a value to a list, --addkey to add a new key/value"
                 "pair to a dict, and --type with a type name to force type conversion.\n"
                 "Valid --types: bool, int, float, str, list, dict, json",
             syntax="(path/to/edit) (value or -r/--remove) [-a/--append] [-k/--addkey key_name] [-t/--type type]"
                    "[-f/--file file]",
             category="bot_management",
             bot_maintainers_only=True,
             dm_command=True)
    async def _set_config(self, msg):
        parser = RSArgumentParser()
        parser.add_argument("path")
        parser.add_argument("value", nargs="*")
        parser.add_argument("-f", "--file", type=str)
        parser.add_argument("-t", "--type", choices=("null", "bool", "int", "float", "str", "list", "dict", "json"),
                            type=str.lower)
        group = parser.add_mutually_exclusive_group()
        group.add_argument("-r", "--remove", action="store_true")
        group.add_argument("-a", "--append", action="store_true")
        group.add_argument("-k", "--addkey")

        args = parser.parse_args(shlex.split(msg.clean_content)[1:])

        type_converters = {
            "null": lambda x: None,
            "bool": is_positive,
            "int": int,
            "float": float,
            "str": str,
            "list": json.loads,
            "dict": json.loads,
            "DotDict": json.loads,
            "json": json.loads
        }

        if args.file:
            try:
                conf_dict = self.config_manager.plugin_config_files[args.file]
            except KeyError:
                raise CommandSyntaxError(f"Config file {args.file} does not exist.")
        else:
            conf_dict = self.config_manager.config.copy()

        try:
            path = args.path
            try:
                path = path.replace("<server>", str(msg.guild.id))
            except AttributeError:
                path = path.replace("<server>", "default")
            if path.startswith("/"):
                path = path[1:]
            path_list = path.split("/")
            final_key = path_list.pop()
            value = " ".join(args.value)
            if args.type:
                try:
                    value = type_converters[args.type](value)
                except ValueError:
                    raise CommandSyntaxError(f"{value} cannot be converted to {args.type}!")
            if value is None and not args.remove and args.type != "null":
                raise CommandSyntaxError("Missing new config value.")
        except IndexError:
            raise CommandSyntaxError("Missing path to config value.")
        for k in path_list:
            try:
                conf_dict = self._list_or_dict_subscript(conf_dict, k)
            except KeyError:
                raise CommandSyntaxError(f"Key {k} does not exist.")
            except IndexError:
                raise CommandSyntaxError(f"Index {k} does not exist.")
            except TypeError:
                raise CommandSyntaxError(f"{args.path} is not a valid path!")

        try:
            orig = self._list_or_dict_subscript(conf_dict, final_key)
        except KeyError:
            raise CommandSyntaxError(f"Key {final_key} does not exist.")
        except IndexError:
            raise CommandSyntaxError(f"Index {final_key} does not exist.")
        except ValueError:
            raise CommandSyntaxError(f"{final_key} is not a valid integer index.")
        except TypeError:
            raise CommandSyntaxError(f"{args.path} is not a valid path!")

        if args.remove:
            if isinstance(conf_dict, dict):
                del conf_dict[final_key]
            elif isinstance(conf_dict, list):
                conf_dict.pop(int(final_key))
            else:
                raise CommandSyntaxError("Path does not lead to a collection!")
            await respond(msg, f"**ANALYSIS: Config value {args.path} deleted successfully.**")

        elif args.append:
            if isinstance(conf_dict[final_key], list):
                conf_dict[final_key].append(value)
                await respond(msg, f"**ANALYSIS: {value} appended to {path} successfully.**")
            else:
                raise CommandSyntaxError("Path does not lead to a list!")

        elif args.addkey:
            if isinstance(conf_dict[final_key], dict):
                conf_dict[final_key][args.addkey] = value
                await respond(msg, f"**ANALYSIS: Key {args.addkey} with value {value} added to {path} "
                                   f"successfully.**")
            else:
                raise CommandSyntaxError("Path does not lead to a dict!")

        elif not args.type and type(value) is not type(orig) and orig is not None:
            orig_type = type(orig).__name__
            try:
                conf_dict[final_key] = type_converters[orig_type](value)
                await respond(msg, f"**ANALYSIS: Config value {path} edited to** `{value}` **successfully.**")
            except (KeyError, ValueError):
                raise CommandSyntaxError(f"Couldn't coerce {value} into type {orig_type}!")
        else:
            conf_dict[final_key] = value
            await respond(msg, f"**ANALYSIS: Config value {path} edited to** `{value}` **successfully.**")

        self.config_manager.save_config()

    @Command("LastError",
             doc="Gets the last error to occur in the specified context.",
             syntax="(command/event/unhandled)",
             category="debug",
             perms={"manage_guild"},
             dm_command=True)
    async def _last_error(self, msg):
        try:
            args = msg.clean_content.split(None, 1)[1].lower()
        except IndexError:
            raise CommandSyntaxError("No error context specified.")
        if args == "command":
            e = self.client.command_dispatcher.last_error
        elif args == "event":
            e = self.plugin_manager.last_error
        elif args == "unhandled":
            e = self.client.last_error
        else:
            raise CommandSyntaxError("Invalid error context.")
        if e:
            excstr = "\n".join(format_exception(*e))
            await respond(msg, f"**ANALYSIS: Last error in context {args}:** ```Python\n{excstr}\n```")
        else:
            await respond(msg, f"**ANALYSIS: No error in context {args}.**")

    @Command("Execute", "Exec", "Eval",
             doc="Executes the given Python code. Be careful, you can really break things with this!\n"
                 "Provided variables are `ct` (shorthand for asyncio.create_task) and `self.res` "
                 "(printed by the bot after execution).",
             syntax="(code in code block)",
             category="debug",
             bot_maintainers_only=True,
             run_anywhere=True,
             dm_command=True)
    async def _execute(self, msg):
        try:
            arg = re.split(r"\s+", msg.content, 1)[1]
            t_match = re.match(r"`([^\n\r`]+)`|```.*?\s+(.*)```", arg, re.DOTALL)
            code = t_match.group(1) or t_match.group(2)
        except IndexError:
            raise CommandSyntaxError("No code provided.")
        except AttributeError:
            raise CommandSyntaxError("Code is not in valid code block.")
        # Convenience variables for printing results and create_task
        ct = asyncio.create_task
        self.res = self.EmptySentinel()
        # noinspection PyBroadException
        try:
            exec(code, globals(), locals())
        except Exception:
            await respond(msg, f"**WARNING: Error occurred while executing code. Traceback:**\n"
                               f"```Py\n{format_exc()}\n```")
        if not isinstance(self.res, self.EmptySentinel):
            await respond(msg, f"**ANALYSIS: Result: {self.res}**")
            self.res = self.EmptySentinel()

    @staticmethod
    def _list_or_dict_subscript(obj, key):
        """
        Helper function to use key as a key if obj is a dict, or as an int index if a list.

        :param obj: The object to subscript.
        :param key: The key to subscript with.
        :return: The subscripted object.
        """
        if isinstance(obj, dict):
            return obj[key]
        elif isinstance(obj, list):
            return obj[int(key)]
        else:
            raise TypeError

    class EmptySentinel:
        """
        Just a simple class to function as a sentinel value for Execute's result variable.
        """
