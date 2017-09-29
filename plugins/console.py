import asyncio
import shlex
import re
import json
import logging
import discord
from plugin_manager import BasePlugin
from concurrent.futures import CancelledError
from rs_errors import ConsoleCommandSyntaxError
from discord import NotFound, Forbidden
from traceback import format_exception


class ConsoleListener(BasePlugin):
    name = "console"
    default_config = {
        "allow_stdout_logging": False,
        "allow_stdout_errors": True
    }

    async def activate(self):
        self.log_items = {}
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
            self.logger.info("Disabling STDOUT logger and starting console...")
            for h in base_logger.handlers:
                if type(h) == logging.StreamHandler:
                    if self.plugin_config.allow_stdout_errors:
                        h.setLevel(logging.ERROR)
                    else:
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

    async def _listen(self):
        conf = self.config_manager.config
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

    async def _shutdown(self, args):
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
            path = None
        print(json.dumps(self._get_config(path), sort_keys=True, indent=2))

    def _get_config(self, path=None):
        conf = self.config_manager.config
        if path and path != "/":
            pattern = re.compile("<guild(\d+)>")

            t_s = pattern.search(path)
            if t_s:
                t_i = min(max(0, int(t_s.group(1))), len(self.client.guilds)-1)
                path = pattern.sub(str(self.client.guilds[t_i].id), path)

            if path.startswith("/"):
                path = path[1:]
            if path.endswith("/"):
                path = path[:-1]
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
                        raise ConsoleCommandSyntaxError(f"{k} is not a valid integer.")
                    except IndentationError:
                        raise ConsoleCommandSyntaxError(f"Path {path} is invalid.")
                except KeyError:
                    raise ConsoleCommandSyntaxError(f"Path {path} is invalid.")
            else:
                return val
        else:
            return conf

    async def _set_config(self, args):
        """
        Sets the specified config key to the specified value, or all of the config if none specified.
        Use <guildX>, where X is the index of a guild as shown in 'guilds', to substitute in a guild's ID.
        An optional third argument, type, can be used to set to a specific type of value.
        Syntax: set_config (path) (value) [type]
        """
        if len(args) not in [2, 3]:
            print("Useage : set_config (path) (value) [type]")
        t_path = args[0].lower().split("/")
        key = t_path.pop(-1)
        t_path = "/".join(t_path)
        val = self._get_config(t_path)
        if t_path == "":
            t_path = "/"
        if val is not None:
            try:
                orig = val[key]
            except TypeError:
                try:
                    key = int(key)
                    orig = val[key]
                except ValueError:
                    raise ConsoleCommandSyntaxError(f"{key} is not a valid integer")
                except IndexError:
                    if isinstance(val, list):
                        print(f"Extending list {t_path}.")
                        key = len(val)
                        val.append(None)
                        orig = None
                    else:
                        raise ConsoleCommandSyntaxError(f"Path {args[0].lower()} is invalid.")
            except KeyError:
                if isinstance(val, dict):
                    print(f"Extending dict {t_path}.")
                    val[key] = None
                    orig = None
                else:
                    raise ConsoleCommandSyntaxError(f"Path {args[0].lower()} is invalid.")

            if len(args) == 3:
                if args[2].lower() == "float":
                    try:
                        value = float(args[2])
                        val[key] = value
                    except ValueError:
                        raise ConsoleCommandSyntaxError(f"{args[1]} is not a valid float")
                elif args[2].lower() == "int":
                    try:
                        value = int(args[1])
                        val[key] = value
                    except ValueError:
                        raise ConsoleCommandSyntaxError(f"{args[1]} is not a valid int")
                elif args[2].lower() in ["str", "string"]:
                    val[key] = args[1]
                elif args[2].lower() in ["bool"]:
                    if args[1].lower() == "true":
                        val[key] = True
                    elif args[1].lower() == "false":
                        val[key] = False
                    else:
                        raise ConsoleCommandSyntaxError(f"{args[1]} is not a valid bool")
                elif args[2].lower() in ["dict"]:
                    val[key] = {}
                elif args[2].lower() in ["list"]:
                    val[key] = []
                elif args[2].lower() == "yes, delete this":
                    val.pop(key)
            else:
                if isinstance(orig, str):
                    val[key] = args[1]
                elif isinstance(orig, bool):
                    if args[1].lower() == "true":
                        val[key] = True
                    elif args[1].lower() == "false":
                        val[key] = False
                    else:
                        raise ConsoleCommandSyntaxError(f"{args[1]} is not a valid bool")
                elif isinstance(orig, float):
                    try:
                        value = float(args[1])
                        val[key] = value
                    except ValueError:
                        raise ConsoleCommandSyntaxError(f"{args[1]} is not a valid float")
                elif isinstance(orig, int):
                    try:
                        value = int(args[1])
                        val[key] = value
                    except ValueError:
                        raise ConsoleCommandSyntaxError(f"{args[1]} is not a valid int")
            t_val = None
            if isinstance(val, dict) and key in val:
                t_val = val[key]
            elif isinstance(val, list) and 0 <= key < len(val):
                t_val = val[key]
            if t_val and orig:
                print(f"Value {key} of {t_path} successfully changed to {t_val} from {orig}")
            elif t_val:
                print(f"Value {key} of {t_path} successfully set to {t_val}")
            else:
                print(f"Value {key} of {t_path} successfully deleted")
            self.config_manager.save_config()

    async def _guilds(self, args):
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
            id = int(args[1])
            if id < 1:
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
            msg = chan.get_message(id)
        except NotFound:
            raise ConsoleCommandSyntaxError(f"Message with ID {id} not found.")
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

    async def _exec(self, args):
        """
        Executes a code snippet in the plugin's context. This is *not* a function; return cannot be used.
        Be careful with this, you can break things pretty badly!
        Syntax: exec (code)
        """
        cmd = " ".join(args)
        try:
            exec(cmd)
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