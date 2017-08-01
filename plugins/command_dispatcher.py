import inspect
from plugin_manager import BasePlugin
from utils import respond


class CommandDispatcher(BasePlugin):
    name = "command_dispatcher"
    default_config = {
        "command_prefix": "!",
        "use_command_channel": True,
        "command_channel": ""
    }

    async def activate(self):
        self.commands = {}

    async def on_all_plugins_loaded(self):
        for plugin in self.plugins.values():
            for _, mth in inspect.getmembers(plugin, predicate=inspect.ismethod):
                if hasattr(mth, "_command"):
                    self.register(mth, mth.name)

    async def on_plugin_activated(self, plgname):
        plugin = self.plugins[plgname]
        for _, mth in inspect.getmembers(plugin, predicate=inspect.ismethod):
            if hasattr(mth, "_command"):
                self.register(mth, mth.name)

    async def on_plugin_deactivated(self, plgname):
        plugin = self.client.plugin_manager.plugins[plgname]
        for _, mth in inspect.getmembers(plugin, predicate=inspect.ismethod):
            if hasattr(mth, "_command"):
                self.deregister(mth, mth.name)

    def register(self, fn, name, is_alias=False):
        """
        Register commands in the command list and handle conflicts. If it's an
        alias, we don't want it to overwrite non-alias commands. Otherwise,
        overwrite based on priority, and failing that, load order.
        :param fn: The command function, with its added information.
        :param name: The command's name, for indexing.
        :param is_alias: A boolean that tells the registrar not to overwrite other commands.
        :return: None.
        """
        self.logger.debug(f"Registering command {name} from {fn.__self__.name}.")

        if name in self.commands:
            oldfn = self.commands[name]
            if fn.priority >= oldfn.priority and not is_alias:
                self.commands[name] = fn
                self.logger.warning(f"Command {name} from {fn.__self__.name} overwrites command {oldfn.name} from "
                                    f"{oldfn.__self__.name}!")
            else:
                self.logger.warning(f"Command {oldfn.name} from {oldfn.__self__.name} overwrites command {name} from "
                                    f"{fn.__self__.name}!")
        else:
            self.commands[name] = fn

        if hasattr(fn, "_aliases") and not is_alias:
            for alias in fn._aliases:
                self.register(fn, alias, is_alias=True)

    def deregister(self, fn, name, is_alias=False):
        """
        Deregister commands from the command list when their plugin is deactivated.
        :param fn: The command function, with its added information.
        :param name: The command's name, for indexing.
        :param is_alias: A boolean that tells the registrar not to overwrite other commands.
        :return: None.
        """
        self.logger.debug(f"Deregistering command {name} from {fn.__self__.name}.")

        if name in self.commands:
            oldfn = self.commands[name]
            # Make sure the command isn't another plugin's
            if fn == oldfn:
                del self.commands[name]
        else:
            self.logger.debug(f"Could not deregister command {name}, no such command!")

        if hasattr(fn, "_aliases") and not is_alias:
            for alias in fn._aliases:
                self.deregister(fn, alias, is_alias=True)

    async def run_command(self, command, data):
        try:
            fn = self.commands[command]
        except KeyError:
            return
        try:
            if self.plugin_config.use_command_channel:
                chan = self.client.get_channel(self.plugin_config.command_channel)
                if not fn.run_anywhere and data.channel != chan:
                    return
            await fn(data)
            if fn.delcall:
                await self.client.delete_message(data)
        except (SyntaxError, SyntaxWarning) as e:
            err = e if e else "Invalid syntax."
            if fn.syntax:
                deco = self.plugin_config.command_prefix
                await respond(self.client, data,
                              f"**WARNING: {err} ANALYSIS: Proper usage: {deco}{command} {fn.syntax}.**")
            else:
                await respond(self.client, data, f"**WARNING: {err}.**")
        except PermissionError:
            await respond(self.client, data, "**NEGATIVE. INSUFFICIENT PERMISSION: <usernick>.**")
        except Exception:
            self.logger.exception("Exception occurred in command. ", exc_info=True)
            await respond(self.client, data, "**WARNING: Error occurred while running command.**")

    # Event hooks

    async def on_message(self, data):
        deco = self.plugin_config.command_prefix
        if data.author != self.client.user:
            cnt = data.content
            if cnt.startswith(deco):
                cmd = cnt[len(deco):].split()[0].lower()
                if cmd in self.commands:
                    await self.run_command(cmd, data)
