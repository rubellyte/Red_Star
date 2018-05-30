from discord import InvalidArgument, HTTPException, Forbidden, Colour
from plugin_manager import BasePlugin
from rs_errors import CommandSyntaxError
from rs_utils import respond, is_positive, find_role, split_output, RSArgumentParser
from command_dispatcher import Command
from string import capwords
import shlex
from argparse import SUPPRESS


class RoleCommands(BasePlugin):
    name = "role_commands"

    @Command("EditRole",
             perms={"manage_roles"},
             category="roles",
             syntax="(role) [-n/--name string][-c/--colour FFFFFF][-h/--hoist bool][-m/--mentionable bool][-p/"
                    "--position integer].\n"
                    "ANALYSIS: Strings can be encapsulated in \"...\" to allow spaces",
             doc="Edits the specified role name, colour, hoist (show separately from others)"
                 " and mentionable properties.\n"
                 "WARNING: Options must be specified as \"--option value\" or \"-o value\".\n"
                 "ANALYSIS: Colour can be reset by setting it to 0.")
    async def _editrole(self, msg):
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

        parser = RSArgumentParser(argument_default=SUPPRESS)
        parser.add_argument("command")                      # Well it's gonna be there.
        parser.add_argument("role")                         # The role name/ID
        parser.add_argument("-n", "--name")                 # New role name
        parser.add_argument("-c", "--colour", "--color")    # New role colour
        parser.add_argument("-h", "--hoist")                # To separate the role or not
        parser.add_argument("-m", "--mentionable")          # To allow role being mentioned
        parser.add_argument("-p", "--position", type=int)   # Changing position (DON'T ACTUALLY USE IT)
        if len(args) > 1:
            p_args = parser.parse_args(args)

            role = find_role(msg.guild, p_args['role'])
            if role:
                # strip out irrelevant fields
                t_dict = {k: v for k, v in p_args.items() if v and k not in ["command", "role"]}
                # colour has to be a Colour()
                if "colour" in t_dict:
                    try:
                        t_dict["colour"] = Colour(int(t_dict["colour"], 16))
                    except ValueError:
                        raise CommandSyntaxError("Colour must be in web-colour hexadecimal format.")
                # position can't be below 0. Or over max number of roles but shhh
                if "position" in t_dict:
                    t_dict["position"] = max(0, t_dict["position"])
                if "mentionable" in t_dict:
                    t_dict["mentionable"] = is_positive(t_dict["mentionable"])
                if "hoist" in t_dict:
                    t_dict["hoist"] = is_positive(t_dict["hoist"])
                if len(t_dict) == 0:
                    raise CommandSyntaxError
                t_string = "\n".join([f"{k}: {v!s}" for k, v in t_dict.items()])
                await respond(msg, f"**AFFIRMATIVE. Role {p_args['role'].capitalize()} modified with parameters :**\n "
                                   f"```{t_string}```")
            else:
                raise CommandSyntaxError(f"No role \"{p_args['role']}\" found.")
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
            p_args = parser.parse_args(args)
            role = find_role(msg.guild, p_args['template'])
            if role:
                try:
                    t_dict = {
                        "name": p_args['name'] if p_args['name'] else args[1],
                        "permissions": role.permissions,
                        "colour": Colour(int(p_args['colour'], 16)) if p_args['colour'] else role.colour,
                        "hoist": is_positive(p_args['hoist']) if p_args['hoist'] else role.hoist,
                        "mentionable": is_positive(p_args['mentionable']) if p_args['mentionable'] else role.mentionable
                    }
                except ValueError:
                    raise CommandSyntaxError("Colour must be in web-colour hexadecimal format.")

                rolepos = max(0, p_args['position']) if p_args['position'] else role.position

                t_role = await msg.guild.create_role(**t_dict)

                try:
                    # since I can't create a role with a preset position :T
                    await t_role.edit(position=rolepos)
                except (InvalidArgument, HTTPException):
                    # oh hey, why are we copying this role again?
                    name = args[1].capitalize()
                    await t_role.delete()
                    raise CommandSyntaxError(f"Failed to move role {name} to position {rolepos}.")
                t_string = ""
                for k, v in t_dict.items():
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
                t_dict = {
                    "name": role.name,
                    "permissions": role.permissions,
                    "colour": role.colour,
                    "hoist": role.hoist,
                    "mentionable": role.mentionable,
                    "position": role.position,
                    "created_at": role.created_at,
                    "id": role.id
                }
                t_string = ""
                for k, v in t_dict.items():
                    if k != "permissions":
                        t_string = f"{t_string}{k}: {v!s}\n"
                    else:
                        t_string += k + ": " + ", ".join({x.upper() for x, y in v if y}) + "\n"
                await respond(msg, f"**ANALYSIS: role {role.name} has parameters :**\n ```{t_string}```")
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
        t_list = [f"[{r.position:03d} | {r.colour} | {r.name[:40].ljust(40,'·')}]" for r in msg.guild.role_hierarchy]
        await split_output(msg, "**AFFIRMATIVE. Listing roles :**", t_list)
