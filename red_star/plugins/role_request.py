from red_star.plugin_manager import BasePlugin
from red_star.command_dispatcher import Command
from red_star.rs_utils import respond, RSArgumentParser, split_message, find_role, group_items
from red_star.rs_errors import CommandSyntaxError, UserPermissionError
import asyncio
import discord
import shlex
import json


class MESSAGE_TYPE:
    NORMAL = 0
    CHOICE = 1


class RoleRequest(BasePlugin):
    name = "role_request"
    version = "1.4"
    author = "GTG3000"

    default_plugin_config = {
        "roles": [],
        "default_roles": []
    }

    reacts = None
    passwords = None

    async def activate(self):
        self._port_old_storage()
        self.reacts = self.storage.setdefault("role_request_reaction_messages", {})
        self.passwords = self.storage.setdefault("role_password", {})
        self._port_old_reacts()

    def _port_old_reacts(self):
        for messageId, config in self.reacts.items():
            if type(config) == list:
                self.reacts[messageId] = {
                    "reacts": config,
                    "type": MESSAGE_TYPE.NORMAL
                }
            elif "required" not in config:
                config["required"] = []

    def _port_old_storage(self):
        old_storage_path = self.config_manager.config_path / "role_request_reaction_messages.json"
        if old_storage_path.exists():
            with old_storage_path.open(encoding="utf-8") as fp:
                old_storage = json.load(fp)
            for msg_id, message_data in old_storage.items():
                # We have no way to check which guild a message belongs to, so we have no choice but to put all
                # message IDs in all guilds.
                for new_storage in self.config_manager.storage_files.values():
                    plugin_storage = new_storage[self.name]
                    plugin_storage.contents.setdefault("role_request_reaction_messages", {})[msg_id] = message_data
                    plugin_storage.save()
                    plugin_storage.load()
            old_storage_path = old_storage_path.replace(old_storage_path.with_suffix(".json.old"))
            self.logger.info(f"Old role request reaction message storage converted to new format. "
                             f"Old data now located at {old_storage_path} - you may delete this file.")

    async def on_member_join(self, member: discord.Member):
        """
        Handles the call of on_member_join to apply the default roles, if any.
        """
        roles = self.config['default_roles']
        if roles:
            roles = map(lambda rid: find_role(member.guild, str(rid)), roles)
            await member.add_roles(*roles, reason="Adding default roles.")

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
             doc="Creates a post with reactions that can be used to gain or remove offered roles.\n"
                 "Use as follows: OfferRoles 🎈 balloonrole 📌 \"pushpin role\"\n"
                 "Opional flags:\n"
                 "-x/--exclusive: only one reaction is allowed to be claimed.\n"
                 "-r/--require  : member must have all of the required roles to claim anything.\n\n"
                 "example: OfferRoles -x -r Speaking -r Special ✅ @extra_special_role",
             syntax="[-x/--exclusive] [-r/--require (role)] (reaction) (role)...",
             perms={"manage_roles"},
             category="role_request",
             run_anywhere=True)
    async def _offer_roles(self, msg: discord.Message):
        parser = RSArgumentParser()
        parser.add_argument("command")
        parser.add_argument("-x", "--exclusive", action="store_true")
        parser.add_argument("-r", "--require", action="append", default=[])
        parser.add_argument("pairs", nargs="+")

        args = parser.parse_args(shlex.split(msg.content))

        if not args["pairs"]:
            return

        print(args)

        found = list(filter(lambda x: x[1],  # throw out the entries where role wasn't found
                            ((emote, find_role(msg.guild, roleQuery))
                             for emote, roleQuery in zip(args["pairs"][::2], args["pairs"][1::2]))))

        requisite = []
        for roleQuery in args["require"]:
            role = find_role(msg.guild, roleQuery)
            if not role:
                raise CommandSyntaxError(F"Could not find required role {roleQuery}")
            requisite.append(role.id)

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
            self.reacts[str(message.id)] = {
                "type": MESSAGE_TYPE.CHOICE if args["exclusive"] else MESSAGE_TYPE.NORMAL,
                "required": requisite,
                "reacts": parsed_found
            }
            self.storage_file.save()

    @Command("PasswordRole", "PWDRole",
             doc="Specifies a role to be granted to people offering a correct password through ClaimRole command.\n"
                 "Pass phrases with spaces in them can be supplied in quotation marks, e.g. \"some pass phrase\".\n"
                 "NOTE: whitespace will be reduced to single space to prevent confusion.\n"
                 "If a given pass phrase already exists on theserver, role will be updated or deleted if no role is "
                 "supplied.\n"
                 "If no arguments are given, lists existing password-role bindings.",
             syntax="[password] [role]",
             perms={"manage_roles"},
             category="role_request")
    async def _password_role(self, msg: discord.Message):
        args = shlex.split(msg.content)
        args_len = len(args)

        if args_len == 1:  # no arguments given, return list. There can never be an empty args list, because command.
            for message in group_items(
                    [f"{key}: {msg.guild.get_role(role['role']).name}" for key, role in self.passwords.items()],
                    message="**ANALYSIS: Following pass phrase - role pairs found:**\n",
            ):
                await respond(msg, message)
            return

        role = None
        if args_len == 3:  # optional role parameter detected. Not joining it up ourselves
            role_query = args[2]
            role = find_role(msg.guild, role_query)
            if not role:
                raise CommandSyntaxError(f"Role `{role_query}` not found. Try using a mention or a role id.")

        #  clean up password white space, to have mercy on our users.
        #  if you think that filtering out reading capability with variable spacing in password is a good idea...
        #  well you are wrong.
        password = " ".join(args[1].split())

        if password not in self.passwords:  # add new password - role pair
            self.passwords[password] = {
                "role": role.id
            }
            await respond(msg, f"**AFFIRMATIVE. Added pass phrase `{password}`, granting role `{role.name}`.**")
        elif role:  # replace role
            self.passwords[password]["role"] = role.id
            await respond(msg, f"**AFFIRMATIVE. Pass phrase `{password}` now grants role `{role.name}`.**")
        else:  # delete password - role pair
            del self.passwords[password]
            await respond(msg, f"**AFFIRMATIVE. Pass phrase `{password}` has been removed.**")
        self.storage_file.save()

    @Command("ClaimRole",
             syntax="(password)",
             category="role_request",
             run_anywhere=True,
             delcall=True)
    async def _claim_role(self, msg: discord.Message):
        _, *password = msg.content.split()
        if not password:
            return

        password = " ".join(password)

        if password not in self.passwords:
            return

        role = msg.guild.get_role(self.passwords[password]['role'])
        if not role:
            return

        await msg.author.add_roles(role)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """
        :param payload:
        :return:
        """
        if payload.user_id == self.client.user.id:
            return

        message_id = str(payload.message_id)

        if message_id not in self.reacts:
            return

        offering = self.reacts[message_id]

        roles = []
        msg = await self.client.get_channel(payload.channel_id).fetch_message(payload.message_id)
        user = self.client.get_guild(payload.guild_id).get_member(payload.user_id)
        emoji = str(payload.emoji)

        if offering["required"]:
            for required_role_id in offering["required"]:
                if not user.get_role(required_role_id):
                    await msg.remove_reaction(payload.emoji, user)
                    return

        if offering["type"] == MESSAGE_TYPE.CHOICE:
            to_add = set()
            to_remove = set()
            to_remove_emoji = set()
            for reaction, roleId in offering["reacts"]:
                if reaction == emoji:
                    to_add.add(roleId)
                else:
                    to_remove.add(roleId)
                    to_remove_emoji.add(reaction)
            to_remove = to_remove - to_add
            roles = [msg.guild.get_role(role_id) for role_id in to_add]
            if to_remove:
                await asyncio.gather(*(msg.remove_reaction(emoji, user) for emoji in to_remove_emoji))
                await user.remove_roles(*(msg.guild.get_role(role_id) for role_id in to_remove),
                                        reason="Removed by request through plugin.")
        else:
            roles = [msg.guild.get_role(role_id) for reaction, role_id in offering["reacts"] if reaction == emoji]

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

        message_id = str(payload.message_id)

        if message_id not in self.reacts:
            return

        offer = self.reacts[message_id]
        msg = await self.client.get_channel(payload.channel_id).fetch_message(payload.message_id)
        user = self.client.get_guild(payload.guild_id).get_member(payload.user_id)
        emoji = str(payload.emoji)

        roles = [msg.guild.get_role(role_id) for reaction, role_id in offer["reacts"] if reaction == emoji]

        if roles:
            await user.remove_roles(*roles, reason="Removed by request through plugin.")
            return

    async def on_message_delete(self, msg: discord.Message):
        mid = str(msg.id)
        if mid in self.reacts:
            del self.reacts[mid]
            self.storage_file.save()
