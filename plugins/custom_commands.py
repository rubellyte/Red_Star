import re
import random
import json
import datetime
from asyncio import ensure_future
from plugin_manager import BasePlugin
import discord.utils
from rs_utils import respond, Command, DotDict, find_user, is_positive
from discord import Embed


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
            "noembed": self._noembed
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
        self.initialize(gid)
        if msg.author.id in self.storage[gid]["cc_use_ban"]:
            await msg.author.send(f"**WARNING: You are banned from usage of custom commands on the server "
                                  f"{str(msg.guild)}**")
            return
        deco = self.plugin_config[gid].cc_prefix
        if msg.author != self.client.user:
            cnt = msg.content
            if cnt.startswith(deco):
                cmd = cnt[len(deco):].split()[0].lower()
                if gid not in self.ccs:
                    self.ccs[gid] = {}
                if cmd in self.ccs[gid]:
                    await self.run_cc(cmd, msg)

    # Commands

    @Command("createcc", "newcc",
             doc="Creates a custom command.\n"
                 "Tag Documentation: https://github.com/medeor413/Red_Star/wiki/Custom-Commands",
             syntax="(name) (content)",
             category="custom_commands")
    async def _createcc(self, msg):
        gid = str(msg.guild.id)
        self.initialize(gid)
        if msg.author.id in self.storage[gid]["cc_create_ban"]:
            raise PermissionError("You are banned from creating custom commands.")
        try:
            args = msg.clean_content.split(" ")[1:]
            name = args[0].lower()
        except IndexError:
            raise SyntaxError("No name provided.")
        try:
            content = " ".join(args[1:])
        except IndexError:
            raise SyntaxError("No content provided.")
        if gid not in self.ccs:
            self.ccs[gid] = {}
        if name in self.ccs[gid]:
            await respond(msg, f"**WARNING: Custom command {args[0]} already exists.**")
        else:
            t_count = len([True for i in self.ccs[gid].values() if i["author"] == msg.author.id])

            if ("bot_maintainers" in self.config_manager.config and msg.author.id not in
                self.config_manager.config.bot_maintainers) or "bot_maintainers" not in self.config_manager.config:
                if t_count >= self.storage[gid]["cc_limit"] \
                        and not msg.author.permissions_in(msg.channel).manage_messages:
                    raise PermissionError(f"Exceeded cc limit of {self.plugin_config[gid]['cc_limit']}")
            newcc = {
                "name": name,
                "content": content,
                "author": msg.author.id,
                "date_created": datetime.datetime.now().strftime("%Y-%m-%d @ %H:%M:%S"),
                "last_edited": None,
                "locked": False,
                "times_run": 0
            }
            self.ccs[gid][args[0].lower()] = newcc
            self._save_ccs()
            await respond(msg, f"**ANALYSIS: Custom command {name} created successfully.**")

    @Command("editcc",
             doc="Edits a custom command you created.",
             syntax="(name) (content)",
             category="custom_commands")
    async def _editcc(self, msg):
        gid = str(msg.guild.id)
        self.initialize(gid)
        if msg.author.id in self.storage[gid]["cc_create_ban"]:
            raise PermissionError("You are banned from editing custom commands.")
        try:
            args = msg.clean_content.split(" ")[1:]
            name = args[0].lower()
        except IndexError:
            raise SyntaxError("No name provided.")
        try:
            content = " ".join(args[1:])
        except IndexError:
            raise SyntaxError("No content provided.")
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
        self.initialize(gid)
        if msg.author.id in self.storage[gid]["cc_create_ban"]:
            raise PermissionError("You are banned from deleting custom commands.")
        try:
            name = msg.clean_content.split()[1].lower()
        except IndexError:
            raise SyntaxError("No name provided.")
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
            raise SyntaxError("No name provided.")
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
        if user:
            by_author = True
            user = user.id
        if not search:
            raise SyntaxError("No search provided.")
        res = []
        gid = str(msg.guild.id)
        if gid not in self.ccs:
            self.ccs[gid] = {}
        for cc, info in self.ccs[gid].items():
            if not by_author and search in cc.lower():
                res.append(cc)
            elif info["author"] == user:
                res.append(cc)
        if res:
            res = ", ".join(res)
            await respond(msg, f"**ANALYSIS: The following custom commands match your search:** `{res}`")
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
            raise SyntaxError("No name provided.")
        gid = str(msg.guild.id)
        if gid not in self.ccs:
            self.ccs[gid] = {}
        if name in self.ccs[gid]:
            self.ccs[gid][name]["locked"] = not self.ccs[gid][name]["locked"]
            lock_status = "locked" if self.ccs[gid][name]["locked"] else "unlocked"
            await respond(msg, f"**ANALYSIS: Custom command {name} has been {lock_status}.**")
        else:
            await respond(msg, f"**WARNING: No such custom command {name}.**")

    @Command("ccmute", "mutecc",
             doc="Toggles users ability to use custom commands.",
             syntax="(user)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _mutecc(self, msg):
        gid = str(msg.guild.id)
        self.initialize(gid)

        args = msg.content.split(" ", 1)

        print(args[1])

        t_member = find_user(msg.guild, args[1])

        if not t_member:
            raise SyntaxError("Not a user, or user not found.")

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
        self.initialize(gid)

        args = msg.content.split(" ", 1)

        print(args[1])

        t_member = find_user(msg.guild, args[1])

        if not t_member:
            raise SyntaxError("Not a user, or user not found.")

        if t_member.id in self.storage[gid]["cc_create_ban"]:
            self.storage[gid]["cc_create_ban"].remove(t_member.id)
            await respond(msg, f"**AFFIRMATIVE. User {t_member.mention} was allowed creation of custom commands.**")
        else:
            self.storage[gid]["cc_create_ban"].append(t_member.id)
            await respond(msg, f"**AFFIRMATIVE. User {t_member.mention} was banned from creating custom commands.**")

    # Custom command machinery

    async def run_cc(self, cmd, msg):
        gid = str(msg.guild.id)
        if self.ccs[gid][cmd]["locked"] and not msg.author.guild_permissions.manage_messages:
            await respond(msg, f"**WARNING: Custom command {cmd} is locked.**")
        else:
            ccdat = self.ccs[gid][cmd]["content"]
            try:
                res = self._find_tags(ccdat, msg)
            except (SyntaxError, SyntaxWarning) as e:
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
        t_str = text
        t_lst = []  # temporary list for opening bracket positions
        t_res = []  # final list for opening bracket positions
        t_lvl = 0  # goes up every < and down every >
        t_pos = 0  # counter for position of symbol in string

        # find all the opening brackets
        for token in t_str:
            if token == '<':
                t_lvl += 1
                t_lst.append(t_pos)
            if token == '>':
                t_lvl -= 1
                if t_lvl < 0:
                    # not enough opening brackets
                    raise SyntaxError("Missing opening bracket!")
                else:
                    t_res.append(t_lst.pop())
            t_pos += 1

        if t_lvl > 0:
            # too many opening brackets
            raise SyntaxError("Missing closing bracket!")

        # last tags first because otherwise positions will shift
        t_res.sort(reverse=True)

        for t_pos in t_res:
            # find closest closing bracket
            e_pos = t_str[t_pos:].find(">") + t_pos
            # replace chunk of text with the parsed result
            t_str = t_str[:t_pos] + self._parse_tag(t_str[t_pos + 1:e_pos], msg) + t_str[e_pos + 1:]

        return t_str

    def _parse_tag(self, tag, msg):
        args = tag.split(":", 1)
        tag = args.pop(0)
        args = " ".join(args)
        if tag.lower() in self.tags:
            return self.tags[tag](args, msg)
        else:
            raise SyntaxError(f"No such tag {tag}!")

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
                raise SyntaxError("<args> argument is not an integer, slice or wildcard!")
            except IndexError:
                return ""
        elif args == "*":
            return " ".join(split_args)
        elif args.startswith("*"):
            try:
                i = int(args[1:])
            except ValueError:
                raise SyntaxError("<args> slice argument is not a valid integer!")
            return " ".join(split_args[:i])
        elif args.endswith("*"):
            try:
                i = int(args[:-1]) - 1
            except ValueError:
                raise SyntaxError("<args> slice argument is not a valid integer!")
            return " ".join(split_args[i:])
        else:
            raise SyntaxError("<args> argument is not a number or *!")

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
            raise SyntaxError(f"No such variable {args.lower()}.")

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
            raise SyntaxError("First argument to <choice> must be integer.")
        except IndexError:
            raise SyntaxError("<choice> requires at least one argument!")
        try:
            return args[index]
        except IndexError:
            raise SyntaxError(f"<choice> does not have an argument at index {index}")

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
            raise SyntaxError("<randint> requires at least one argument.")
        except ValueError:
            raise SyntaxError("Arguments to <randint> must be integers.")
        try:
            b = int(args[1])
        except IndexError:
            b = 0
        except ValueError:
            raise SyntaxError("Arguments to <randint> must be integers.")
        if a > b:
            a, b = b, a
        return str(random.randint(a, b))

    def _rot13(self, args, msg):
        rot13 = str.maketrans(
                "ABCDEFGHIJKLMabcdefghijklmNOPQRSTUVWXYZnopqrstuvwxyz",
                "NOPQRSTUVWXYZnopqrstuvwxyzABCDEFGHIJKLMabcdefghijklm")
        return str.translate(args, rot13)

    def _delcall(self, args, msg):
        ensure_future(msg.delete())
        return ""

    def _embed(self, args, msg):
        t_args = self._split_args(args)
        if t_args == ['']:
            raise SyntaxError("<embed> tag needs arguments in arg=val format.")
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

    def initialize(self, gid):
        if gid not in self.plugin_config:
            self.plugin_config[gid] = DotDict(self.default_config["default"])
            self.config_manager.save_config()
        if gid not in self.storage:
            self.storage[gid] = {
                "cc_create_ban": [],
                "cc_use_ban": []
            }
