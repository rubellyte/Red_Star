import re
import random
import json
import datetime
from asyncio import ensure_future
from plugin_manager import BasePlugin
import discord.utils
from utils import respond, Command, DotDict


class CustomCommands(BasePlugin):
    name = "custom_commands"
    default_config = {
        "cc_file": "config/ccs.json",
        "default": {
            "cc_prefix": "!!"
        }
    }

    async def activate(self):
        self.args = None
        self.tags = {
            "args": self._args,
            "username": self._username,
            "usernick": self._usernick,
            "usermention": self._usermention,
            "authorname": self._authorname,
            "authornick": self._authornick,
            "if": self._if,
            "not": self._not,
            "isempty": self._isempty,
            "equals": self._equals,
            "hasrole": self._hasrole,
            "upper": self._upper,
            "lower": self._lower,
            "random": self._random,
            "rot13": self._rot13,
            "delcall": self._delcall
        }
        try:
            with open(self.plugin_config.cc_file, "r") as f:
                self.ccs = json.load(f)
        except FileNotFoundError:
            self.ccs = {}
            with open(self.plugin_config.cc_file, "w") as f:
                f.write("{}")
        except json.decoder.JSONDecodeError:
            self.logger.exception("Could not decode ccs.json! ", exc_info=True)

    # Event hooks

    async def on_message(self, msg):
        gid = str(msg.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = DotDict(self.default_config["default"])
            self.config_manager.save_config()
        deco = self.plugin_config[gid].cc_prefix
        if msg.author != self.client.user:
            cnt = msg.content
            if cnt.startswith(deco):
                cmd = cnt[len(deco):].split()[0].lower()
                if gid not in self.ccs:
                    self.ccs[gid] = {}
                if cmd in self.ccs[gid]:
                    await self.run_cc(cmd, msg)
                else:
                    await respond(msg, f"**WARNING: No such custom command {cmd}.**")

    # Commands

    @Command("createcc",
             doc="Creates a custom command.",
             syntax="(name) (content)",
             category="custom_commands")
    async def _createcc(self, msg):
        gid = str(msg.guild.id)
        try:
            args = msg.clean_content.split()[1:]
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
        try:
            args = msg.clean_content.split()[1:]
            name = args[0].lower()
        except IndexError:
            raise SyntaxError("No name provided.")
        try:
            content = " ".join(args[1:])
        except IndexError:
            raise SyntaxError("No content provided.")
        gid = str(msg.guild.id)
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
        try:
            name = msg.clean_content.split()[1].lower()
        except IndexError:
            raise SyntaxError("No name provided.")
        gid = str(msg.guild.id)
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
                author = f"{author.name}#{author.discriminator}"
            else:
                author = "<Unknown user>"
            datastr = f"**ANALYSIS: Information for custom command {name}:**```\nName: {name}\nAuthor: {author}\n" \
                      f"Date Created: {ccdata['date_created']}\n{last_edited}Locked: {cc_locked}\n" \
                      f"Times Run: {ccdata['times_run']}```"
            await respond(msg, datastr)
        else:
            await respond(msg, f"**WARNING: No such custom command {name}.**")

    @Command("searchccs",
             doc="Searches CCs by name.",
             syntax="(search)",
             category="custom_commands")
    async def _searchccs(self, msg):
        search = " ".join(msg.clean_content.split()[1:])
        if not search:
            raise SyntaxError("No search provided.")
        res = []
        if msg.guild.id not in self.ccs:
            self.ccs[msg.guild.id] = {}
        for cc in self.ccs[str(msg.guild.id)].keys():
            if search in cc:
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
                await respond(msg, res)
                self.args = None
                self.ccs[gid][cmd]["times_run"] += 1
                self._save_ccs()

    def _save_ccs(self):
        with open(self.plugin_config.cc_file, "w") as f:
            json.dump(self.ccs, f, indent=2)

    def _find_tags(self, text, msg):
        def tag_iter(level=0):
            try:
                token = next(tokens)
            except StopIteration:
                if level != 0:
                    raise SyntaxError("Missing closing bracket!")
                else:
                    return ""
            if token == '>':
                if level == 0:
                    raise SyntaxError("Missing opening bracket!")
                else:
                    return ""
            elif token == '<':
                tag = "".join([tag_iter(level + 1)])
                parsed = self._parse_tag(tag, msg)
                return parsed + tag_iter(level)
            else:
                return "".join([token]) + tag_iter(level)

        tokens = iter(text)
        return tag_iter()

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
        split_args = msg.clean_content.split()[1:]
        if args.isdecimal():
            try:
                i = int(args) - 1
                return split_args[i]
            except ValueError:
                raise SyntaxError("<args> argument is not a number or *!")
            except IndexError:
                return ""
        elif args == "*":
            return " ".join(split_args)
        else:
            raise SyntaxError("<args> argument is not a number or *!")

    def _username(self, args, msg):
        return msg.author.name

    def _usernick(self, args, msg):
        return msg.author.display_name

    def _usermention(self, args, msg):
        return msg.author.mention

    def _authorname(self, args, msg):
        author = self.ccs[str(msg.guild.id)][msg.clean_content.split()[0][len(self.plugin_config.cc_prefix):]]["author"]
        return discord.utils.get(msg.guild.members, id=author).name

    def _authornick(self, args, msg):
        author = self.ccs[str(msg.guild.id)][msg.clean_content.split()[0][len(self.plugin_config.cc_prefix):]]["author"]
        return discord.utils.get(msg.guild.members, id=author).display_name

    def _if(self, args, msg):
        args = self._split_args(args)
        if args[0] == "true":
            return args[1]
        else:
            return args[2]

    def _equals(self, args, msg):
        args = self._split_args(args)
        test = args[0]
        for arg in args[1:]:
            if test != arg:
                return "false"
        else:
            return "true"

    def _not(self, args, msg):
        if args == "true":
            return "false"
        else:
            return "true"

    def _isempty(self, args, msg):
        if len(args) == 0:
            return "true"
        else:
            return "false"

    def _hasrole(self, args, msg):
        if args[0] in [x.name.lower() for x in msg.author.roles]:
            return "true"
        else:
            return "false"

    def _upper(self, args, msg):
        return args.upper()

    def _lower(self, args, msg):
        return args.lower()

    def _random(self, args, msg):
        return random.choice(self._split_args(args))

    def _rot13(self, args, msg):
        rot13 = str.maketrans(
                "ABCDEFGHIJKLMabcdefghijklmNOPQRSTUVWXYZnopqrstuvwxyz",
                "NOPQRSTUVWXYZnopqrstuvwxyzABCDEFGHIJKLMabcdefghijklm")
        return str.translate(args, rot13)

    def _delcall(self, args, msg):
        ensure_future(msg.delete())
        return ""
