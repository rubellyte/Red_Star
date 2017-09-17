import re
import json
import shlex
from random import randint
from rs_errors import CommandSyntaxError, UserPermissionError
from rs_utils import respond, DotDict, find_role, find_user, split_output
from command_dispatcher import Command
from plugin_manager import BasePlugin
from discord import Embed, File
from io import BytesIO


class Roleplay(BasePlugin):
    name = "roleplay"
    fields = ["name", "race", "gender", "height", "age", "theme", "link", "image", "appearance", "equipment", "skills",
              "personality", "backstory", "interests"]
    mandatory_fields = ["name", "race", "gender", "appearance", "backstory"]
    default_config = {
        "bio_file": "config/bios.json",
        "allow_race_requesting": False,
        "default": {
            "race_roles": []
        }
    }

    async def activate(self):
        try:
            with open(self.plugin_config.bio_file, "r", encoding="utf8") as f:
                self.bios = json.load(f)
        except FileNotFoundError:
            self.bios = {}
            with open(self.plugin_config.bio_file, "w", encoding="utf8") as f:
                f.write("{}")
        except json.decoder.JSONDecodeError:
            self.logger.exception("Could not decode bios.json! ", exc_info=True)

    @Command("roll",
             doc="Rolls a specified amount of specified dice with specified bonus and advantage/disadvantage",
             syntax="[number]D(die)[+/-bonus][A/D]",
             category="role_play",
             run_anywhere=True)
    async def _roll(self, msg):
        args = msg.content.split(" ", 1)
        if len(args) < 2:
            raise CommandSyntaxError("Needs an argument, dumbass.")
        dice_data = re.search(r"(\d+|)d(\d+)(\+\d+|-\d+|)(a|d|)", args[1].lower())
        if dice_data:
            if dice_data.group(1):
                num_dice = min(max(int(dice_data.group(1)), 1), 10000)
            else:
                num_dice = 1
            die_sides = min(max(int(dice_data.group(2)), 2), 10000)
            if dice_data.group(3):
                modif = int(dice_data.group(3))
                modif_str = f" with a {'+' if modif > 0 else ''}{modif} modifier"
            else:
                modif = 0
                modif_str = ""
            t_adv = dice_data.group(4)
            dice_set_a = [randint(1, die_sides) for i in range(num_dice)]
            dice_set_b = [randint(1, die_sides) for i in range(num_dice)]
            if t_adv == "a":
                rolled_dice = dice_set_a if sum(dice_set_a) >= sum(dice_set_b) else dice_set_b
                advstr = "an advantageous"
            elif t_adv == "d":
                rolled_dice = dice_set_a if sum(dice_set_a) < sum(dice_set_b) else dice_set_b
                advstr = "a disadvantageous"
            else:
                rolled_dice = dice_set_a
                advstr = "a"
            rolled_sum = sum(rolled_dice) + modif
            dicestr = "] [".join(map(str, rolled_dice))
            dicestr = f"[{dicestr}]"
            await respond(msg,
                          f"**ANALYSIS: {msg.author.display_name} has attempted {advstr} "
                          f"{num_dice}D{die_sides} roll{modif_str}, getting {rolled_sum}.**\n"
                          f"**ANALYSIS: Rolled dice:** `{dicestr}`")

    @Command("racerole",
             doc="Adds or removes roles from the list of race roles that are searched by the bio command.",
             syntax="add/remove (role mentions)",
             perms={"manage_messages"},
             category="role_play")
    async def _racerole(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        args = shlex.split(msg.content)
        if len(args) < 2:
            await split_output(msg, "**ANALYSIS: Currently approved race roles:**",
                               [x.name for x in msg.guild.roles if x.id in self.plugin_config[gid]["race_roles"]])
        else:
            if args[1].lower() == "add":
                for arg in args[1:]:
                    t_role = find_role(msg.guild, arg)
                    if t_role and t_role.id not in self.plugin_config[gid]["race_roles"]:
                        self.plugin_config[gid]["race_roles"].append(t_role.id)
                await respond(msg, "**AFFIRMATIVE. Roles added to race list.**")
            elif args[1].lower() == "remove":
                for arg in args[1:]:
                    t_role = find_role(msg.guild, arg)
                    if t_role and t_role.id not in self.plugin_config[gid]["race_roles"]:
                        self.plugin_config[gid]["race_roles"].remove(t_role.id)
                await respond(msg, "**AFFIRMATIVE. Roles removed from race list.**")
            else:
                raise CommandSyntaxError(f"Unsupported mode {args[1].lower()}.")

    @Command("getracerole",
             doc="Allows the user to request one of the approved race roles for themselves.",
             syntax="(role)",
             category="role_play")
    async def _getracerole(self, msg):
        if not self.plugin_config.get("allow_race_requesting", False):
            return
        gid = str(msg.guild.id)
        self._initialize(gid)
        args = msg.content.split(" ", 1)
        t_role_list = []
        for role in msg.author.roles:
            if role.id in self.plugin_config[gid]["race_roles"]:
                t_role_list.append(role)
        await msg.author.remove_roles(*t_role_list)
        if len(args) < 2:
            await respond(msg, "**AFFIRMATIVE. Race role removed.**")
        else:
            t_role = find_role(msg.guild, args[1])
            if t_role:
                if t_role.id in self.plugin_config[gid]["race_roles"]:
                    await msg.author.add_roles(t_role)
                    await respond(msg, f"**AFFIRMATIVE. Race role {str(t_role)} granted.**")
                else:
                    raise CommandSyntaxError("Not an approved race role.")
            else:
                raise CommandSyntaxError("Not a role or role not found.")

    @Command("listraceroles",
             doc="Lists all approved race roles.",
             category="role_play")
    async def _listraceroles(self, msg):
        if not self.plugin_config.get("allow_race_requesting", False):
            return
        gid = str(msg.guild.id)
        self._initialize(gid)
        await split_output(msg, "**ANALYSIS: Currently approved race roles:**",
                           [x.name for x in msg.guild.roles if x.id in self.plugin_config[gid]["race_roles"]])

    @Command("listbio",
             doc="Lists all available bios in the database.",
             syntax="[user]",
             category="role_play")
    async def _listbio(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        args = msg.content.split(" ", 1)
        if len(args) > 1:
            t_member = find_user(msg.guild, args[1])
            if t_member:
                t_bio_list = [v["name"] for k, v in self.bios[gid].items() if v.get("author", 0) == t_member.id]
                await split_output(msg, f"**ANALYSIS: User {t_member.display_name} has following characters:**",
                                   t_bio_list)
            else:
                raise CommandSyntaxError("Not a user or user not found.")
        else:
            await split_output(msg, "**ANALYSIS: Following character bios found:**",
                               [v['name'] for k, v in self.bios[gid].items()])

    @Command("bio",
             doc="Adds, edits, prints, dumps or deletes character bios.\n"
                 "Each character name must be unique.\n"
                 "Fields: race/gender/height/age: limit 64 characters. theme/link: must be viable http(s) url. "
                 "appearance/equipment/skills/personality/backstory/interests: limit 1024 characters.\n"
                 "Setting 'race' to the same name as a registered character role will fetch the colour.\n"
                 "Be aware that the total length of the bio must not exceed 6000 characters.",
             syntax="\nediting/creating: (name) set (field) [value]\n"
                    "printing: (name)\n"
                    "dumping: (name) dump\n"
                    "deleting: (name) delete",
             category="role_play",
             run_anywhere=True)
    async def _bio(self, msg):
        """
        multipurpose command.

        !bio (name) - print out bio
        !bio (name) (set) (field) [value] - set a bio value
        !bio (name) (delete) - delete the bio

        :param msg:
        :return:
        """
        gid = str(msg.guild.id)
        self._initialize(gid)
        try:
            args = shlex.split(msg.content)
        except ValueError as e:
            self.logger.warning("Unable to split {data.content}. {e}")
            raise CommandSyntaxError(e)

        if len(args) < 2:
            raise CommandSyntaxError("At least one argument required.")

        t_name = args[1].lower()

        if len(args) == 2:
            if t_name in self.bios[gid]:
                await respond(msg, None, embed=self._print_bio(msg.guild, t_name))
            else:
                raise CommandSyntaxError(f"No such character {args[1]}.")
        elif len(args) == 3:
            if args[2].lower() == "delete":
                if t_name in self.bios[gid]:
                    if self.bios[gid][t_name].get("author", 0) == msg.author.id or \
                            msg.author.permissions_in(msg.channel).manage_messages or \
                            msg.author.id in self.config_manager.config.get("bot_maintainers", []):
                        del self.bios[gid][t_name]
                        await respond(msg, f"**AFFIRMATIVE. Character bio {args[1]} was deleted.**")
                    else:
                        raise UserPermissionError("Character belongs to other user.")
                else:
                    raise CommandSyntaxError(f"No such character {args[1]}.")
                self._save_bios()
            elif args[2].lower() == "dump":
                if t_name in self.bios[gid]:
                    t_bio = self.bios[gid][t_name].copy()
                    del t_bio["author"]
                    t_bio = json.dumps(t_bio, indent=2, ensure_ascii=False)
                    async with msg.channel.typing():
                        await respond(msg, "**AFFIRMATIVE. Completed file upload.**",
                                      file=File(BytesIO(bytes(t_bio, encoding="utf-8")), filename=t_name+".json"))
                else:
                    raise CommandSyntaxError(f"No such character {args[1]}.")

        elif len(args) >= 4 and args[2].lower() == "set":
            if t_name in self.bios[gid]:
                if self.bios[gid][t_name].get("author", 0) != msg.author.id:
                    raise UserPermissionError("Character belongs to other user.")
            else:
                if len(t_name) > 64:
                    raise CommandSyntaxError("Character name too long. Maximum length is 64 characters.")
                self.bios[gid][t_name] = {
                    "author": msg.author.id,
                    "name": args[1],
                    "race": "undefined",
                    "gender": "undefined",
                    "appearance": "undefined",
                    "backstory": "undefined"
                }
                for f in self.fields:
                    if f not in self.bios[gid][t_name]:
                        self.bios[gid][t_name][f] = ""
                await respond(msg, f"**ANALYSIS: created character {args[1]}.**")
                self._save_bios()
            t_field = args[3].lower()
            if t_field in self.fields and t_field != "name":
                bio = self.bios[gid][t_name]
                if len(args) < 5:
                    if t_field in self.mandatory_fields:
                        bio[t_field] = "undefined"
                    else:
                        bio[t_field] = ""
                    await respond(msg, f"**AFFIRMATIVE. {t_field.capitalize()} reset.**")
                else:
                    t_value = " ".join(args[4:])
                    if t_field in ["race", "gender", "height", "age"]:
                        if len(t_value) > 64:
                            raise CommandSyntaxError(f"{t_field.capitalize()} too long. "
                                                     f"Maximum length is 64 characters.")
                        bio[t_field] = t_value
                        await respond(msg, f"**AFFIRMATIVE. {t_field.capitalize()} set.**")
                    else:
                        if len(t_value) > 1024:
                            raise CommandSyntaxError(f"{t_field.capitalize()} too long. "
                                                     f"Maximum length is 1024 characters.")
                        bio[t_field] = t_value
                        await respond(msg, f"**AFFIRMATIVE. {t_field.capitalize()} set.**")
            elif t_field not in self.fields:
                raise CommandSyntaxError(f"Available fields: {', '.join(self.fields[1:])}.")
            self._save_bios()

    @Command("uploadbio",
             doc="Parses a json file to update/create character bios.\n"
                 "See output of !bio (charname) dump for more details on file formatting.",
             syntax="(attach the file to the message, no arguments required)",
             category="role_play")
    async def _uploadbio(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        if msg.attachments:
            t_file = BytesIO()
            await msg.attachments[0].save(t_file)
            try:
                t_data = json.loads(t_file.getvalue().decode())
            except:
                raise CommandSyntaxError("Not a valid JSON file.")
        else:
            args = re.split("\w|\\r|\\n", msg.content, 1)
            if len(args) == 1:
                raise CommandSyntaxError("File or code block required")
            t_search = re.search("```.*({.+}).*```", args[1], re.DOTALL)
            if t_search:
                try:
                    t_data = json.loads(t_search.group(1))
                except:
                    raise CommandSyntaxError("Not a valid JSON string.")
            else:
                raise CommandSyntaxError("Not valid JSON code block.")

        if "name" not in t_data:
            raise CommandSyntaxError("Not a valid character file: No name.")

        t_bio = {}

        for field in self.fields:
            t_field = t_data.get(field, "")
            if t_field:
                t_len = len(t_field)
                if field in ["name", "race", "gender", "height", "age"] and t_len > 64:
                    raise CommandSyntaxError(f"Not a valid character file: field {field} too long (max 64 chars).")
                elif field in ["link", "theme"] and t_len > 256:
                    raise CommandSyntaxError(f"Not a valid character file: field {field} too long (max 256 chars).")
                elif t_len > 1024:
                    raise CommandSyntaxError(f"Not a valid character file: field {field} too long (max 1024 chars).")
                t_bio[field] = t_field

        t_name = t_bio["name"].lower()
        if t_name in self.bios[gid]:
            if self.bios[gid][t_name].get("author", 0) != msg.author.id:
                raise PermissionError("Character belongs to other user.")
        else:
            self.bios[gid][t_name] = {
                "author": msg.author.id,
                "name": t_bio["name"],
                "race": "undefined",
                "gender": "undefined",
                "appearance": "undefined",
                "backstory": "undefined"
            }
            for f in self.fields:
                if f not in self.bios[gid][t_name]:
                    self.bios[gid][t_name][f] = ""
            await respond(msg, f"**ANALYSIS: created character {t_bio['name']}.**")
            self._save_bios()
        for field, value in t_bio.items():
            self.bios[gid][t_name][field] = value
        self._save_bios()
        await respond(msg, f"**AFFIRMATIVE. Character {t_bio['name']} updated.**")

    @Command("reloadbio",
             doc="Administrative function that reloads the bios from the file.",
             perms={"manage_messages"})
    async def _reloadbio(self, msg):
        try:
            with open(self.plugin_config.bio_file, "r", encoding="utf8") as f:
                self.bios = json.load(f)
        except FileNotFoundError:
            self.bios = {}
            with open(self.plugin_config.bio_file, "w", encoding="utf8") as f:
                f.write("{}")
        except json.decoder.JSONDecodeError:
            self.logger.exception("Could not decode bios.json! ", exc_info=True)
            raise CommandSyntaxError("Bios.json is not a valid JSON file.")
        await respond(msg, "**AFFIRMATIVE. Bios reloaded from file.**")

    # util commands

    def _initialize(self, gid):
        if gid not in self.plugin_config:
            self.plugin_config[gid] = DotDict(self.default_config["default"])
            self.config_manager.save_config()
        if gid not in self.bios:
            self.bios[gid] = {}

    def _print_bio(self, guild, name):
        gid = str(guild.id)
        if name in self.bios[gid]:
            t_embed = Embed(type="rich", colour=16711680)
            bio = self.bios[gid][name]
            t_role = find_role(guild, bio["race"])

            t_embed.title = bio["name"]
            if t_role and t_role.id in self.plugin_config[gid]["race_roles"]:
                t_embed.colour = t_role.colour

            t_s = "```\n"
            for i in range(1, 5):
                if bio.get(self.fields[i], ""):
                    t_s = f"{t_s}{self.fields[i].capitalize().ljust(7)}: {bio[self.fields[i]]}\n"
            t_s += "```\n"
            if bio.get("theme", ""):
                t_s = f"{t_s} [Theme song.]({bio['theme']})\n"
            if bio.get("link", ""):
                t_s = f"{t_s} [Extended bio.]({bio['link']})"

            t_embed.description = t_s

            if bio.get("image", ""):
                t_embed.set_image(url=bio["image"])

            for field in self.fields[8:]:
                if bio.get(field, ""):
                    t_embed.add_field(name=field.capitalize(), value=bio[field])

            t_member = guild.get_member(bio["author"])

            t_embed.set_footer(text=f"Character belonging to {t_member.display_name}", icon_url=t_member.avatar_url)
            return t_embed
        else:
            return None

    def _save_bios(self):
        with open(self.plugin_config.bio_file, "w", encoding="utf8") as f:
            json.dump(self.bios, f, indent=2, ensure_ascii=False)
