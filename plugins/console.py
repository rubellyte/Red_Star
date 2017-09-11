import asyncio
import sys
import shlex
import re
import json
from plugin_manager import BasePlugin
from concurrent.futures import CancelledError
from rs_errors import ConsoleCommandSyntaxError


class ConsoleListener(BasePlugin):
    name = "console"
    docstring = "This is the terminal control plugin.\n" \
                "Current commands:\n" \
                "shutdown: shuts bot down\n" \
                "guilds: lists all the servers the bot is currently connected to\n" \
                "get_config: pretty-prints a value from a desired path. " \
                "Can substitute guild id with <server(number)>\n" \
                "help: you are reading it right now"


    async def activate(self):
        self.log_items = {}
        self.run_loop = True
        self.con_commands = {
            "set_config": self._set_config,
            "get_config": self._get_config_cmd,
            "shutdown": self._shutdown,
            "guilds": self._guilds,
            "channels": self._channels,
            "say": self._say,
            "help": self._help
        }
        self.task = asyncio.ensure_future(self._listen())

    async def deactivate(self):
        self.run_loop = False
        try:
            self.task.cancel()
        except CancelledError:
            pass

    async def _readline(self):
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, sys.stdin.readline)
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
        self.logger.info("Shutdown called from console.")
        self.run_loop = False
        await self.client.stop_bot()

    async def _get_config_cmd(self, args):
        if args:
            path = " ".join(args)
        else:
            path = None
        print(json.dumps(self._get_config(path), sort_keys=True, indent=2))

    def _get_config(self, path=None):
        conf = self.config_manager.config
        if path and path != "/":
            pattern = re.compile("<server(\d+)>")

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

            if len(args) == 4:
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
        for i, guild in enumerate(self.client.guilds):
            print(f"{i:02d} : {guild.name[:40].ljust(40)} : {guild.id}")

    async def _channels(self, args):
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

    async def _say(self, args):
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

    async def _help(self, args):
        print(self.docstring)
