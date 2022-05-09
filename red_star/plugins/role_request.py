from red_star.plugin_manager import BasePlugin
from red_star.command_dispatcher import Command
from red_star.rs_utils import respond, RSArgumentParser, split_message, find_role
from red_star.rs_errors import CommandSyntaxError, UserPermissionError
import discord
import shlex


class RoleRequest(BasePlugin):
    name = "role_request"
    version = "1.1"
    author = "GTG3000"

    default_config = {
        "roles": [],
        "default_roles": []
    }

    async def activate(self):
        self.reacts = self.config_manager.get_plugin_config_file("role_request_reaction_messages.json")

    async def on_member_join(self, member: discord.Member):
        """
        Handles the call of on_member_join to apply the default roles, if any.
        """
        roles = self.config['default_roles']
        if roles:
            roles = map(lambda rid: find_role(member.guild, str(rid)), roles)
            await member.add_roles(*roles, reason="Adding default roles.")

    @Command("ManageRequestableRoles", "MReqRoles",
             doc="-a/--add   : Adds specified roles to the list of allowed requestable roles.\n"
                 "-r/--remove: Removes speficied roles from the list.\n"
                 "Calling it without any arguments prints the list.",
             syntax="[-a/--add (role mentions/ids/names)] [-r/--remove (role mentions/ids/names)]",
             perms={"manage_roles"},
             category="role_request")
    async def _manage(self, msg: discord.Message):
        parser = RSArgumentParser()
        parser.add_argument("command")
        parser.add_argument("-a", "--add", default=[], nargs='+')
        parser.add_argument("-r", "--remove", default=[], nargs='+')

        args = parser.parse_args(shlex.split(msg.content))

        if not (args['add'] or args['remove']):
            role_str = "\n".join(x.name for x in msg.guild.roles if x.id in self.config["roles"])
            for split_msg in split_message(f"**ANALYSIS: Currently approved requestable roles:**```\n{role_str}```"):
                await respond(msg, split_msg)
        else:
            args['add'] = [r for r in [find_role(msg.guild, r) for r in args['add']] if r]
            args['remove'] = [r for r in [find_role(msg.guild, r) for r in args['remove']] if r]

            # for nice output
            added_roles = []
            removed_roles = []

            for role in args['add']:
                if role.id not in self.config["roles"]:
                    added_roles.append(role.name)
                    self.config["roles"].append(role.id)
            for role in args['remove']:
                if role.id in self.config["roles"]:
                    removed_roles.append(role.name)
                    self.config["roles"].remove(role.id)

            if added_roles or removed_roles:
                output_str = "**AFFIRMATIVE. ANALYSIS:**\n```diff\n"
                if added_roles:
                    output_str += "Added roles:\n+ " + "\n+ ".join(added_roles) + "\n"
                if removed_roles:
                    output_str += "Removed roles:\n- " + "\n- ".join(removed_roles) + "\n"
                output_str += "```"
                await respond(msg, output_str)
            else:
                raise CommandSyntaxError

    @Command("RequestRole",
             doc="Adds or removes the specified requestable role from the user.\n"
                 "Role can be specified by name or ID. Please don't mention roles.",
             syntax="(role)",
             category="role_request")
    async def _requestrole(self, msg: discord.Message):
        try:
            query = msg.content.split(None, 1)[1]
        except IndexError:
            raise CommandSyntaxError("Role query required.")

        roles = find_role(msg.guild, query, return_all=True)
        if not roles:
            raise CommandSyntaxError(f"Unable to find role {query}.")
        roles = [x for x in roles if x.id in self.config['roles']]
        if not roles:
            raise UserPermissionError(f"Role {query} is not requestable.")
        role = roles[0]

        if role in msg.author.roles:
            rem = True
            await msg.author.remove_roles(role, reason="Removed by request through plugin.")
        else:
            rem = False
            await msg.author.add_roles(role, reason="Added by request through plugin.")
        await respond(msg, f"**AFFIRMATIVE. Role {role.name} {'removed' if rem else 'added'}.**")

    @Command("DefaultRole",
             doc="-a/--add   : Adds specified roles to the list of default roles.\n"
                 "-r/--remove: Removes speficied roles from the list.\n"
                 "Calling it without any arguments prints the list.",
             syntax="[-a/--add (role mentions/ids/names)] [-r/--remove (role mentions/ids/names)]",
             perms={"manage_roles"},
             category="role_request")
    async def _manage_default(self, msg: discord.Message):
        parser = RSArgumentParser()
        parser.add_argument("command")
        parser.add_argument("-a", "--add", default=[], nargs='+')
        parser.add_argument("-r", "--remove", default=[], nargs='+')

        args = parser.parse_args(shlex.split(msg.content))

        d_r_list = self.config["default_roles"]

        if not (args['add'] or args['remove']):
            role_str = "\n".join(x.name for x in msg.guild.roles if x.id in d_r_list)
            for split_msg in split_message(f"**ANALYSIS: Currently approved default roles:```\n{role_str}```"):
                await respond(msg, split_msg)
        else:
            args['add'] = [r for r in [find_role(msg.guild, r) for r in args['add']] if r]
            args['remove'] = [r for r in [find_role(msg.guild, r) for r in args['remove']] if r]

            # for nice output
            added_roles = []
            removed_roles = []

            for role in args['add']:
                if role.id not in d_r_list:
                    added_roles.append(role.name)
                    d_r_list.append(role.id)
            for role in args['remove']:
                if role.id in d_r_list:
                    removed_roles.append(role.name)
                    d_r_list.remove(role.id)

            if added_roles or removed_roles:
                output_str = "**AFFIRMATIVE. ANALYSIS:**\n```diff\n"
                if added_roles:
                    output_str += "Added roles:\n+ " + "\n+ ".join(added_roles) + "\n"
                if removed_roles:
                    output_str += "Removed roles:\n- " + "\n- ".join(removed_roles) + "\n"
                output_str += "```"
                await respond(msg, output_str)
            else:
                raise CommandSyntaxError

    @Command("OfferRoles",
             syntax="(reaction) (role)...",
             perms={"manage_roles"},
             category="role_request",
             run_anywhere=True)
    async def _offer_roles(self, msg: discord.Message):
        args = msg.content.split()[1::]
        found = []
        for emote, roleQuery in zip(args[::2], args[1::2]):
            role = find_role(msg.guild, roleQuery)
            if role:
                found.append((emote, role))

        if found:
            message = await respond(msg, "**Following roles available through reacting to this message:**\n" +
                                    "\n".join(f"> {react}: {r.mention}" for react, r in found))
            parsed_found = tuple((e, r.id) for e, r in found)
            for r, _ in found:
                try:
                    await message.add_reaction(r)
                except discord.HTTPException:
                    await message.delete()
                    raise CommandSyntaxError('Do not use emoji unavailable to the bot.')
            self.reacts[str(message.id)] = parsed_found
            self.reacts.save()

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """
        :param payload:
        :return:
        """
        if payload.user_id == self.client.user.id:
            return
        mid = str(payload.message_id)
        if mid in self.reacts:
            roles = []
            msg = await self.client.get_channel(payload.channel_id).fetch_message(payload.message_id)
            user = self.client.get_guild(payload.guild_id).get_member(payload.user_id)

            for react, roleId in self.reacts[mid]:
                if react == str(payload.emoji):
                    role = msg.guild.get_role(roleId)
                    if role not in user.roles:
                        roles.append(role)
            if roles:
                await user.add_roles(*roles, reason="Added by request through plugin.")
                return
            await msg.remove_reaction(payload.emoji, user)

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """
        :param payload:
        :return:
        """
        if payload.user_id == self.client.user.id:
            return
        mid = str(payload.message_id)
        if mid in self.reacts:
            roles = []
            msg = await self.client.get_channel(payload.channel_id).fetch_message(payload.message_id)
            user = self.client.get_guild(payload.guild_id).get_member(payload.user_id)

            for react, roleId in self.reacts[mid]:
                if react == str(payload.emoji):
                    role = msg.guild.get_role(roleId)
                    if role in user.roles:
                        roles.append(role)
            if roles:
                await user.remove_roles(*roles, reason="Removed by request through plugin.")
                return

    async def on_message_delete(self, msg: discord.Message):
        mid = str(msg.id)
        if mid in self.reacts:
            del self.reacts[mid]
            self.reacts.save()
