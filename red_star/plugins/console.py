import asyncio
import shlex
import re
import json
import logging
from red_star.plugin_manager import BasePlugin
from concurrent.futures import CancelledError
from red_star.rs_errors import ConsoleCommandSyntaxError
from red_star.rs_utils import RSArgumentParser, is_positive
from discord import NotFound, Forbidden
from traceback import format_exception


class ConsoleListener(BasePlugin):
    name = "console"
    default_config = {
        "allow_stdout_logging": False,
        "allow_stdout_errors": True
    }

    async def activate(self):
        self.run_loop = True
        self.con_commands = {
            "set_config": self._set_config,
            "get_config": self._get_config_cmd,
            "shutdown": self._shutdown,
            "guilds": self._guilds,
            "channels": self._channels,
            "read": self._read,
            "say": self._say,
            "delete_msg": self._delete_msg,
            "help": self._help,
            "exec": self._exec,
            "last_error": self._last_error
        }
        if not self.plugin_config.allow_stdout_logging:
            base_logger = logging.getLogger()
            for h in base_logger.handlers:
                if type(h) == logging.StreamHandler:
                    if self.plugin_config.allow_stdout_errors:
                        self.logger.info("Quieting STDOUT logger (errors-only) and starting console...")
                        h.setLevel(logging.ERROR)
                    else:
                        self.logger.info("Disabling STDOUT logger and starting console...")
                        base_logger.removeHandler(h)
        else:
            self.logger.info("Starting console...")
        self.task = asyncio.ensure_future(self._listen())
        self.read_task = None

    async def deactivate(self):
        print("Please press enter to kill the readline loop.")
        self.run_loop = False
        try:
            self.task.cancel()
            if self.read_task:
                # noinspection PyUnresolvedReferences
                self.read_task.cancel()
        except CancelledError:
            pass

    async def _readline(self):
        loop = asyncio.get_event_loop()
        self.read_task = loop.run_in_executor(None, input, ">> ")
        data = await self.read_task
        if not isinstance(data, str):
            data = data.decode(encoding="utf-8")
        self.eof = not data
        return data

    # noinspection PyBroadException
    async def _listen(self):
        while self.run_loop:
            try:
                t_input = await self._readline()
            except CancelledError:
                raise
            except Exception:
                self.logger.exception("Exception waiting for input: ", exc_info=True)
                continue
            args = shlex.split(t_input)
            if not args:
                continue
            elif args[0].lower() in self.con_commands:
                try:
                    await self.con_commands[args[0].lower()](args[1:])
                except ConsoleCommandSyntaxError as e:
                    err = str(e) if str(e) else "No additional information."
                    print("Syntax error: " + err)
                except CancelledError:
                    raise
                except Exception:
                    self.logger.exception("Exception while running console command: ", exc_info=True)
            else:
                print("Invalid command.")

    # Console command functions

    async def _shutdown(self, _):
        """
        Shuts down the bot.
        Syntax: shutdown
        """
        self.logger.info("Shutdown called from console.")
        self.run_loop = False
        asyncio.ensure_future(self.client.stop_bot())

    async def _get_config_cmd(self, args):
        """
        Retrieves the specified config key, or all of the config if none specified.
        Use <guildX>, where X is the index of a guild as shown in 'guilds', to substitute in a guild's ID.
        Syntax: get_config [path]
        """
        if args:
            path = " ".join(args)
        else:
            path = ""
        print(json.dumps(self._get_config(path), sort_keys=True, indent=2))

    def _get_config(self, path=""):
        conf_dict = self.config_manager.config
        pattern = re.compile("<guild(\d+)>")

        t_s = pattern.search(path)
        if t_s:
            t_i = min(max(0, int(t_s.group(1))), len(self.client.guilds)-1)
            path = pattern.sub(str(self.client.guilds[t_i].id), path)

        if path.startswith("/"):
            path = path[1:]
        if path.endswith("/"):
            path = path[:-1]
        path_list = path.split("/")

        for k in path_list:
            if not k:
                break
            try:
                conf_dict = self._list_or_dict_subscript(conf_dict, k)
            except KeyError:
                raise ConsoleCommandSyntaxError(f"Key {k} does not exist.")
            except IndexError:
                raise ConsoleCommandSyntaxError(f"Index {k} does not exist.")
            except ValueError:
                raise ConsoleCommandSyntaxError(f"{k} is not a valid integer index.")
            except TypeError:
                raise ConsoleCommandSyntaxError(f"{path} is not a valid path!")

        return conf_dict

    async def _set_config(self, args):
        """
        Sets the specified config key to the specified value. Doesn't allow types to be changed unless forced.
        Use <guildX>, where X is the index of a guild as shown in 'guilds', to substitute in a guild's ID.
        Use --remove to delete a value, --append to add a value to a list, --addkey to add a new key/value pair
        to a dict, and --type with a type name to force type conversion.
        Valid --types: bool, int, float, str, list, dict, json
        Syntax: (path/to/edit) (value or -r/--remove) [-a/--append] [-k/--addkey key_name] [-t/--type type]
        """
        parser = RSArgumentParser()
        parser.add_argument("path")
        parser.add_argument("value", nargs="*")
        parser.add_argument("-r", "--remove", action="store_true")
        parser.add_argument("-a", "--append", action="store_true")
        parser.add_argument("-k", "--addkey")
        parser.add_argument("-t", "--type", choices=("null", "bool", "int", "float", "str", "list", "dict", "json"),
                            type=str.lower)

        args = parser.parse_args(args)

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

        if sum((args.remove, args.append, bool(args.addkey))) > 1:
            raise ConsoleCommandSyntaxError("--remove, --append, and --addkey arguments are mutually exclusive.")

        try:
            path = args.path
            if path.startswith("/"):
                path = path[1:]
            path_list = path.split("/")
            final_key = path_list.pop()
            value = " ".join(args.value)
            if args.type:
                try:
                    value = type_converters[args.type](value)
                except ValueError:
                    raise ConsoleCommandSyntaxError(f"{value} cannot be converted to {args.type}!")
            if value is None and not args.remove and args.type != "null":
                raise ConsoleCommandSyntaxError("Missing new config value.")
        except IndexError:
            raise ConsoleCommandSyntaxError("Missing path to config value.")

        conf_dict = self._get_config(path="/".join(path_list))

        try:
            orig = self._list_or_dict_subscript(conf_dict, final_key)
        except KeyError:
            raise ConsoleCommandSyntaxError(f"Key {final_key} does not exist.")
        except IndexError:
            raise ConsoleCommandSyntaxError(f"Index {final_key} does not exist.")
        except ValueError:
            raise ConsoleCommandSyntaxError(f"{final_key} is not a valid integer index.")
        except TypeError:
            raise ConsoleCommandSyntaxError(f"{args.path} is not a valid path!")

        if args.remove:
            if isinstance(conf_dict, dict):
                del conf_dict[final_key]
            elif isinstance(conf_dict, list):
                conf_dict.pop(int(final_key))
            else:
                raise ConsoleCommandSyntaxError("Path does not lead to a collection!")
            print(f"Config value {args.path} deleted successfully.")

        elif args.append:
            if isinstance(conf_dict[final_key], list):
                conf_dict[final_key].append(value)
                print(f"{value} appended to {path} successfully.")
            else:
                raise ConsoleCommandSyntaxError("Path does not lead to a list!")

        elif args.addkey:
            if isinstance(conf_dict[final_key], dict):
                conf_dict[final_key][args.addkey] = value
                print(f"Key {args.addkey} with value {value} added to {path} successfully.")
            else:
                raise ConsoleCommandSyntaxError("Path does not lead to a dict!")

        elif not args.type and type(value) is not type(orig) and orig is not None:
            orig_type = type(orig).__name__
            try:
                conf_dict[final_key] = type_converters[orig_type](value)
                print(f"Config value {path} edited to `{value}` successfully.")
            except (KeyError, ValueError):
                raise ConsoleCommandSyntaxError(f"Couldn't coerce {value} into type {orig_type}!")
        else:
            conf_dict[final_key] = value
            print(f"Config value {path} edited to `{value}` successfully.")

        self.config_manager.save_config()

    async def _guilds(self, _):
        """
        Prints the list of guilds the bot is in, with numbers usable for addressing them in other commands.
        Syntax: guilds
        """
        for i, guild in enumerate(self.client.guilds):
            print(f"{i:02d} : {guild.name[:40].ljust(40)} : {guild.id}")

    async def _channels(self, args):
        """
        Prints the list of channels in the specified guild, with numbers usable for addressing them in other commands.
        Syntax: channels (guild)
        """
        try:
            server_index = int(args[0])
            if server_index < 0:
                raise ValueError
        except IndexError:
            raise ConsoleCommandSyntaxError("Missing argument.")
        except ValueError:
            raise ConsoleCommandSyntaxError("Argument is not a valid integer.")
        try:
            srv = self.client.guilds[server_index]
        except IndexError:
            raise ConsoleCommandSyntaxError("Invalid server index.")
        for i, chan in enumerate(srv.text_channels):
            print(f"{i:02d} : {chan.name[:40].ljust(40)} : {chan.id}")

    async def _read(self, args):
        """
        Reads the last x messages from the specified guild and channel and prints them.
        Syntax: read (guild.channel) (amount)
        """
        try:
            chanstr = args[0]
        except IndexError:
            raise ConsoleCommandSyntaxError("No arguments provided.")
        try:
            count = int(args[1])
            if count < 1:
                raise ValueError
        except ValueError:
            raise ConsoleCommandSyntaxError("Invalid amount.")
        except IndexError:
            raise ConsoleCommandSyntaxError("Missing amount argument.")
        try:
            guild, chan = re.match(r"(\d+).(\d+)", chanstr).group(1, 2)
        except AttributeError:
            raise ConsoleCommandSyntaxError("Invalid indices string.")
        try:
            guild = self.client.guilds[int(guild)]
        except IndexError:
            raise ConsoleCommandSyntaxError("Invalid guild index.")
        try:
            chan = guild.text_channels[int(chan)]
        except IndexError:
            raise ConsoleCommandSyntaxError("Invalid channel index.")
        print(f"Last {count} messages in channel {chan.name}:")
        async for msg in chan.history(limit=count, reverse=True):
            print(f"{msg.author} @ {msg.created_at.strftime('%H:%M:%S')}: {msg.clean_content} [{msg.id}]")

    async def _say(self, args):
        """
        Sends the given text to the specified guild and channel.
        Syntax: say (guild.channel) (text)
        """
        try:
            chanstr = args.pop(0)
        except IndexError:
            raise ConsoleCommandSyntaxError("No arguments provided.")
        res = " ".join(args)
        if not res:
            raise ConsoleCommandSyntaxError("Must provide text to say.")
        try:
            guild, chan = re.match(r"(\d+).(\d+)", chanstr).group(1, 2)
        except AttributeError:
            raise ConsoleCommandSyntaxError("Invalid indices string.")
        try:
            guild = self.client.guilds[int(guild)]
        except IndexError:
            raise ConsoleCommandSyntaxError("Invalid guild index.")
        try:
            chan = guild.text_channels[int(chan)]
        except IndexError:
            raise ConsoleCommandSyntaxError("Invalid channel index.")
        await chan.send(res)

    async def _delete_msg(self, args):
        """
        Deletes the given message.
        Syntax: delete_msg (id)
        """
        try:
            chanstr = args[0]
        except IndexError:
            raise ConsoleCommandSyntaxError("No arguments provided.")
        try:
            msg_id = int(args[1])
            if msg_id < 1:
                raise ValueError
        except ValueError:
            raise ConsoleCommandSyntaxError("Invalid amount.")
        except IndexError:
            raise ConsoleCommandSyntaxError("Missing amount argument.")
        try:
            guild, chan = re.match(r"(\d+).(\d+)", chanstr).group(1, 2)
        except AttributeError:
            raise ConsoleCommandSyntaxError("Invalid indices string.")
        try:
            guild = self.client.guilds[int(guild)]
        except IndexError:
            raise ConsoleCommandSyntaxError("Invalid guild index.")
        try:
            chan = guild.text_channels[int(chan)]
        except IndexError:
            raise ConsoleCommandSyntaxError("Invalid channel index.")
        try:
            msg = chan.get_message(msg_id)
        except NotFound:
            raise ConsoleCommandSyntaxError(f"Message with ID {msg_id} not found.")
        try:
            await msg.delete()
        except Forbidden:
            raise ConsoleCommandSyntaxError("Cannot delete message; no permissions.")

    async def _help(self, args):
        """
        Displays information on a specified command, or lists all available commands.
        Syntax: help [command]
        """
        if args:
            cmd = args[0].lower()
            try:
                doc = self.con_commands[cmd].__doc__
                if not doc:
                    raise AttributeError
                print(doc)
            except KeyError:
                print(f"No such command {cmd}. Use 'help' to list available commands.")
            except AttributeError:
                print(f"Command {cmd} has no documentation.")
        else:
            cmds = ", ".join(self.con_commands.keys())
            print(f"Available commands:\n{cmds}")

    @staticmethod
    async def _exec(args):
        """
        Executes a code snippet in the plugin's context. This is *not* a function; return cannot be used.
        Be careful with this, you can break things pretty badly!
        Syntax: exec (code)
        """
        cmd = " ".join(args)
        try:
            exec(cmd, globals(), locals())
        except Exception as e:
            raise ConsoleCommandSyntaxError(e)

    async def _last_error(self, args):
        try:
            args = args[0]
        except IndexError:
            raise ConsoleCommandSyntaxError("No error context specified.")
        if args == "command":
            e = self.client.command_dispatcher.last_error
        elif args == "event":
            e = self.plugin_manager.last_error
        elif args == "unhandled":
            e = self.client.last_error
        else:
            raise ConsoleCommandSyntaxError("Invalid error context.")
        if e:
            excstr = "\n".join(format_exception(*e))
            print(f"Last error in context {args}:\n{excstr}")
        else:
            print(f"No error in context {args}.")

    @staticmethod
    def _list_or_dict_subscript(obj, key):
        """
        Helper function to use key as a key if obj is a dict, or as an int index if list.

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
