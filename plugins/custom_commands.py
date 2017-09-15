import re
import random
import json
import datetime
from asyncio import ensure_future, sleep
from plugin_manager import BasePlugin
import discord.utils
from io import BytesIO

from rs_errors import CommandSyntaxError, UserPermissionError, CustomCommandSyntaxError
from rs_utils import respond, Command, DotDict, find_user, is_positive
from discord import Embed, File
from discord.errors import Forbidden


class CustomCommands(BasePlugin):
    name = "custom_commands"
    default_config = {
        "cc_file": "config/ccs.json",
        "default": {
            "cc_prefix": "!!",
            "cc_limit": 25
        }
    }

    async def activate(self):
        self.tags = {
            "args": self._args,
            "username": self._username,
            "usernick": self._usernick,
            "usermention": self._usermention,
            "authorname": self._authorname,
            "authornick": self._authornick,
            "if": self._if,
            "not": self._not,
            "getvar": self._getvar,
            "setvar": self._setvar,
            "equals": self._equals,
            "match": self._match,
            "choice": self._choice,
            "contains": self._contains,
            "isempty": self._isempty,
            "hasrole": self._hasrole,
            "upper": self._upper,
            "lower": self._lower,
            "random": self._random,
            "randint": self._randint,
            "rot13": self._rot13,
            "delcall": self._delcall,
            "embed": self._embed,
            "noembed": self._noembed,
            "transcode": self._transcode
        }
        self.ccvars = {}
        try:
            with open(self.plugin_config.cc_file, "r", encoding="utf8") as f:
                self.ccs = json.load(f)
        except FileNotFoundError:
            self.ccs = {}
            with open(self.plugin_config.cc_file, "w", encoding="utf8") as f:
                f.write("{}")
        except json.decoder.JSONDecodeError:
            self.logger.exception("Could not decode ccs.json! ", exc_info=True)

    # Event hooks

    async def on_message(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        deco = self.plugin_config[gid].cc_prefix
        if msg.author != self.client.user:
            cnt = msg.content
            if cnt.startswith(deco):
                if msg.author.id in self.storage[gid]["cc_use_ban"]:
                    try:
                        await msg.author.send(f"**WARNING: You are banned from usage of custom commands on the server "
                                              f"{str(msg.guild)}**")
                    except Forbidden:
                        pass
                    return
                elif self.plugins.channel_manager.channel_in_category(msg.guild, "no_cc", msg.channel):
                    await self.plugin_manager.hook_event("on_log_event", msg.guild,
                                                         f"**WARNING: Attempted CC use in restricted channel"
                                                         f" {msg.channel.mention} by: {msg.author.display_name}**",
                                                         log_type="cc_event")
                    return
                cmd = cnt[len(deco):].split()[0].lower()
                if gid not in self.ccs:
                    self.ccs[gid] = {}
                if cmd in self.ccs[gid]:
                    if "restricted" not in self.ccs[gid][cmd]:
                        self.ccs[gid][cmd]["restricted"] = []
                    if self.ccs[gid][cmd]["restricted"]:
                        for t_cat in self.ccs[gid][cmd]["restricted"]:
                            if self.plugins.channel_manager.channel_in_category(msg.guild, t_cat, msg.channel):
                                break
                        else:
                            await self.plugin_manager.hook_event("on_log_event", msg.guild,
                                                                 f"**WARNING: Attempted CC use "
                                                                 f"outside of it's categories in"
                                                                 f" {msg.channel.mention} by: "
                                                                 f"{msg.author.display_name}**",
                                                                 log_type="cc_event")
                            return
                    await self.run_cc(cmd, msg)

    # Commands

    @Command("createcc", "newcc",
             doc="Creates a custom command.\n"
                 "Tag Documentation: https://github.com/medeor413/Red_Star/wiki/Custom-Commands",
             syntax="(name) (content)",
             category="custom_commands")
    async def _createcc(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        if msg.author.id in self.storage[gid]["cc_create_ban"]:
            raise UserPermissionError("You are banned from creating custom commands.")
        try:
            args = msg.clean_content.split(" ")[1:]
            name = args[0].lower()
        except IndexError:
            raise CommandSyntaxError("No name provided.")
        try:
            content = " ".join(args[1:])
        except IndexError:
            raise CommandSyntaxError("No content provided.")
        if gid not in self.ccs:
            self.ccs[gid] = {}
        if name in self.ccs[gid]:
            await respond(msg, f"**WARNING: Custom command {args[0]} already exists.**")
        else:
            t_count = len([True for i in self.ccs[gid].values() if i["author"] == msg.author.id])

            if msg.author.id not in self.config_manager.config.get("bot_maintainers", []) and\
                    not msg.author.permissions_in(msg.channel).manage_messages and\
                    t_count >= self.plugin_config[gid]["cc_limit"]:
                raise UserPermissionError(f"Exceeded cc limit of {self.plugin_config[gid]['cc_limit']}")
            newcc = {
                "name": name,
                "content": content,
                "author": msg.author.id,
                "date_created": datetime.datetime.now().strftime("%Y-%m-%d @ %H:%M:%S"),
                "last_edited": None,
                "locked": False,
                "restricted": [],
                "times_run": 0
            }
            self.ccs[gid][args[0].lower()] = newcc
            self._save_ccs()
            await respond(msg, f"**ANALYSIS: Custom command {name} created successfully.**")

    @Command("dumpcc",
             doc="Uploads the contents of the specified custom command as a text file.",
             syntax="(name)",
             category="custom_commands")
    async def _dumpcc(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        if msg.author.id in self.storage[gid]["cc_create_ban"]:
            raise UserPermissionError("You are banned from editing custom commands.")
        gid = str(msg.guild.id)
        self._initialize(gid)
        args = msg.content.split(" ", 1)
        if len(args) < 2:
            raise CommandSyntaxError("No name provided.")
        name = args[1].lower()
        if name in self.ccs[gid]:
            t_cc = {
                "name": name,
                "content": self.ccs[gid][name]["content"]
            }
            t_cc = json.dumps(t_cc, indent=2, ensure_ascii=False)
            async with msg.channel.typing():
                await respond(msg, "**AFFIRMATIVE. Completed file upload.**",
                              file=File(BytesIO(bytes(t_cc, encoding="utf-8")), filename=name+".json"))
        else:
            raise CommandSyntaxError("No such custom command.")

    @Command("editcc",
             doc="Edits a custom command you created.",
             syntax="(name) (content)",
             category="custom_commands")
    async def _editcc(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        if msg.author.id in self.storage[gid]["cc_create_ban"]:
            raise UserPermissionError("You are banned from editing custom commands.")
        try:
            args = msg.clean_content.split(" ")[1:]
            name = args[0].lower()
        except IndexError:
            raise CommandSyntaxError("No name provided.")
        try:
            content = " ".join(args[1:])
        except IndexError:
            raise CommandSyntaxError("No content provided.")
        if gid not in self.ccs:
            self.ccs[gid] = {}
        if name in self.ccs[gid]:
            ccdata = self.ccs[gid][name]
            if ccdata["author"] == msg.author.id or msg.author.guild_permissions.manage_messages:
                ccdata["content"] = content
                ccdata["last_edited"] = datetime.datetime.now().strftime("%Y-%m-%d @ %H:%M:%S")
                self.ccs[gid][name] = ccdata
                self._save_ccs()
                await respond(msg, f"**ANALYSIS: Custom command {name} edited successfully.**")
            else:
                await respond(msg, f"**WARNING: No permission to edit custom command {name}.**")
        else:
            await respond(msg, f"**WARNING: No such custom command {name}**")

    @Command("delcc",
             doc="Deletes a custom command.",
             syntax="(name)",
             category="custom_commands")
    async def _delcc(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        if msg.author.id in self.storage[gid]["cc_create_ban"]:
            raise UserPermissionError("You are banned from deleting custom commands.")
        try:
            name = msg.clean_content.split()[1].lower()
        except IndexError:
            raise CommandSyntaxError("No name provided.")
        if gid not in self.ccs:
            self.ccs[gid] = {}
        if name in self.ccs[gid]:
            if self.ccs[gid][name]["author"] == msg.author.id or \
                    msg.author.guild_permissions.manage_messages:
                del self.ccs[gid][name]
                self._save_ccs()
                await respond(msg, f"**ANALYSIS: Custom command {name} deleted successfully.**")
            else:
                await respond(msg, f"**WARNING: No permission to delete custom command {name}.**")
        else:
            await respond(msg, f"**WARNING: No such custom command {name}.**")

    @Command("ccinfo",
             doc="Displays information about a custom command.",
             syntax="(name)",
             category="custom_commands")
    async def _ccinfo(self, msg):
        try:
            name = msg.clean_content.split()[1].lower()
        except IndexError:
            raise CommandSyntaxError("No name provided.")
        gid = str(msg.guild.id)
        if gid not in self.ccs:
            self.ccs[gid] = {}
        if name in self.ccs[gid]:
            ccdata = self.ccs[gid][name]
            last_edited = f"Last Edited: {ccdata['last_edited']}\n" if ccdata["last_edited"] else ""
            cc_locked = "Yes" if ccdata["locked"] else "No"
            author = discord.utils.get(msg.guild.members, id=ccdata["author"])
            if author:
                author = str(author)
            else:
                author = "<Unknown user>"
            datastr = f"**ANALYSIS: Information for custom command {name}:**```\nName: {name}\nAuthor: {author}\n" \
                      f"Date Created: {ccdata['date_created']}\n{last_edited}Locked: {cc_locked}\n" \
                      f"Times Run: {ccdata['times_run']}```"
            await respond(msg, datastr)
        else:
            await respond(msg, f"**WARNING: No such custom command {name}.**")

    @Command("searchccs",
             doc="Searches CCs by name or author.",
             syntax="(name or author)",
             category="custom_commands")
    async def _searchccs(self, msg):
        search = " ".join(msg.content.split(" ")[1:]).lower()
        user = find_user(msg.guild, search)
        by_author = False
        get_all = False
        if search == "*":
            get_all = True
        elif user:
            by_author = True
            user = user.id
        if not search:
            raise CommandSyntaxError("No search provided.")
        res = []
        gid = str(msg.guild.id)
        if gid not in self.ccs:
            self.ccs[gid] = {}
        for cc, info in self.ccs[gid].items():
            if get_all:
                res.append(cc)
            elif not by_author and search in cc.lower():
                res.append(cc)
            elif info["author"] == user:
                res.append(cc)
        if res:
            t_str = f"**ANALYSIS: The following custom commands match your search:** `{res[1]}"
            for r in res[1:]:
                if len(t_str)+len(r) > 1999:
                    await respond(msg, f"{t_str}`")
                    t_str = f"`{r}"
                else:
                    t_str += f", {r}"
            await respond(msg, t_str+"`")
        else:
            await respond(msg, "**WARNING: No results found for your search.**")

    @Command("lockcc",
             doc="Toggles lock on a custom command, preventing it from being used.",
             syntax="(name)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _lockcc(self, msg):
        try:
            name = msg.clean_content.split()[1].lower()
        except IndexError:
            raise CommandSyntaxError("No name provided.")
        gid = str(msg.guild.id)
        if gid not in self.ccs:
            self.ccs[gid] = {}
        if name in self.ccs[gid]:
            self.ccs[gid][name]["locked"] = not self.ccs[gid][name]["locked"]
            lock_status = "locked" if self.ccs[gid][name]["locked"] else "unlocked"
            await respond(msg, f"**ANALYSIS: Custom command {name} has been {lock_status}.**")
        else:
            await respond(msg, f"**WARNING: No such custom command {name}.**")

    @Command("restrictcc",
             doc="Restricts specified custom command to a specified category of channels, or removes said "
                 "restriction.",
             syntax="(name) (category)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _restrictcc(self, msg):
        gid = str(msg.guild.id)
        if gid not in self.ccs:
            self.ccs[gid] = {}
        args = msg.content.split(" ", 2)
        if len(args) < 3:
            raise CommandSyntaxError("Two arguments required.")
        t_name = args[1].lower()
        t_cat = args[2].lower()
        if t_name in self.ccs[gid]:
            if "restricted" in self.ccs[gid][t_name]:
                if t_cat not in self.ccs[gid][t_name]["restricted"]:
                    self.ccs[gid][t_name]["restricted"].append(t_cat)
                    await respond(msg, f"**AFFIRMATIVE. Custom command {t_name} restricted to category {t_cat}.**")
                else:
                    self.ccs[gid][t_name]["restricted"].remove(t_cat)
                    await respond(msg, f"**AFFIRMATIVE. Custom command {t_name} no longer restricted to category "
                                       f"{t_cat}.**")
            else:
                self.ccs[gid][t_name]["restricted"] = [t_cat]
                await respond(msg, f"**AFFIRMATIVE. Custom command {t_name} restricted to category {t_cat}.**")
        else:
            raise CommandSyntaxError(f"No custom command by name of {t_name}.")

    @Command("ccmute", "mutecc",
             doc="Toggles users ability to use custom commands.",
             syntax="(user)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _mutecc(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)

        args = msg.content.split(" ", 1)

        t_member = find_user(msg.guild, args[1])

        if not t_member:
            raise CommandSyntaxError("Not a user, or user not found.")

        if t_member.id in self.storage[gid]["cc_use_ban"]:
            self.storage[gid]["cc_use_ban"].remove(t_member.id)
            await respond(msg, f"**AFFIRMATIVE. User {t_member.mention} was allowed the usage of custom commands.**")
        else:
            self.storage[gid]["cc_use_ban"].append(t_member.id)
            await respond(msg, f"**AFFIRMATIVE. User {t_member.mention} was banned from using custom commands.**")

    @Command("ccban", "bancc",
             doc="Toggles users ability to create and alter custom commands.",
             syntax="(user)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _bancc(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)

        args = msg.content.split(" ", 1)

        t_member = find_user(msg.guild, args[1])

        if not t_member:
            raise CommandSyntaxError("Not a user, or user not found.")

        if t_member.id in self.storage[gid]["cc_create_ban"]:
            self.storage[gid]["cc_create_ban"].remove(t_member.id)
            await respond(msg, f"**AFFIRMATIVE. User {t_member.mention} was allowed creation of custom commands.**")
        else:
            self.storage[gid]["cc_create_ban"].append(t_member.id)
            await respond(msg, f"**AFFIRMATIVE. User {t_member.mention} was banned from creating custom commands.**")

    @Command("listccban",
             doc="Lists users banned from using or creating CCs",
             syntax="(user)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _listccban(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)

        t_dict = {}

        for t_id in self.storage[gid]["cc_create_ban"]:
            if t_id in self.storage[gid]["cc_use_ban"]:
                t_dict[t_id] = (True, True)
            else:
                t_dict[t_id] = (True, False)
        for t_id in self.storage[gid]["cc_use_ban"]:
            if t_id not in t_dict:
                t_dict[t_id] = (False, True)
        t_string = f"**ANALYSIS: Currently banned members:**\n```{'Username'.ljust(32)} |  Ban  |  Mute\n"
        for k, v in t_dict.items():
            t_s = f"{msg.guild.get_member(k).display_name.ljust(32)} | {str(v[0]).ljust(5)} | {str(v[1]).ljust(5)}\n"
            if len(t_string+t_s) < 1997:
                t_string += t_s
            else:
                await respond(msg, t_string+"```")
                t_string = "```"+t_s
        await respond(msg, t_string+"```")

    # Custom command machinery

    async def run_cc(self, cmd, msg):
        gid = str(msg.guild.id)
        if self.ccs[gid][cmd]["locked"] and not msg.author.guild_permissions.manage_messages:
            await respond(msg, f"**WARNING: Custom command {cmd} is locked.**")
        else:
            ccdat = self.ccs[gid][cmd]["content"]
            try:
                res = self._find_tags(ccdat, msg)
            except CustomCommandSyntaxError as e:
                err = e if e else "Syntax error."
                await respond(msg, f"**WARNING: Author made syntax error: {err}**")
            except CommandSyntaxError as e:
                err = e if e else "Syntax error."
                await respond(msg, f"**WARNING: {err}**")
            except Exception:
                self.logger.exception("Exception occurred in custom command: ", exc_info=True)
                await respond(msg, "**WARNING: An error occurred while running the custom command.**")
            else:
                if res:
                    await respond(msg, res)
                else:
                    self.logger.warning(f"CC {cmd} of {str(msg.guild)} returns nothing!")
                self.ccvars = {}
                self.ccs[gid][cmd]["times_run"] += 1
                self._save_ccs()

    def _save_ccs(self):
        with open(self.plugin_config.cc_file, "w", encoding="utf8") as f:
            json.dump(self.ccs, f, indent=2, ensure_ascii=False)

    def _find_tags(self, text, msg):
        """
        Finds and processes tags, right-to-left, starting from the deepest ones.
        :param text: text of the custom command
        :param msg: message that summoned the custom command
        :return:
        """
        t_str = text[::-1]
        t_lst = []  # temporary list for closing bracket positions
        t_res = []  # final list for closing bracket positions
        t_lvl = 0  # goes up every > and down every <
        t_pos = 0  # counter for position of symbol in string

        # find all the closing brackets
        # the algorithm runs in reverse now to parse in the right direction.
        for token in t_str:
            if token == '>':
                t_lvl += 1
                t_lst.append(t_pos)
            if token == '<':
                t_lvl -= 1
                if t_lvl < 0:
                    # not enough closing brackets
                    raise CommandSyntaxError("Missing closing bracket!")
                else:
                    t_res.append(t_lst.pop())
            t_pos += 1

        if t_lvl > 0:
            # too many closing brackets
            raise CommandSyntaxError("Missing opening bracket!")

        # last tags first because otherwise positions will shift
        t_res.sort(reverse=True)

        for t_pos in t_res:
            # find closest opening bracket
            e_pos = t_str[t_pos:].find("<") + t_pos
            # replace chunk of text with the parsed result
            t_str = t_str[:t_pos] + self._parse_tag(t_str[t_pos + 1:e_pos][::-1], msg)[::-1] + t_str[e_pos + 1:]

        return t_str[::-1]

    def _parse_tag(self, tag, msg):
        args = tag.split(":", 1)
        tag = args.pop(0)
        args = " ".join(args)
        if tag.lower() in self.tags:
            return self.tags[tag](args, msg)
        else:
            raise CustomCommandSyntaxError(f"No such tag {tag}!")

    def _split_args(self, argstr):
        args = re.split(r"(?<!\\);", argstr)
        return [x.replace("\\;", ";") for x in args]

    # CC argument tag functions

    def _args(self, args, msg):
        split_args = msg.clean_content.split(" ")[1:]
        if args.isdecimal():
            try:
                i = int(args) - 1
                return split_args[i]
            except ValueError:
                raise CustomCommandSyntaxError("<args> argument is not an integer, slice or wildcard!")
            except IndexError:
                return ""
        elif args == "*":
            return " ".join(split_args)
        elif args.startswith("*"):
            try:
                i = int(args[1:])
            except ValueError:
                raise CustomCommandSyntaxError("<args> slice argument is not a valid integer!")
            return " ".join(split_args[:i])
        elif args.endswith("*"):
            try:
                i = int(args[:-1]) - 1
            except ValueError:
                raise CustomCommandSyntaxError("<args> slice argument is not a valid integer!")
            return " ".join(split_args[i:])
        else:
            raise CustomCommandSyntaxError("<args> argument is not a number or *!")

    def _username(self, args, msg):
        return msg.author.name

    def _usernick(self, args, msg):
        return msg.author.display_name

    def _usermention(self, args, msg):
        return msg.author.mention

    def _authorname(self, args, msg):
        gid = str(msg.guild.id)
        author = self.ccs[gid][msg.clean_content.split()[0][len(self.plugin_config[gid].cc_prefix):]]["author"]
        try:
            return discord.utils.get(msg.guild.members, id=author).name
        except AttributeError:
            return "<Unknown user>"

    def _authornick(self, args, msg):
        gid = str(msg.guild.id)
        author = self.ccs[gid][msg.clean_content.split()[0][len(self.plugin_config[gid].cc_prefix):]]["author"]
        try:
            return discord.utils.get(msg.guild.members, id=author).display_name
        except AttributeError:
            return "<Unknown user>"

    def _if(self, args, msg):
        args = self._split_args(args)
        if args[0] == "true":
            return args[1]
        else:
            return args[2]

    def _equals(self, args, msg):
        args = self._split_args(args)
        return str(all(i == args[0] for i in args[1:])).lower()

    def _match(self, args, msg):
        args = self._split_args(args)
        return str(any(i == args[0] for i in args[1:])).lower()

    def _not(self, args, msg):
        if args == "true":
            return "false"
        else:
            return "true"

    def _getvar(self, args, msg):
        if args.lower() in self.ccvars:
            return self.ccvars[args.lower()]
        else:
            raise CustomCommandSyntaxError(f"No such variable {args.lower()}.")

    def _setvar(self, args, msg):
        var, val = self._split_args(args)[0:2]
        self.ccvars[var.lower()] = val
        return ""

    def _contains(self, args, msg):
        args = self._split_args(args)
        for test in args[1:]:
            if test in args[0]:
                return "true"
        return "false"

    def _choice(self, args, msg):
        args = self._split_args(args)
        try:
            index = int(args[0])
        except ValueError:
            raise CommandSyntaxError("First argument to <choice> must be integer.")
        except IndexError:
            raise CustomCommandSyntaxError("<choice> requires at least one argument!")
        try:
            return args[index]
        except IndexError:
            raise CommandSyntaxError(f"<choice> does not have an argument at index {index}")

    def _isempty(self, args, msg):
        if len(args) == 0:
            return "true"
        else:
            return "false"

    def _hasrole(self, args, msg):
        args = self._split_args(args)
        roles = [x.name.lower() for x in msg.author.roles]
        for r in args:
            if r.lower() in roles:
                return "true"
        return "false"

    def _upper(self, args, msg):
        return args.upper()

    def _lower(self, args, msg):
        return args.lower()

    def _random(self, args, msg):
        return random.choice(self._split_args(args))

    def _randint(self, args, msg):
        args = self._split_args(args)
        try:
            a = int(args[0])
        except IndexError:
            raise CustomCommandSyntaxError("<randint> requires at least one argument.")
        except ValueError:
            raise CommandSyntaxError("Arguments to <randint> must be integers.")
        try:
            b = int(args[1])
        except IndexError:
            b = 0
        except ValueError:
            raise CommandSyntaxError("Arguments to <randint> must be integers.")
        if a > b:
            a, b = b, a
        return str(random.randint(a, b))

    def _rot13(self, args, msg):
        rot13 = str.maketrans(
                "ABCDEFGHIJKLMabcdefghijklmNOPQRSTUVWXYZnopqrstuvwxyz",
                "NOPQRSTUVWXYZnopqrstuvwxyzABCDEFGHIJKLMabcdefghijklm")
        return str.translate(args, rot13)

    def _transcode(self, args, msg):
        def_code = "ABCDEFGHIJKLMabcdefghijklmNOPQRSTUVWXYZnopqrstuvwxyz"
        alt_code = {
            "rot13": "NOPQRSTUVWXYZnopqrstuvwxyzABCDEFGHIJKLMabcdefghijklm",
            "circled": "ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩ",
            "circled_neg": "🅐🅑🅒🅓🅔🅕🅖🅗🅘🅙🅚🅛🅜🅐🅑🅒🅓🅔🅕🅖🅗🅘🅙🅚🅛🅜🅝🅞🅟🅠🅡🅢🅣🅤🅥🅦🅧🅨🅩🅝🅞🅟🅠🅡🅢🅣🅤🅥🅦🅧🅨🅩",
            "fwidth": "ＡＢＣＤＥＦＧＨＩＪＫＬＭａｂｃｄｅｆｇｈｉｊｋｌｍＮＯＰＱＲＳＴＵＶＷＸＹＺｎｏｐｑｒｓｔｕｖｗｘｙｚ",
            "mbold": "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳",
            "mbolditalic": "𝑨𝑩𝑪𝑫𝑬𝑭𝑮𝑯𝑰𝑱𝑲𝑳𝑴𝒂𝒃𝒄𝒅𝒆𝒇𝒈𝒉𝒊𝒋𝒌𝒍𝒎𝑵𝑶𝑷𝑸𝑹𝑺𝑻𝑼𝑽𝑾𝑿𝒀𝒁𝒏𝒐𝒑𝒒𝒓𝒔𝒕𝒖𝒗𝒘𝒙𝒚𝒛",
            "frakturbold": "𝕬𝕭𝕮𝕯𝕰𝕱𝕲𝕳𝕴𝕵𝕶𝕷𝕸𝖆𝖇𝖈𝖉𝖊𝖋𝖌𝖍𝖎𝖏𝖐𝖑𝖒𝕹𝕺𝕻𝕼𝕽𝕾𝕿𝖀𝖁𝖂𝖃𝖄𝖅𝖓𝖔𝖕𝖖𝖗𝖘𝖙𝖚𝖛𝖜𝖝𝖞𝖟",
            "fraktur": "𝔄𝔅ℭ𝔇𝔈𝔉𝔊ℌℑ𝔍𝔎𝔏𝔐𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔥𝔦𝔧𝔨𝔩𝔪𝔑𝔒𝔓𝔔ℜ𝔖𝔗𝔘𝔙𝔚𝔛𝔜ℨ𝔫𝔬𝔭𝔮𝔯𝔰𝔱𝔲𝔳𝔴𝔵𝔶𝔷",
            "scriptbold": "𝓐𝓑𝓒𝓓𝓔𝓕𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓪𝓫𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓝𝓞𝓟𝓠𝓡𝓢𝓣𝓤𝓥𝓦𝓧𝓨𝓩𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝔁𝔂𝔃",
            "script": "𝒜𝐵𝒞𝒟𝐸𝐹𝒢𝐻𝐼𝒥𝒦𝐿𝑀𝒶𝒷𝒸𝒹𝑒𝒻𝑔𝒽𝒾𝒿𝓀𝓁𝓂𝒩𝒪𝒫𝒬𝑅𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵𝓃𝑜𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏",
            "sans": "𝖠𝖡𝖢𝖣𝖤𝖥𝖦𝖧𝖨𝖩𝖪𝖫𝖬𝖺𝖻𝖼𝖽𝖾𝖿𝗀𝗁𝗂𝗃𝗄𝗅𝗆𝖭𝖮𝖯𝖰𝖱𝖲𝖳𝖴𝖵𝖶𝖷𝖸𝖹𝗇𝗈𝗉𝗊𝗋𝗌𝗍𝗎𝗏𝗐𝗑𝗒𝗓",
            "sansbold": "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇",
            "sansbolditalic": "𝘼𝘽𝘾𝘿𝙀𝙁𝙂𝙃𝙄𝙅𝙆𝙇𝙈𝙖𝙗𝙘𝙙𝙚𝙛𝙜𝙝𝙞𝙟𝙠𝙡𝙢𝙉𝙊𝙋𝙌𝙍𝙎𝙏𝙐𝙑𝙒𝙓𝙔𝙕𝙣𝙤𝙥𝙦𝙧𝙨𝙩𝙪𝙫𝙬𝙭𝙮𝙯",
            "sansitalic": "𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻",
            "parenthesized": "⒜⒝⒞⒟⒠⒡⒢⒣⒤⒥⒦⒧⒨⒜⒝⒞⒟⒠⒡⒢⒣⒤⒥⒦⒧⒨⒩⒪⒫⒬⒭⒮⒯⒰⒱⒲⒳⒴⒵⒩⒪⒫⒬⒭⒮⒯⒰⒱⒲⒳⒴⒵",
            "doublestruck": "𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫",
            "region": "🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇦🇧🇨🇩🇪🇫🇬🇭🇮🇯🇰🇱🇲🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿🇳🇴🇵🇶🇷🇸🇹🇺🇻🇼🇽🇾🇿",
            "squared": "🄰🄱🄲🄳🄴🄵🄶🄷🄸🄹🄺🄻🄼🄰🄱🄲🄳🄴🄵🄶🄷🄸🄹🄺🄻🄼🄽🄾🄿🅀🅁🅂🅃🅄🅅🅆🅇🅈🅉🄽🄾🄿🅀🅁🅂🅃🅄🅅🅆🅇🅈🅉",
            "squared_neg": "🅰🅱🅲🅳🅴🅵🅶🅷🅸🅹🅺🅻🅼🅰🅱🅲🅳🅴🅵🅶🅷🅸🅹🅺🅻🅼🅽🅾🅿🆀🆁🆂🆃🆄🆅🆆🆇🆈🆉🅽🅾🅿🆀🆁🆂🆃🆄🆅🆆🆇🆈🆉",
            "subscript": "ₐBCDₑFGₕᵢⱼₖₗₘₐbcdₑfgₕᵢⱼₖₗₘₙₒₚQᵣₛₜᵤᵥWₓYZₙₒₚqᵣₛₜᵤᵥwₓyz",
            "superscript": "ᴬᴮᶜᴰᴱᶠᴳᴴᴵᴶᴷᴸᴹᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐᴺᴼᴾQᴿˢᵀᵁⱽᵂˣʸᶻⁿᵒᵖqʳˢᵗᵘᵛʷˣʸᶻ",
            "inverted": "ɐqɔpǝɟƃɥıɾʞןɯɐqɔpǝɟƃɥıɾʞןɯuodbɹsʇn𐌡ʍxʎzuodbɹsʇnʌʍxʎz",
            "reversed": "AdↃbƎꟻGHIJK⅃MAdↄbɘꟻgHijklmᴎOꟼpᴙꙄTUVWXYZᴎoqpᴙꙅTUvwxYz",
            "smallcaps": "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴩQʀꜱᴛᴜᴠᴡxYᴢɴᴏᴩqʀꜱᴛᴜᴠᴡxyᴢ",
            "weird1": "ልጌርዕቿቻኗዘጎጋጕረጠልጌርዕቿቻኗዘጎጋጕረጠክዐየዒዪነፕሁሀሠሸሃጊክዐየዒዪነፕሁሀሠሸሃጊ",
            "weird2": "ДБҀↁЄFБНІЈЌLМаъсↁэfБЂіјкlмИФРQЯЅГЦVЩЖЧZиорqѓѕтцvшхЎz",
            "weird3": "ค๒ƈɗﻉिﻭɦٱﻝᛕɭ๓ค๒ƈɗﻉिﻭɦٱﻝᛕɭ๓กѻρ۹ɼรՇપ۷ฝซץչกѻρ۹ɼรՇપ۷ฝซץչ",
            "weird4": "αв¢∂єƒﻭнιנкℓмαв¢∂єƒﻭнιנкℓмησρ۹яѕтυνωχуչησρ۹яѕтυνωχуչ",
            "weird5": "ค๒ς๔єŦﻮђเןкɭ๓ค๒ς๔єŦﻮђเןкɭ๓ภ๏קợгรՇยשฬאץչภ๏קợгรՇยשฬאץչ",
            "weird6": "ﾑ乃cd乇ｷgんﾉﾌズﾚﾶﾑ乃cd乇ｷgんﾉﾌズﾚﾶ刀oｱq尺丂ｲu√wﾒﾘ乙刀oｱq尺丂ｲu√wﾒﾘ乙",
            "sbancient": ""
        }
        t_args = self._split_args(args)
        if t_args == [''] or len(t_args) < 2:
            raise CustomCommandSyntaxError("<transcode> tag needs at least two arguments.")
        t_str = t_args[0]
        if len(t_args) == 2:
            t_name = t_args[1].lower()
            if t_name in alt_code:
                tcode = str.maketrans(def_code, alt_code[t_name])
                return t_str.translate(tcode)
            else:
                raise CustomCommandSyntaxError(f"{t_name} is not a supported transcoding.")
        else:
            if len(t_args[1]) == len(t_args[2]):
                tcode = str.maketrans(t_args[1], t_args[2])
                return t_str.translate(tcode)
            else:
                raise CustomCommandSyntaxError("To and From transcoding patterns must be the same length.")

    def _delcall(self, args, msg):
        ensure_future(self._rm_msg(msg))
        return ""

    def _embed(self, args, msg):
        t_args = self._split_args(args)
        if t_args == ['']:
            raise CustomCommandSyntaxError("<embed> tag needs arguments in arg=val format.")
        t_embed = Embed(type="rich", colour=16711680)
        t_post = False
        for arg in t_args:
            t_arg = list(map(lambda x: x.replace("═", "="), arg.replace("\\=", "═").split("=")))
            if len(t_arg) < 2:
                continue
            t_post = True
            if t_arg[0].lower() == "!title":
                t_embed.title = t_arg[1]
            elif t_arg[0].lower() in ["!color", "!colour"]:
                try:
                    t_embed.colour = discord.Colour(int(t_arg[1], 16))
                except:
                    pass
            elif t_arg[0].lower() == "!url":
                t_embed.url = t_arg[1]
            elif t_arg[0].lower() == "!thumbnail":
                t_embed.set_thumbnail(url=t_arg[1])
            elif t_arg[0].lower() == "!image":
                t_embed.set_image(url=t_arg[1])
            elif t_arg[0].lower() in ["!desc", "!description"]:
                t_embed.description = t_arg[1]
            elif t_arg[0].lower() == "!footer":
                t_embed.set_footer(text=t_arg[1])
            else:
                t_name = t_arg[0]
                t_val = t_arg[1]
                if len(t_arg) > 2:
                    t_inline = is_positive(t_arg[2])
                else:
                    t_inline = False
                t_embed.add_field(name=t_name, value=t_val, inline=t_inline)
        if t_post:
            ensure_future(respond(msg, None, embed=t_embed))
        return ""

    def _noembed(self, args, msg):
        return f"<{args}>"

    # util functions

    async def _rm_msg(self, msg):
        await sleep(1)
        await msg.delete()

    def _initialize(self, gid):
        if gid not in self.plugin_config:
            self.plugin_config[gid] = DotDict(self.default_config["default"])
            self.config_manager.save_config()
        if gid not in self.storage:
            self.storage[gid] = {
                "cc_create_ban": [],
                "cc_use_ban": []
            }
