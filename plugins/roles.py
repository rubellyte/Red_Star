from discord import InvalidArgument, HTTPException, Forbidden, Colour
from plugin_manager import BasePlugin
from rs_utils import Command, respond, split_message, is_positive
from string import capwords
import shlex


class RoleCommands(BasePlugin):
    name = "role_commands"

    @Command("editrole",
             perms={"manage_roles"},
             category="roles",
             syntax="(role name) [name=string][colour=FFFFFF][hoist=bool][mentionable=bool][position=integer].\n"
                    "ANALYSIS: Strings can be encapsulated in \"...\" to allow spaces",
             doc="Edits the specified role name, colour, hoist (show separately from others)"
                 " and mentionable properties.\n"
                 "WARNING: Options must be specified as option=value. No spaces around `=`.\n"
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
            self.logger.warning("Unable to split {data.content}. {e}")
            raise SyntaxError(e)
        if len(args) > 1:
            for role in msg.guild.roles:
                if args[1].lower() == role.name.lower():  # found role
                    t_dict = {}
                    for arg in args[2:]:
                        t_arg = arg.split("=")
                        if len(t_arg) > 1:  # beautiful
                            if t_arg[0].lower() == "name":
                                t_dict["name"] = t_arg[1]
                            elif t_arg[0].lower() == "colour":
                                t_dict["colour"] = Colour(int(t_arg[1], 16))
                            elif t_arg[0].lower() == "color":
                                t_dict["colour"] = Colour(int(t_arg[1], 16))
                            elif t_arg[0].lower() == "hoist":
                                t_dict["hoist"] = is_positive(t_arg[1])
                            elif t_arg[0].lower() == "mentionable":
                                t_dict["mentionable"] = is_positive(t_arg[1])
                            elif t_arg[0].lower() == "position":
                                if t_arg[1].isdecimal():
                                    pos = int(t_arg[1])
                                    if pos >= 0:
                                        t_dict["position"] = pos
                                else:
                                    raise SyntaxError("Position must be a positive integer.")
                    if len(t_dict) == 0:  # you're wasting my time
                        raise SyntaxError
                    await role.edit(**t_dict)
                    t_string = ""
                    for k, v in t_dict.items():
                        t_string = f"{t_string}{k}: {v!s}\n"
                    name = args[1].capitalize()
                    await respond(msg, f"**AFFIRMATIVE. Role {name} modified with parameters :**\n ```{t_string}```")
                    break
            else:
                await respond(msg, f"**NEGATIVE. ANALYSIS: no role {args[1].capitalize()} found.**")
        else:
            raise SyntaxError

    @Command("createrole",
             perms={"manage_roles"},
             category="roles",
             syntax="(role name) (base role) [name=string][colour=FFFFFF][hoist=bool][mentionable=bool].\n"
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
            self.logger.warning("Unable to split {data.content}. {e}")
            raise SyntaxError(e)
        if len(args) > 2:
            for role in msg.guild.roles:
                if args[2].lower() == role.name.lower():
                    # copying the existing role (especially permissions)
                    t_dict = {
                        "name": args[1],
                        "permissions": role.permissions,
                        "colour": role.colour,
                        "hoist": role.hoist,
                        "mentionable": role.mentionable
                    }
                    rolepos = role.position
                    for arg in args[3:]:
                        t_arg = arg.split("=")
                        if len(t_arg) > 1:  # beautiful
                            if t_arg[0].lower() == "name":
                                t_dict["name"] = t_arg[1]
                            elif t_arg[0].lower() == "colour":
                                t_dict["colour"] = Colour(int(t_arg[1], 16))
                            elif t_arg[0].lower() == "color":
                                t_dict["colour"] = Colour(int(t_arg[1], 16))
                            elif t_arg[0].lower() == "hoist":
                                t_dict["hoist"] = is_positive(t_arg[1])
                            elif t_arg[0].lower() == "mentionable":
                                t_dict["mentionable"] = is_positive(t_arg[1])
                            elif t_arg[0].lower() == "position":
                                if t_arg[1].isdecimal():
                                    pos = int(t_arg[1])
                                    if pos > 0:
                                        rolepos = pos
                                else:
                                    raise SyntaxError("Position must be a positive integer.")
                    t_role = await msg.guild.create_role(**t_dict)
                    try:
                        # since I can't create a role with a preset position :T
                        await t_role.edit(position=rolepos)
                    except (InvalidArgument, HTTPException):
                        # oh hey, why are we copying this role again?
                        name = args[1].capitalize()
                        await t_role.delete()
                        await respond(msg, f"**WARNING: Failed to move role {name} to position {rolepos}.**")
                        raise Forbidden  # yeah, we're not copying this
                    t_string = ""
                    for k, v in t_dict.items():
                        if k != "permissions":
                            t_string = f"{t_string}{k}: {v!s}\n"
                        else:
                            t_string += k + ": " + ", ".join({x.upper() for x, y in v if y}) + "\n"
                    name = args[1].capitalize()
                    await respond(msg, f"**AFFIRMATIVE. Created role {name} with parameters :**\n ```{t_string}```")
                    break
            else:
                await respond(msg, f"**NEGATIVE. ANALYSIS: no base role {args[2].capitalize()} found.**")
        else:
            raise SyntaxError

    @Command("deleterole",
             perms={"manage_roles"},
             category="roles",
             syntax="(role name) [position].\nANALYSIS: Strings can be encapsulated in \"...\" to allow spaces",
             doc="Deletes first encounter of the role with the given name and optionally position.")
    async def _deleterole(self, msg):
        try:
            args = shlex.split(msg.content)
        except ValueError as e:
            self.logger.warning("Unable to split {data.content}. {e}")
            raise SyntaxError(e)
        if len(args) > 1:
            name = args[1].capitalize()
            pos = -1
            if len(args) > 2:
                try:
                    pos = int(args[2])
                except ValueError:
                    raise SyntaxWarning("Position should be integer.")
            for role in msg.guild.roles:
                # delete if name matches, and if pos is not -1 - if position matches
                if (args[1].lower() == role.name.lower()) and (((pos >= 0) and (role.position == pos)) or pos < 0):
                    t_position = role.position
                    await role.delete()
                    await respond(msg, f"**AFFIRMATIVE. Deleted role: {name} in position: {str(t_position)}.**")
                    break
            else:
                await respond(msg, f"**NEGATIVE. ANALYSIS: no role {name} found.**")
        else:
            raise SyntaxError("Expected role name.")

    @Command("roleinfo", "inforole",
             category="roles",
             syntax="(role name).\nANALYSIS: Strings can be encapsulated in \"...\" to allow spaces",
             doc="Returns all the info about the given role.")
    async def _inforole(self, msg):
        """
        provides an infodump of a role, including permissions and position
        """
        try:
            args = shlex.split(msg.content)
        except ValueError as e:
            self.logger.warning("Unable to split {data.content}. {e}")
            raise SyntaxError(e)
        if len(args) > 1:
            name = capwords(args[1])
            for role in msg.guild.roles:
                if args[1].lower() == role.name.lower():
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
                    await respond(msg, f"**ANALYSIS: role {name} has parameters :**\n ```{t_string}```")
                    break
            else:
                await respond(msg, f"**NEGATIVE. ANALYSIS: no role {name} found.**")
        else:
            raise SyntaxError

    @Command("listroles", "listrole",
             category="roles",
             perms={"manage_roles"},
             doc="Lists all roles.")
    async def _listroles(self, msg):
        """
        lists all roles along with position and color
        """
        t_string = "**AFFIRMATIVE. Listing roles :**\n"
        for role in msg.guild.role_hierarchy:
            t_string += f"`{role.name[:40].ljust(40)} [{role.position:02d} | {role.colour}]`\n"
        for t in split_message(t_string, splitter="\n"):
            await respond(msg, t)
