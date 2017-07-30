import inspect
import asyncio
from plugin_manager import BasePlugin
from utils import respond


class CommandDispatcher(BasePlugin):
    name = "command_dispatcher"
    default_config = {"command_prefix": "!"}

    def activate(self):
        self.commands = {}
        for plugin in self.plugins.values():
            for _, mth in inspect.getmembers(plugin, predicate=inspect.ismethod):
                if hasattr(mth, "_command"):
                    self.register(mth, mth.name)

    def register(self, fn, name, is_alias=False):
        """
        Register commands in the command list and handle conflicts. If it's an
        alias, we don't want it to overwrite non-alias commands. Otherwise,
        overwrite based on priority, and failing that, load order.
        """
        self.logger.debug("Registering command {} from {}.".format(name, fn.__self__.name))

        if name in self.commands:
            oldfn = self.commands[name]
            if fn.priority >= oldfn.priority and not is_alias:
                self.commands[name] = fn
                self.logger.warning("Command {} from {} overwrites command {} from {}!"
                    .format(name, fn.__self__.name, oldfn.name, oldfn.__self__.name))
            else:
                self.logger.warning("Command {} from {} overwrites command {} from {}!"
                    .format(oldfn.name, oldfn.__self__.name, name, fn.__self__.name))
        else:
            self.commands[name] = fn

        if hasattr(fn, "aliases"):
            for alias in fn.aliases:
                self.register(fn, alias, is_alias=True)

    async def run_command(self, command, data):
        try:
            fn = self.commands[command]
            if fn.delcall:
                await self.client.delete_message(data)
            await fn(data)
        except KeyError:
            pass
        except (SyntaxError, SyntaxWarning) as e:
            if fn.human_syntax:
                await respond(self.client, data,
                    "**WARNING: Invalid syntax. ANALYSIS: Proper usage: {}.**".format(fn.human_syntax))
            else:
                await respond(self.client, data, "**WARNING: Invalid syntax.**")
        except Exception:
            self.logger.exception("Exception occured in command. ", exc_info=True)
            await respond(self.client, data, "**WARNING: Error occurred while running command.**")

    # Event hooks

    async def on_message(self, data):
        deco = self.plugin_config.command_prefix
        if data.author != self.client.user:
            cnt = data.content
            if cnt.startswith(deco):
                cmd = cnt[len(deco):].split()[0]
                if cmd in self.commands:
                    await self.run_command(cmd, data)
