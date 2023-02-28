import discord
import shlex
from red_star.plugin_manager import BasePlugin
from red_star.command_dispatcher import Command, CommandPermissions
from red_star.rs_errors import CommandSyntaxError, UserPermissionError
from red_star.rs_utils import respond, find_user, find_role

# TODO: Refactors. This could probably be deduplicated a lot. Also evaluate whether update() method and creation of
# new permission objects is actually necessary...


class CommandPermissionCommands(BasePlugin):
    name = "command_permission_commands"
    version = "1.0"
    author = "medeor413"
    description = "A somewhat confusingly-named plugin that implements commands to edit the necessary permissions " \
                  "for other commands."

    async def activate(self):
        self.permission_overrides = self.command_dispatcher.config["permission_overrides"]
        self.commands = self.command_dispatcher.commands

    @Command("AddCommandPermission", "AddCmdPerm",
             doc="Adds a required permission(s) to a given command. All of these permissions are required to run a "
                 "command.",
             syntax="(command) (permissions_to_add)",
             perms="manage_guild",
             category="command_permissions")
    async def _add_command_permission(self, msg: discord.Message):
        command_to_edit, perms_to_add = self._validate_arguments_permissions(msg.clean_content)
        existing_perms = command_to_edit.perms
        successfully_added_perms = {x.upper() for x in perms_to_add if x not in existing_perms.permissions_all}

        if not existing_perms.check_permissions(msg.author, msg.channel):
            raise UserPermissionError

        new_perms = CommandPermissions.from_existing(existing_perms,
                                                     permissions_all=existing_perms.permissions_all | perms_to_add)

        if not new_perms.check_permissions(msg.author, msg.channel):
            raise UserPermissionError

        command_to_edit.perms.update(new_perms)
        self.permission_overrides[command_to_edit.name.lower()]["permissions_all"] = list(new_perms.permissions_all)
        self.config_manager.save_config()

        await respond(msg, f"**ANALYSIS: Command {command_to_edit.name} edited successfully. Added required "
                           f"permissions:** `{', '.join(successfully_added_perms)}`")

    @Command("RemoveCommandPermission", "RmCmdPerm",
             doc="Removes a required permission(s) from a given command. If all required permissions are removed "
                 "from a command, and it has no \"any of\" permissions, it can be used by anyone.",
             syntax="(command) (permissions_to_remove)",
             perms="manage_guild",
             category="command_permissions")
    async def _rm_command_permission(self, msg: discord.Message):
        command_to_edit, perms_to_remove = self._validate_arguments_permissions(msg.clean_content)
        existing_perms = command_to_edit.perms

        if not existing_perms.check_permissions(msg.author, msg.channel):
            raise UserPermissionError

        new_perms = CommandPermissions.from_existing(existing_perms,
                                                     permissions_all=existing_perms.permissions_all - perms_to_remove)

        difference_set = existing_perms.permissions_all - new_perms.permissions_all

        command_to_edit.perms.update(new_perms)
        self.permission_overrides[command_to_edit.name.lower()]["permissions_all"] = list(new_perms.permissions_all)
        self.config_manager.save_config()

        await respond(msg, f"**ANALYSIS: Command {command_to_edit.name} edited successfully. Removed required "
                           f"permissions:** `{', '.join(x.upper() for x in difference_set)}`")

    @Command("AddCommandPermissionAnyOf", "AddCmdPermAny",
             doc="Adds an \"any of\" permission to a given command. Any one of the permissions in the \"any of\" "
                 "list are required to run a command.",
             syntax="(command) (permissions_to_add)",
             perms="manage_guild",
             category="command_permissions")
    async def _add_command_permission_any(self, msg: discord.Message):
        command_to_edit, perms_to_add = self._validate_arguments_permissions(msg.clean_content)
        existing_perms = command_to_edit.perms
        successfully_added_perms = {x.upper() for x in perms_to_add if x not in existing_perms.permissions_any}

        if not existing_perms.check_permissions(msg.author, msg.channel):
            raise UserPermissionError

        new_perms = CommandPermissions.from_existing(existing_perms,
                                                     permissions_any=existing_perms.permissions_any | perms_to_add)

        if not new_perms.check_permissions(msg.author, msg.channel):
            raise UserPermissionError

        command_to_edit.perms.update(new_perms)
        self.permission_overrides[command_to_edit.name.lower()]["permissions_any"] = list(new_perms.permissions_any)
        self.config_manager.save_config()

        await respond(msg, f"**ANALYSIS: Command {command_to_edit.name} edited successfully. Added \"any of\" "
                           f"permissions:** `{', '.join(successfully_added_perms)}`")

    @Command("RemoveCommandPermissionAnyOf", "RmCmdPermAny",
             doc="Removes an \"any of\" permission from a given command. If all required permissions are removed "
                 "from a command, and it has no \"any of\" permissions, it can be used by anyone.",
             syntax="(command) (permissions_to_remove)",
             perms="manage_guild",
             category="command_permissions")
    async def _rm_command_permission_any(self, msg: discord.Message):
        command_to_edit, perms_to_remove = self._validate_arguments_permissions(msg.clean_content)
        existing_perms = command_to_edit.perms

        if not existing_perms.check_permissions(msg.author, msg.channel):
            raise UserPermissionError

        new_perms = CommandPermissions.from_existing(existing_perms,
                                                     permissions_any=existing_perms.permissions_any - perms_to_remove)
        difference_set = existing_perms.permissions_any - new_perms.permissions_any

        command_to_edit.perms.update(new_perms)
        self.permission_overrides[command_to_edit.name.lower()]["permissions_any"] = list(new_perms.permissions_any)
        self.config_manager.save_config()

        await respond(msg, f"**ANALYSIS: Command {command_to_edit.name} edited successfully. Removed \"any of\" "
                           f"permissions:** `{', '.join(x.upper() for x in difference_set)}`")

    @Command("AddCommandUserOverride", "AddCmdUser",
             doc="Adds a user override(s) to a given command. A user with an override can use a command as if they "
                 "have all required and optional permissions.",
             syntax="(command) (users_to_add)",
             perms="manage_guild",
             category="command_permissions")
    async def _add_command_user_override(self, msg: discord.Message):
        command_to_edit, users_to_add = self._validate_arguments_users(msg.clean_content)
        existing_perms = command_to_edit.perms
        ids_to_add = {x.id for x in users_to_add}
        successfully_added_users = {x.name for x in users_to_add if x.id not in existing_perms.user_overrides}

        if not existing_perms.check_permissions(msg.author, msg.channel):
            raise UserPermissionError

        new_perms = CommandPermissions.from_existing(existing_perms,
                                                     user_overrides=existing_perms.user_overrides | ids_to_add)

        command_to_edit.perms.update(new_perms)
        self.permission_overrides[command_to_edit.name.lower()]["user_overrides"] = list(new_perms.user_overrides)
        self.config_manager.save_config()

        await respond(msg, f"**ANALYSIS: Command {command_to_edit.name} edited successfully. Added user overrides:** "
                           f"`{', '.join(successfully_added_users)}`")

    @Command("RemoveCommandUserOverride", "RmCmdUser",
             doc="Removes a user override(s) from a given command.",
             syntax="(command) (users_to_remove)",
             perms="manage_guild",
             category="command_permissions")
    async def _rm_command_user_override(self, msg: discord.Message):
        command_to_edit, users_to_remove = self._validate_arguments_users(msg.clean_content)
        existing_perms = command_to_edit.perms
        ids_to_remove = {x.id for x in users_to_remove}
        successfully_removed_users = {x.name for x in users_to_remove if x in existing_perms.user_overrides}

        if not existing_perms.check_permissions(msg.author, msg.channel):
            raise UserPermissionError

        new_perms = CommandPermissions.from_existing(existing_perms,
                                                     user_overrides=existing_perms.user_overrides - ids_to_remove)

        if not new_perms.check_permissions(msg.author, msg.channel):
            raise UserPermissionError

        command_to_edit.perms.update(new_perms)
        self.permission_overrides[command_to_edit.name.lower()]["user_overrides"] = list(new_perms.user_overrides)
        self.config_manager.save_config()

        await respond(msg, f"**ANALYSIS: Command {command_to_edit.name} edited successfully. Removed user "
                           f"overrides:** `{', '.join(successfully_removed_users)}`")

    @Command("AddCommandRoleOverride", "AddCmdRole",
             doc="Adds a role override(s) to a given command. Users with any of the roles in the override list can "
                 "use a command as if they have all required and optional permissions.",
             syntax="(command) (roles_to_add)",
             perms="manage_guild",
             category="command_permissions")
    async def _add_command_role_override(self, msg: discord.Message):
        command_to_edit, roles_to_add = self._validate_arguments_roles(msg.clean_content)
        existing_perms = command_to_edit.perms
        ids_to_add = {x.id for x in roles_to_add}
        successfully_added_roles = {x.name for x in roles_to_add if x.id not in existing_perms.role_overrides}

        if not existing_perms.check_permissions(msg.author, msg.channel):
            raise UserPermissionError

        new_perms = CommandPermissions.from_existing(existing_perms,
                                                     role_overrides=existing_perms.role_overrides | ids_to_add)

        command_to_edit.perms.update(new_perms)
        self.permission_overrides[command_to_edit.name.lower()]["role_overrides"] = list(new_perms.role_overrides)
        self.config_manager.save_config()

        await respond(msg, f"**ANALYSIS: Command {command_to_edit.name} edited successfully. Added role overrides:** "
                           f"`{', '.join(successfully_added_roles)}`")

    @Command("RemoveCommandRoleOverride", "RmCmdRole",
             doc="Removes a role override(s) from a given command.",
             syntax="(command) (roles_to_remove)",
             perms="manage_guild",
             category="command_permissions")
    async def _rm_command_role_override(self, msg: discord.Message):
        command_to_edit, roles_to_remove = self._validate_arguments_roles(msg.clean_content)
        existing_perms = command_to_edit.perms
        ids_to_remove = {x.id for x in roles_to_remove}
        successfully_removed_roles = {x.name for x in roles_to_remove if x in existing_perms.role_overrides}

        if not existing_perms.check_permissions(msg.author, msg.channel):
            raise UserPermissionError

        new_perms = CommandPermissions.from_existing(existing_perms,
                                                     role_overrides=existing_perms.role_overrides - ids_to_remove)

        if not new_perms.check_permissions(msg.author, msg.channel):
            raise UserPermissionError

        command_to_edit.perms.update(new_perms)
        self.permission_overrides[command_to_edit.name.lower()]["role_overrides"] = list(new_perms.role_overrides)
        self.config_manager.save_config()

        await respond(msg, f"**ANALYSIS: Command {command_to_edit.name} edited successfully. Removed role "
                           f"overrides:** `{', '.join(successfully_removed_roles)}`")

    @Command("AddCommandOptionalPermission", "AddCmdPermOpt",
             doc="Adds a permission to a given command's specified optional permission set. Optional permission sets "
                 "are used to give commands additional functions for users who have all of the permissions in the "
                 "set - such as bypassing limits or modifying other members. Most commands don't have these - refer "
                 "to the command of interest's documentation for more information.",
             syntax="(command) (feature_set) (permissions_to_add)",
             perms="manage_guild",
             category="command_permissions")
    async def _add_command_optional_permission(self, msg: discord.Message):
        command_to_edit, feature_set, perms_to_add = self._validate_arguments_optional_permissions(msg.clean_content)
        existing_perms = command_to_edit.perms
        successfully_added_perms = {x.upper() for x in perms_to_add
                                    if x not in existing_perms.optional_permissions[feature_set]}

        if not existing_perms.check_optional_permissions(feature_set, msg.author, msg.channel):
            raise UserPermissionError

        new_optional_perms = existing_perms.optional_permissions.copy()
        new_optional_perms[feature_set] = new_optional_perms[feature_set].copy() | perms_to_add
        new_perms = CommandPermissions.from_existing(existing_perms, optional_permissions=new_optional_perms)

        if not new_perms.check_optional_permissions(feature_set, msg.author, msg.channel):
            raise UserPermissionError

        command_to_edit.perms.update(new_perms)
        self.permission_overrides[command_to_edit.name.lower()]["optional_permissions"] = \
            {k: list(v) for k, v in new_perms.optional_permissions.items()}
        self.config_manager.save_config()

        await respond(msg, f"**ANALYSIS: Command {command_to_edit.name} edited successfully. Added permissions to "
                           f"optional feature set {feature_set}:** `{', '.join(successfully_added_perms)}`")

    @Command("RemoveCommandOptionalPermission", "RmCmdPermOpt",
             doc="Removes a permission from the given command's specified optional permission set. If all "
                 "permissions are removed from a feature set, all users have access to the optional features.",
             syntax="(command) (feature_set) (permissions_to_add)",
             perms="manage_guild",
             category="command_permissions")
    async def _rm_command_optional_permission(self, msg: discord.Message):
        command_to_edit, feature_set, perms_to_remove = \
            self._validate_arguments_optional_permissions(msg.clean_content)
        existing_perms = command_to_edit.perms
        successfully_removed_perms = {x.upper() for x in perms_to_remove if x in
                                      existing_perms.optional_permissions[feature_set]}

        if not existing_perms.check_optional_permissions(feature_set, msg.author, msg.channel):
            raise UserPermissionError

        new_optional_perms = existing_perms.optional_permissions.copy()
        new_optional_perms[feature_set] = new_optional_perms[feature_set].copy() - perms_to_remove
        new_perms = CommandPermissions.from_existing(existing_perms, optional_permissions=new_optional_perms)

        command_to_edit.perms.update(new_perms)
        self.permission_overrides[command_to_edit.name.lower()]["optional_permissions"] = \
            {k: list(v) for k, v in new_perms.optional_permissions.items()}
        self.config_manager.save_config()

        await respond(msg, f"**ANALYSIS: Command {command_to_edit.name} edited successfully. Removed permissions "
                           f"from optional feature set {feature_set}:** `{', '.join(successfully_removed_perms)}`")

    @Command("ListCommandPermissions", "ListCmdPerms",
             doc="Lists the permission configuration for a given command.",
             syntax="(command)",
             perms="manage_guild",
             category="command_permissions")
    async def _list_command_permissions(self, msg: discord.Message):
        args = shlex.split(msg.clean_content.lower())[1:]
        try:
            command_to_read = self._validate_arguments_command(args.pop(0))
        except IndexError:
            raise CommandSyntaxError

        perms = command_to_read.perms

        if perms.permissions_all:
            permissions_all_printable = ', '.join(x.upper() for x in perms.permissions_all)
        else:
            permissions_all_printable = "None"
        permissions_all_printable = f"Required permissions: `{permissions_all_printable}`\n"
        if perms.permissions_any:
            permissions_any_printable = f"Any permission of these required: " \
                                        f"`{', '.join(x.upper() for x in perms.permissions_any)}`\n"
        else:
            permissions_any_printable = ""
        if perms.user_overrides:
            users_printable = f"Users with permission override: " \
                              f"`{', '.join(self.guild.get_member(x).name for x in perms.user_overrides)}`\n"
        else:
            users_printable = ""
        if perms.role_overrides:
            roles_printable = f"Roles with permission overrides: " \
                              f"`{', '.join(self.guild.get_role(x).name for x in perms.role_overrides)}`\n"
        else:
            roles_printable = ""

        if perms.optional_permissions:
            optionals_printable = "Optional feature sets:\n"
            optionals_printable += "\n".join(f"- {k}: {', '.join(x.upper() for x in v)}"
                                             for k, v in perms.optional_permissions.items())
            optionals_printable += "\n"
        else:
            optionals_printable = ""

        response = f"```Permissions for command {command_to_read.name}:\n" \
                   f"{permissions_all_printable}{permissions_any_printable}{users_printable}{roles_printable}" \
                   f"{optionals_printable}```"

        await respond(msg, response)

    # Utility functions

    def _validate_arguments_command(self, command: str) -> Command:
        try:
            return self.commands[command]
        except KeyError:
            raise CommandSyntaxError(f"Command {command} does not exist.")

    def _validate_arguments_permissions(self, args: str) -> tuple[Command, set[str]]:
        args = shlex.split(args.lower())[1:]
        try:
            command_to_edit = self._validate_arguments_command(args.pop(0))
        except IndexError:
            raise CommandSyntaxError

        if not all(hasattr(discord.Permissions, x) for x in args):
            raise CommandSyntaxError("One or more permissions do not exist.")

        return command_to_edit, set(args)

    def _validate_arguments_optional_permissions(self, args: str) -> tuple[Command, str, set[str]]:
        args = shlex.split(args.lower())[1:]
        try:
            command_to_edit = self._validate_arguments_command(args.pop(0))
        except IndexError:
            raise CommandSyntaxError

        try:
            feature_set_to_edit = args.pop(0)
        except IndexError:
            raise CommandSyntaxError
        try:
            feature_set_to_edit = command_to_edit.perms.optional_permissions[feature_set_to_edit]
        except KeyError:
            raise CommandSyntaxError(f"Command {command_to_edit.name} has no such optional feature set "
                                     f"{feature_set_to_edit}.")

        if not all(hasattr(discord.Permissions, x) for x in args):
            raise CommandSyntaxError("One or more permissions do not exist.")

        return command_to_edit, feature_set_to_edit, set(args)

    def _validate_arguments_users(self, args: str) -> tuple[Command, set[discord.Member]]:
        args = shlex.split(args.lower())[1:]
        try:
            command_to_edit = self._validate_arguments_command(args.pop(0))
        except IndexError:
            raise CommandSyntaxError

        users = set()
        for search_str in args:
            user = find_user(self.guild, search_str)
            if user is None:
                raise CommandSyntaxError(f"User {search_str} could not be found.")
            users.add(user)

        return command_to_edit, users

    def _validate_arguments_roles(self, args: str) -> tuple[Command, set[discord.Role]]:
        args = shlex.split(args.lower())[1:]
        try:
            command_to_edit = self._validate_arguments_command(args.pop(0))
        except IndexError:
            raise CommandSyntaxError

        roles = set()
        for search_str in args:
            role = find_role(self.guild, search_str)
            if role is None:
                raise CommandSyntaxError(f"Role {search_str} could not be found.")
            roles.add(role)

        return command_to_edit, roles
