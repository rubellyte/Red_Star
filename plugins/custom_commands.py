import re
import random
import json
import datetime
from plugin_manager import BasePlugin
import discord.utils
from utils import respond, Command

class CustomCommands(BasePlugin):
    name = "custom_commands"
    default_config = {
        "cc_file": "config/ccs.json",
        "cc_prefix": "!!"
    }

    def activate(self):
        self.args = None
        self.tags = {
            "random": self._random,
            "rot13": self._rot13
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

    async def on_message(self, data):
        deco = self.plugin_config.cc_prefix
        if data.author != self.client.user:
            cnt = data.content
            if cnt.startswith(deco):
                cmd = cnt[len(deco):].split()[0].lower()
                if cmd in self.ccs:
                    await self.run_cc(cmd, data)
                else:
                    await respond(self.client, data, f"**WARNING: No such custom command {cmd}.**")

    @Command("createcc",
             doc="Creates a custom command.",
             syntax="(name) (content)",
             category="custom_commands")
    async def _createcc(self, data):
        try:
            args = data.clean_content.split()[1:]
            name = args[0].lower()
        except IndexError:
            raise SyntaxError("No name provided.")
        try:
            content = " ".join(args[1:])
        except IndexError:
            raise SyntaxError("No content provided.")
        if name in self.ccs:
            await respond(self.client, data, f"**WARNING: Custom command {args[0]} already exists.**")
        else:
            newcc = {
                "name": name,
                "content": content,
                "author": data.author.id,
                "date_created": datetime.datetime.now().strftime("%Y-%m-%d @ %H:%M:%S"),
                "last_edited": None,
                "locked": False,
                "times_run": 0
            }
            self.ccs[args[0].lower()] = newcc
            self._save_ccs()
            await respond(self.client, data, f"**ANALYSIS: Custom command {name} created successfully.**")

    @Command("editcc",
             doc="Edits a custom command you created.",
             syntax="(name) (content)",
             category="custom_commands")
    async def _editcc(self, data):
        try:
            args = data.clean_content.split()[1:]
            name = args[0].lower()
        except IndexError:
            raise SyntaxError("No name provided.")
        try:
            content = " ".join(args[1:])
        except IndexError:
            raise SyntaxError("No content provided.")
        if name in self.ccs:
            ccdata = self.ccs[name]
            if ccdata["author"] == data.author.id or data.author.server_permissions.manage_messages:
                ccdata["content"] = content
                ccdata["last_edited"] = datetime.datetime.now().strftime("%Y-%m-%d @ %H:%M:%S")
                self.ccs[name] = ccdata
                self._save_ccs()
                await respond(self.client, data, f"**ANALYSIS: Custom command {name} edited successfully.**")
            else:
                await respond(self.client, data, f"**WARNING: No permission to edit custom command {name}.**")
        else:
            await respond(self.client, data, f"**WARNING: No such custom command {name}**")

    @Command("delcc",
             doc="Deletes a custom command.",
             syntax="(name)",
             category="custom_commands")
    async def _delcc(self, data):
        try:
            name = data.clean_content.split()[1].lower()
        except IndexError:
            raise SyntaxError("No name provided.")
        if name in self.ccs:
            if self.ccs[name]["author"] == data.author.id or data.author.server_permissions.manage_messages:
                del self.ccs[name]
                self._save_ccs()
                await respond(self.client, data, f"**ANALYSIS: Custom command {name} deleted successfully.**")
            else:
                await respond(self.client, data, f"**WARNING: No permission to delete custom command {name}.**")
        else:
            await respond(self.client, data, f"**WARNING: No such custom command {name}.**")

    @Command("ccinfo",
             doc="Displays information about a custom command.",
             syntax="(name)",
             category="custom_commands")
    async def _ccinfo(self, data):
        try:
            name = data.clean_content.split()[1].lower()
        except IndexError:
            raise SyntaxError("No name provided.")
        if name in self.ccs:
            ccdata = self.ccs[name]
            last_edited = ccdata["last_edited"] if ccdata["last_edited"] else ""
            cc_locked = "Yes" if ccdata["locked"] else "No"
            author = discord.utils.get(data.server.members, id=ccdata["author"])
            if author:
                author = f"{author.name}#{author.discriminator}"
            else:
                author = "<Unknown user>"
            datastr = f"**ANALYSIS: Information for custom command {name}:**```\nName: {name}\nAuthor: {author}\n" \
                      f"Date Created: {ccdata['date_created']}\n{last_edited}Locked: {cc_locked}\n" \
                      f"Times Run: {ccdata['times_run']}```"
            await respond(self.client, data, datastr)
        else:
            await respond(self.client, data, f"**WARNING: No such custom command {name}.**")

    @Command("searchccs",
             doc="Searches CCs by name.",
             syntax="(type) (search)",
             category="custom_commands")
    async def _searchccs(self, data):
        try:
            search = " ".join(data.clean_content.split()[1:])
        except IndexError:
            raise SyntaxError("No search provided.")
        res = []
        for cc in self.ccs.keys():
            if search in cc:
                res.append(cc)
        if res:
            res = ", ".join(res)
            await respond(self.client, data, f"**ANALYSIS: The following custom commands match your search:** `{res}`")
        else:
            await respond(self.client, data, "**WARNING: No results found for your search.**")

    @Command("lockcc",
             doc="Toggles lock on a custom command, preventing it from being used.",
             syntax="(name)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _lockcc(self, data):
        try:
            name = data.clean_content.split()[1].lower()
        except IndexError:
            raise SyntaxError("No name provided.")
        if name in self.ccs:
            self.ccs[name]["locked"] = not self.ccs[name]["locked"]
            lock_status = "locked" if self.ccs[name]["locked"] else "unlocked"
            await respond(self.client, data, f"**ANALYSIS: Custom command {name} has been {lock_status}.**")
        else:
            await respond(self.client, data, f"**WARNING: No such custom command {name}.**")

    async def run_cc(self, cmd, data):
        if self.ccs[cmd]["locked"] and not data.author.server_permissions.manage_messages:
            await respond(self.client, data, "**WARNING: Custom command {cmd} is locked.**")
        else:
            self.args = data.clean_content.split()[1:]
            ccdat = self.ccs[cmd]["content"]
            res = self._find_tags(ccdat)
            await respond(self.client, data, res)
            self.ccs[cmd]["times_run"] += 1
            self._save_ccs()

    def _save_ccs(self):
        with open(self.plugin_config.cc_file, "w") as f:
            json.dump(self.ccs, f, indent=2)


    def _find_tags(self, s):
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
                parsed = self._parse_tag(tag)
                return parsed + tag_iter(level)
            else:
                return "".join([token]) + tag_iter(level)

        tokens = iter(s)
        return tag_iter()

    def _parse_tag(self, tag):
        tag, args = tag.split(":", 1)
        if self.tags[tag]:
            return self.tags[tag](args)
        else:
            raise SyntaxError(f"No such tag {tag}!")

    def _split_args(self, argstr):
        args = re.split(r"(?<!\\);", argstr)
        return [x.replace("\\;", ";") for x in args]

    def _random(self, args):
        return random.choice(self._split_args(args))

    def _rot13(self, args):
        rot13 = str.maketrans(
                "ABCDEFGHIJKLMabcdefghijklmNOPQRSTUVWXYZnopqrstuvwxyz",
                "NOPQRSTUVWXYZnopqrstuvwxyzABCDEFGHIJKLMabcdefghijklm")
        return str.translate(args, rot13)