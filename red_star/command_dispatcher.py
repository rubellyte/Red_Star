from __future__ import annotations
import inspect
import logging
from asyncio import sleep
from sys import exc_info
from functools import wraps
from discord import Forbidden
from red_star.rs_errors import ChannelNotFoundError, CommandSyntaxError, UserPermissionError
from red_star.rs_utils import respond, sub_user_data

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import discord
    import plugin_manager
    from red_star.client import RedStar
    from channel_manager import ChannelManager


class CommandDispatcher:
    def __init__(self, client: RedStar, guild: discord.Guild, channel_manager: ChannelManager):
        self.client = client
        self.guild = guild
        self.channel_manager = channel_manager
        self.config_manager = client.config_manager
        self.logger = logging.getLogger(f"red_star.command_dispatcher.{guild.id}")
        self.conf = self.config_manager.get_server_config(self.guild, "command_dispatcher",
                                                          default_config={"command_prefix": "!",
                                                                          "permission_overrides": {}})

        self.commands = {}
        self.last_error = None

    async def on_message(self, msg: discord.Message):
        await self.command_check(msg)

    def initialize_command_permissions(self, command: Command):
        overrides = self.conf["permission_overrides"]

        if command.name in overrides:
            if "permissions_all" in overrides:
                command.perms.permissions_all = set(overrides["permissions_all"])
            if "optional_permissions" in overrides:
                command.perms.optional_permissions = {k: set(v) for k, v in overrides["optional_permissions"].items()}
            command.perms.permissions_any = set(overrides.get("permissions_any", []))
            command.perms.user_overrides = set(overrides.get("user_overrides", []))
            command.perms.role_overrides = set(overrides.get("role_overrides", []))

        command.perms.bot_maintainers = self.config_manager.config["global"].get("bot_maintainers", [])

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
        """
        self.logger.debug(f"Registering command {name} from {fn.__self__.name}.")

        if not is_alias:
            self.initialize_command_permissions(fn)

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
                self.deregister(fn, alias.lower(), is_alias=True)

    # noinspection PyBroadException
    async def run_command(self, command, msg, dm_cmd=False):
        try:
            fn = self.commands[command]
        except KeyError:
            return
        if dm_cmd:
            # if msg.author.id not in self.config_manager.config.get("bot_maintainers", []):
            #     return
            # if not fn.dm_command:
            #     return
            # try:
            #     await fn(msg)
            # except CommandSyntaxError as e:
            #     err = e if e else "Invalid syntax."
            #     if fn.syntax:
            #         await respond(msg, f"**WARNING: {err} ANALYSIS: Proper usage: {fn.name} {fn.syntax}.**")
            #     else:
            #         await respond(msg, f"**WARNING: {err}**")
            # except Exception:
            #     self.last_error = exc_info()
            #     self.logger.exception("Exception occurred in command. ", exc_info=True)
            #     await respond(msg, "**WARNING: Error occurred while running command.**")
            return  # TODO: DM commands???

        else:
            try:
                if not fn.run_anywhere:
                    try:
                        cmd_channel = self.channel_manager.get_channel("commands")
                        if msg.channel != cmd_channel:
                            return
                    except ChannelNotFoundError:
                        pass
                await fn(msg)
                if fn.delcall:
                    await sleep(1)
                    try:
                        await msg.delete()
                    except Forbidden:
                        pass
            except CommandSyntaxError as e:
                err = e if e else "Invalid syntax."
                if fn.syntax:
                    deco = self.conf["command_prefix"].lower()
                    await respond(msg, f"**WARNING: {err} ANALYSIS: Proper usage: {deco}{fn.name} {fn.syntax}.**")
                else:
                    await respond(msg, f"**WARNING: {err}**")
            except UserPermissionError as e:
                err = f"\nANALYSIS: {e}" if str(e) else ""
                await respond(msg, sub_user_data(msg.author,
                                                 f"**NEGATIVE. INSUFFICIENT PERMISSION: <usernick>.{err}**"))
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
            deco = self.conf["command_prefix"]
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

    def __init__(self, name, *aliases, perms=None, optional_perms=None, doc=None, syntax=None, priority=0,
                 delcall=False, run_anywhere=False, bot_maintainers_only=False, dm_command=False, category="other"):
        if syntax is None:
            syntax = ()
        if isinstance(syntax, str):
            syntax = (syntax,)
        if doc is None:
            doc = ""

        if not perms:
            perms = set()
        if isinstance(perms, str):
            perms = {perms}
        self.perms = CommandPermissions(perms, bot_maintainers_only=bot_maintainers_only,
                                        optional_permissions=optional_perms)

        self.name = name
        self.syntax = syntax
        self.human_syntax = " ".join(syntax)
        self.doc = doc
        self.aliases = aliases
        self.priority = priority
        self.delcall = delcall
        self.run_anywhere = run_anywhere
        self.category = category
        self.dm_command = dm_command

    def __call__(self, f):
        """
        Whenever a command is called, its handling gets done here.

        :param f: The function the Command decorator is wrapping.
        :return: The now-wrapped command, with all the trappings.
        """
        @wraps(f)
        async def wrapped(s: plugin_manager.BasePlugin, msg: discord.Message):
            if msg.guild is None and self.dm_command:  # The permission check was handled pre-call.
                return await f(s, msg)
            # user_perms = {x for x, y in msg.channel.permissions_for(msg.author) if y}
            # if msg.guild.voice_client:
            #     user_perms |= {x for x, y in msg.guild.voice_client.channel.permissions_for(msg.author) if y}
            # if (not user_perms >= self.perms or self.bot_maintainers_only) \
            #         and msg.author.id not in s.config_manager.config["global"].get("bot_maintainers", []):
            #     raise UserPermissionError
            if self.perms.check_permissions(msg.author, msg.channel):
                return await f(s, msg)
            else:
                raise UserPermissionError

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


class CommandPermissions:
    def __init__(self, permissions_all, permissions_any=None, role_overrides=None, user_overrides=None,
                 optional_permissions=None, bot_maintainers_only=False):
        if permissions_any is None:
            permissions_any = set()
        if role_overrides is None:
            role_overrides = set()
        if user_overrides is None:
            user_overrides = set()
        if optional_permissions is None:
            optional_permissions = {}
        self.permissions_all = permissions_all
        self.permissions_any = permissions_any
        self.role_overrides = role_overrides
        self.user_overrides = user_overrides
        self.optional_permissions = optional_permissions
        self.bot_maintainers = []
        self.bot_maintainers_only = bot_maintainers_only

    @classmethod
    def from_existing(cls, existing_obj: CommandPermissions, permissions_all=None, permissions_any=None,
                      role_overrides=None, user_overrides=None, optional_permissions=None):
        if permissions_all is None:
            permissions_all = existing_obj.permissions_all
        if permissions_any is None:
            permissions_any = existing_obj.permissions_any
        if role_overrides is None:
            role_overrides = existing_obj.role_overrides
        if user_overrides is None:
            user_overrides = existing_obj.user_overrides
        if optional_permissions is None:
            optional_permissions = existing_obj.optional_permissions
        return cls(permissions_all, permissions_any, role_overrides, user_overrides, optional_permissions,
                   bot_maintainers_only=existing_obj.bot_maintainers_only)

    def update(self, new_perms: CommandPermissions):
        self.permissions_all = new_perms.permissions_all
        self.permissions_any = new_perms.permissions_any
        self.role_overrides = new_perms.role_overrides
        self.user_overrides = new_perms.user_overrides
        self.optional_permissions = new_perms.optional_permissions

    def check_permissions(self, member: discord.Member, channel: discord.abc.GuildChannel) -> bool:
        if member.id in self.bot_maintainers:
            return True
        elif self.bot_maintainers_only:
            return False

        if member.id in self.user_overrides:
            return True
        if not {x.id for x in member.roles}.isdisjoint(self.role_overrides):
            return True

        member_permissions_set = {x for x, y in channel.permissions_for(member) if y}
        if member.guild.voice_client:
            member_permissions_set |= {x for x, y in member.guild.voice_client.channel.permissions_for(member) if y}

        if self.permissions_all and not (member_permissions_set > self.permissions_all):
            return False
        if self.permissions_any and member_permissions_set.isdisjoint(self.permissions_any):
            return False
        return True

    def check_optional_permissions(self, optional_permission_set: str, member: discord.Member,
                                   channel: discord.abc.GuildChannel) -> bool:
        if optional_permission_set not in self.optional_permissions:
            raise SyntaxError(f"No such permission set {optional_permission_set}")

        if member.id in self.bot_maintainers:
            return True

        if member.id in self.user_overrides:
            return True
        if not {x.id for x in member.roles}.isdisjoint(self.role_overrides):
            return True

        member_permissions_set = {x for x, y in channel.permissions_for(member) if y}
        if member.guild.voice_client:
            member_permissions_set |= {x for x, y in member.guild.voice_client.channel.permissions_for(member) if y}

        if member_permissions_set > self.optional_permissions[optional_permission_set]:
            return True
        return False
