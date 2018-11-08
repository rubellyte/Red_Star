import shlex
from string import capwords
from discord import InvalidArgument, HTTPException, Colour
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import CommandSyntaxError
from red_star.rs_utils import respond, is_positive, find_role, group_items, RSArgumentParser
from red_star.command_dispatcher import Command


class RoleCommands(BasePlugin):
    name = "role_commands"
    version = "1.1"
    author = "GTG3000"
    description = "A plugin for manipulating server roles via commands."

    @Command("EditRole",
             perms={"manage_roles"},
             category="roles",
             syntax="(role) [-n/--name string][-c/--colour FFFFFF][-h/--hoist bool][-m/--mentionable bool]"
                    "[-p/--position integer].\nANALYSIS: Strings can be encapsulated in \"...\" to allow spaces",
             doc="Edits the specified role name, colour, hoist (show separately from others) "
                 "and mentionable properties.\nOptions must be specified as \"--option value\" or \"-o value\".\n"
                 "Colour can be reset by setting it to 0.")
    async def _edit_role(self, msg):
        """
        a command for editing a role.
        !editrole (role name) [name=name][colour=colour][hoist=hoist][mentionable=mentionable]
        name is a string
        colour is a colour object (value converted from hexadecimal string)
        hoist and mentionable are boolean
        """
        try:
            args = shlex.split(msg.content)
        except ValueError as e:
            self.logger.warning(f"Unable to split {msg.content}. {e}")
            raise CommandSyntaxError(e)

        parser = RSArgumentParser()
        parser.add_argument("command")                      # Well it's gonna be there.
        parser.add_argument("role")                         # The role name/ID
        parser.add_argument("-n", "--name")                 # New role name
        parser.add_argument("-c", "--colour", "--color")    # New role colour
        parser.add_argument("-h", "--hoist")                # To separate the role or not
        parser.add_argument("-m", "--mentionable")          # To allow role being mentioned
        parser.add_argument("-p", "--position", type=int)   # Changing position (DON'T ACTUALLY USE IT)
        if len(args) > 1:
            args = parser.parse_args(args)

            role = find_role(msg.guild, args['role'])
            if role:
                try:
                    arg_dict = {
                        "name": args['name'] if args['name'] else None,
                        "colour": Colour(int(args['colour'], 16)) if args['colour'] else None,
                        "hoist": is_positive(args['hoist']) if args['hoist'] else None,
                        "mentionable": is_positive(args['mentionable']) if args['mentionable'] else None,
                        "position": max(0, args['position']) if args['position'] else None
                    }
                    arg_dict = {k: v for k, v in arg_dict.items() if v is not None}
                except ValueError:
                    raise CommandSyntaxError("Colour must be in web-colour hexadecimal format.")
                await role.edit(**arg_dict)
                result_string = "\n".join([f"{k}: {v}" for k, v in arg_dict.items()])
                await respond(msg, f"**AFFIRMATIVE. Role {role.name} modified with parameters :**\n"
                                   f"```{result_string}```")
            else:
                raise CommandSyntaxError(f"No role \"{args['role']}\" found.")
        else:
            raise CommandSyntaxError

    @Command("CreateRole",
             perms={"manage_roles"},
             category="roles",
             syntax="(role name) (base role) [-n/--name string][-c/--colour FFFFFF][-h/--hoist bool]"
                    "[-m/--mentionable bool][-p/--position integer].\n"
                    "ANALYSIS: Strings can be encapsulated in \"...\" to allow spaces",
             doc="Creates a role based on an existing role (for position and permissions), "
             "with parameters similar to editrole")
    async def _createrole(self, msg):
        """
        a command for creating a role
        takes names for new role and a role that will be copied for position/permissions
        """
        try:
            args = shlex.split(msg.content)
        except ValueError as e:
            self.logger.warning(f"Unable to split {msg.content}. {e}")
            raise CommandSyntaxError(e)

        parser = RSArgumentParser()
        parser.add_argument("command")                      # Well it's gonna be there.
        parser.add_argument("role")                         # Name of the new role
        parser.add_argument("template")                     # Permission donor name/ID
        parser.add_argument("-n", "--name")                 # New role name
        parser.add_argument("-c", "--colour", "--color")    # New role colour
        parser.add_argument("-h", "--hoist")                # To separate the role or not
        parser.add_argument("-m", "--mentionable")          # To allow role being mentioned
        parser.add_argument("-p", "--position", type=int)   # Changing position (DON'T ACTUALLY USE IT)

        if len(args) > 2:
            parsed_args = parser.parse_args(args)
            role = find_role(msg.guild, parsed_args['template'])
            if role:
                try:
                    arg_dict = {
                        "name": parsed_args['name'] if parsed_args['name'] else args[1],
                        "permissions": role.permissions,
                        "colour": Colour(int(parsed_args['colour'], 16)) if parsed_args['colour'] else role.colour,
                        "hoist": is_positive(parsed_args['hoist']) if parsed_args['hoist'] else role.hoist,
                        "mentionable": is_positive(parsed_args['mentionable'])
                        if parsed_args['mentionable'] else role.mentionable
                    }
                except ValueError:
                    raise CommandSyntaxError("Colour must be in web-colour hexadecimal format.")

                rolepos = max(0, parsed_args['position']) if parsed_args['position'] else role.position

                t_role = await msg.guild.create_role(**arg_dict)

                try:
                    # since I can't create a role with a preset position :T
                    await t_role.edit(position=rolepos)
                except (InvalidArgument, HTTPException):
                    # oh hey, why are we copying this role again?
                    name = args[1].capitalize()
                    await t_role.delete()
                    raise CommandSyntaxError(f"Failed to move role {name} to position {rolepos}.")
                t_string = ""
                for k, v in arg_dict.items():
                    if k != "permissions":
                        t_string = f"{t_string}{k}: {v!s}\n"
                    else:
                        t_string += k + ": " + ", ".join({x.upper() for x, y in v if y}) + "\n"
                name = args[1].capitalize()
                await respond(msg, f"**AFFIRMATIVE. Created role {name} with parameters :**\n ```{t_string}```")
            else:
                await respond(msg, f"**NEGATIVE. ANALYSIS: no base role {args[2].capitalize()} found.**")
        else:
            raise CommandSyntaxError

    @Command("DeleteRole",
             perms={"manage_roles"},
             category="roles",
             syntax="(role) [position].\nANALYSIS: Strings can be encapsulated in \"...\" to allow spaces",
             doc="Deletes first encounter of the role with the given name and optionally position.")
    async def _deleterole(self, msg):
        try:
            args = shlex.split(msg.content)
        except ValueError as e:
            self.logger.warning(f"Unable to split {msg.content}. {e}")
            raise CommandSyntaxError(e)
        if len(args) > 1:
            name = args[1].capitalize()
            pos = -1
            if len(args) > 2:
                try:
                    pos = int(args[2])
                except ValueError:
                    raise SyntaxWarning("Position should be integer.")
            role = find_role(msg.guild, args[1])
            if role and (((pos >= 0) and (role.position == pos)) or pos < 0):
                # delete if name matches, and if pos is not -1 - if position matches
                t_position = role.position
                await role.delete()
                await respond(msg, f"**AFFIRMATIVE. Deleted role: {name} in position: {str(t_position)}.**")
            else:
                await respond(msg, f"**NEGATIVE. ANALYSIS: no role {name} found.**")
        else:
            raise CommandSyntaxError("Expected role name.")

    @Command("RoleInfo", "InfoRole",
             category="roles",
             syntax="(role).\nANALYSIS: Strings can be encapsulated in \"...\" to allow spaces",
             doc="Returns all the info about the given role.")
    async def _inforole(self, msg):
        """
        provides an infodump of a role, including permissions and position
        """
        try:
            args = shlex.split(msg.content)
        except ValueError as e:
            self.logger.warning("Unable to split {data.content}. {e}")
            raise CommandSyntaxError(e)
        if len(args) > 1:
            name = capwords(args[1])
            role = find_role(msg.guild, args[1])
            if role:
                info_dict = {
                    "name": role.name,
                    "permissions": role.permissions,
                    "colour": role.colour,
                    "hoist": role.hoist,
                    "mentionable": role.mentionable,
                    "position": role.position,
                    "created_at": role.created_at,
                    "id": role.id
                }
                result_string = ""
                for k, v in info_dict.items():
                    if k != "permissions":
                        result_string = f"{result_string}{k}: {v!s}\n"
                    else:
                        result_string += k + ": " + ", ".join({x.upper() for x, y in v if y}) + "\n"
                await respond(msg, f"**ANALYSIS: role {role.name} has parameters :**\n ```{result_string}```")
            else:
                await respond(msg, f"**NEGATIVE. ANALYSIS: no role {name} found.**")
        else:
            raise CommandSyntaxError

    @Command("ListRoles", "ListRole",
             category="roles",
             perms={"manage_roles"},
             doc="Lists all roles.")
    async def _listroles(self, msg):
        """
        lists all roles along with position and color
        """
        role_list = (f"[{role.position:03d} | {role.colour} | {role.name[:40].ljust(40,'·')}]"
                     for role in msg.guild.roles[::-1])
        for split_msg in group_items(role_list, message="**AFFIRMATIVE. Listing roles :**"):
            await respond(msg, split_msg)
