import asyncio
import threading
import sys
import shlex
import re
import json
from plugin_manager import BasePlugin
from concurrent.futures import CancelledError


class ConsoleListener(BasePlugin):
    name = "console"
    docstring = "This is the terminal control plugin.\n" \
                "Current commands:\n" \
                "shutdown : shuts bot down\n" \
                "guilds/servers/guildlist/serverlist : lists all the servers the bot is currently connected to\n" \
                "get_config : pretty-prints a value from a desired path. " \
                "Can substitute guild id with <server(number)>\n" \
                "help : you are reading it right now"


    async def activate(self):
        self.log_items = {}
        self.run_loop = True
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
            print(args)
            if not args:
                pass
            elif args[0].lower() == "shutdown":
                self.logger.info("Shutdown called from console.")
                self.run_loop = False
                await self.client.stop_bot()

            elif args[0].lower() == "get_config":
                if len(args) > 1:
                    path = args[1].lower()
                else:
                    path = None
                print(json.dumps(self._get_config(path), sort_keys=True, indent=2))

            elif args[0].lower() == "set_config":
                if len(args) not in [3, 4]:
                    print("Useage : set_config (path) (value) [type]")
                t_path = args[1].lower().split("/")
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
                            print(f"{key} is not a valid integer")
                            continue
                        except IndexError:
                            if isinstance(val, list):
                                print(f"Extending list {t_path}.")
                                key = len(val)
                                val.append(None)
                                orig = None
                            else:
                                print(f"Path {args[1].lower()} is invalid.")
                    except KeyError:
                        if isinstance(val, dict):
                            print(f"Extending dict {t_path}.")
                            val[key] = None
                            orig = None
                        else:
                            print(f"Path {args[1].lower()} is invalid.")

                    if len(args) == 4:
                        if args[3].lower() == "float":
                            try:
                                value = float(args[2])
                                val[key] = value
                            except ValueError:
                                print(f"{args[2]} is not a valid float")
                                continue
                        elif args[3].lower() == "int":
                            try:
                                value = int(args[2])
                                val[key] = value
                            except ValueError:
                                print(f"{args[2]} is not a valid int")
                                continue
                        elif args[3].lower() in ["str", "string"]:
                            val[key] = args[2]
                        elif args[3].lower() in ["bool"]:
                            if args[2].lower() == "true":
                                val[key] = True
                            elif args[2].lower() == "false":
                                val[key] = False
                            else:
                                print(f"{args[2]} is not a valid bool")
                                continue
                        elif args[3].lower() in ["dict"]:
                            val[key] = {}
                        elif args[3].lower() in ["list"]:
                            val[key] = []
                        elif args[3].lower() == "yes, delete this":
                            val.pop(key)
                    else:
                        if isinstance(orig, str):
                            val[key] = args[2]
                        elif isinstance(orig, bool):
                            if args[2].lower() == "true":
                                val[key] = True
                            elif args[2].lower() == "false":
                                val[key] = False
                            else:
                                print(f"{args[2]} is not a valid bool")
                                continue
                        elif isinstance(orig, float):
                            try:
                                value = float(args[2])
                                val[key] = value
                            except ValueError:
                                print(f"{args[2]} is not a valid float")
                                continue
                        elif isinstance(orig, int):
                            try:
                                value = int(args[2])
                                val[key] = value
                            except ValueError:
                                print(f"{args[2]} is not a valid int")
                                continue
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

            elif args[0].lower() in ["serverlist", "guildlist", "servers", "guilds"]:
                k = 0
                for guild in self.client.guilds:
                    print(f"{k:02d} : {guild.name[:40].ljust(40)} : {guild.id}")
                    k += 1

            elif args[0].lower() == "help":
                print(self.docstring)

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
                        print(f"{k} is not a valid integer.")
                        return None
                    except IndentationError:
                        print(f"Path {path} is invalid.")
                        return None
                except KeyError:
                    print(f"Path {path} is invalid.")
                    return None
            else:
                return val
        else:
            return conf
