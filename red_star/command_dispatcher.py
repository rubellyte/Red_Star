import inspect
import logging
from asyncio import sleep
from sys import exc_info
from red_star.rs_errors import ChannelNotFoundError, CommandSyntaxError, UserPermissionError
from discord import Forbidden
from red_star.rs_utils import respond


class CommandDispatcher:
    def __init__(self, client):
        self.client = client
        self.config_manager = client.config_manager
        self.logger = logging.getLogger("red_star.command_dispatcher")
        try:
            self.conf = client.config_manager.config["command_dispatcher"]
        except KeyError:
            client.config_manager.config["command_dispatcher"] = {}
            self.conf = client.config_manager.config["command_dispatcher"]
        self.default_config = {
            "command_prefix": "!"
        }

        self.commands = {}
        self.last_error = None

    def register_plugin(self, plugin):
        for _, mth in inspect.getmembers(plugin, predicate=inspect.ismethod):
            if hasattr(mth, "_command"):
                self.register(mth, mth.name.lower())

    def deregister_plugin(self, plugin):
        for _, mth in inspect.getmembers(plugin, predicate=inspect.ismethod):
            if hasattr(mth, "_command"):
                self.deregister(mth, mth.name.lower())

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

        if hasattr(fn, "aliases") and not is_alias:
            for alias in fn.aliases:
                self.register(fn, alias.lower(), is_alias=True)

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

        if hasattr(fn, "aliases") and not is_alias:
            for alias in fn.aliases:
                self.deregister(fn, alias, is_alias=True)

    # noinspection PyBroadException
    async def run_command(self, command, msg, dm_cmd=False):
        try:
            fn = self.commands[command]
        except KeyError:
            return
        if dm_cmd:
            if msg.author.id not in self.config_manager.config.get("bot_maintainers", []):
                return
            if not fn.dm_command:
                return
            try:
                await fn(msg)
            except CommandSyntaxError as e:
                err = e if e else "Invalid syntax."
                if fn.syntax:
                    await respond(msg, f"**WARNING: {err} ANALYSIS: Proper usage: !{fn.name} {fn.syntax}.**")
                else:
                    await respond(msg, f"**WARNING: {err}.**")
            except Exception:
                self.last_error = exc_info()
                self.logger.exception("Exception occurred in command. ", exc_info=True)
                await respond(msg, "**WARNING: Error occurred while running command.**")

        else:
            gid = str(msg.guild.id)
            try:
                if not fn.run_anywhere:
                    try:
                        cmd_channel = self.client.channel_manager.get_channel(msg.guild, "commands")
                        if msg.channel != cmd_channel:
                            return
                    except ChannelNotFoundError:
                        pass
                await fn(msg)
                if fn.delcall:
                    await sleep(1)
                    await msg.delete()
            except CommandSyntaxError as e:
                err = e if e else "Invalid syntax."
                if fn.syntax:
                    deco = self.conf[gid]["command_prefix"]
                    await respond(msg, f"**WARNING: {err} ANALYSIS: Proper usage: {deco}{fn.name} {fn.syntax}.**")
                else:
                    await respond(msg, f"**WARNING: {err}**")
            except UserPermissionError as e:
                err = f"\nANALYSIS: {e}" if str(e) else ""
                await respond(msg, f"**NEGATIVE. INSUFFICIENT PERMISSION: <usernick>.{err}**")
            except Forbidden:
                await respond(msg, "**NEGATIVE. This unit does not have permission to perform that action.**")
            except ChannelNotFoundError as e:
                await respond(msg, f"**NEGATIVE. Channel type `{e}` is not set on this server.**")
            except Exception:
                self.last_error = exc_info()
                self.logger.exception("Exception occurred in command. ", exc_info=True)
                await respond(msg, "**WARNING: Error occurred while running command.**")

    # Event hooks

    async def command_check(self, msg):
        try:
            gid = str(msg.guild.id)
            if gid not in self.conf:
                self.conf[gid] = self.default_config.copy()
            deco = self.conf[gid]["command_prefix"]
            dm_cmd = False
        except AttributeError:  # Oops, it's a DM isn't it
            deco = "!"
            dm_cmd = True
        if msg.author != self.client.user:
            cnt = msg.content
            if cnt.startswith(deco):
                cmd = cnt[len(deco):].split()[0].lower()
                if cmd in self.commands:
                    await self.run_command(cmd, msg, dm_cmd=dm_cmd)


class Command:
    """
    Defines a decorator that encapsulates a chat command. Provides a common
    interface for all commands, including roles, documentation, usage syntax,
    and aliases.
    """

    def __init__(self, name, *aliases, perms=None, doc=None, syntax=None, priority=0, delcall=False,
                 run_anywhere=False, bot_maintainers_only=False, dm_command=False, category="other"):
        if syntax is None:
            syntax = ()
        if isinstance(syntax, str):
            syntax = (syntax,)
        if doc is None:
            doc = ""
        self.name = name
        if not perms:
            perms = set()
        if isinstance(perms, str):
            perms = {perms}
        self.perms = perms
        self.syntax = syntax
        self.human_syntax = " ".join(syntax)
        self.doc = doc
        self.aliases = aliases
        self.priority = priority
        self.delcall = delcall
        self.run_anywhere = run_anywhere
        self.category = category
        self.bot_maintainers_only = bot_maintainers_only
        self.dm_command = dm_command

    def __call__(self, f):
        """
        Whenever a command is called, its handling gets done here.

        :param f: The function the Command decorator is wrapping.
        :return: The now-wrapped command, with all the trappings.
        """

        async def wrapped(s, msg):
            if msg.guild is None and self.dm_command:  # The permission check was handled pre-call.
                return await f(s, msg)
            user_perms = msg.author.permissions_in(msg.channel)
            user_perms = {x for x, y in user_perms if y}
            try:
                if not user_perms >= self.perms and msg.author.id \
                        not in s.config_manager.config.get("bot_maintainers", []):
                    raise PermissionError
                if self.bot_maintainers_only and msg.author.id \
                        not in s.config_manager.config.get("bot_maintainers", []):
                    raise PermissionError
                return await f(s, msg)
            except PermissionError:
                return await respond(msg, "**NEGATIVE. INSUFFICIENT PERMISSION: <usernick>.**")

        wrapped._command = True
        wrapped.aliases = self.aliases
        wrapped.__doc__ = self.doc
        wrapped.name = self.name
        wrapped.perms = self.perms
        wrapped.syntax = self.human_syntax
        wrapped.priority = self.priority
        wrapped.delcall = self.delcall
        wrapped.run_anywhere = self.run_anywhere
        wrapped.dm_command = self.dm_command
        wrapped.category = self.category
        return wrapped
