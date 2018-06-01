import re
import json
import shlex
from random import randint
from rs_errors import CommandSyntaxError, UserPermissionError
from rs_utils import respond, DotDict, find_role, find_user, split_output, decode_json
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

    @Command("Roll",
             doc="Rolls a specified amount of specified dice with specified bonus and advantage/disadvantage",
             syntax="[number]D(die/F)[+/-bonus][A/D]",
             category="role_play",
             run_anywhere=True)
    async def _roll(self, msg):
        args = msg.content.split(" ", 1)
        if len(args) < 2:
            raise CommandSyntaxError("Requires one argument.")
        dice_data = re.search(r"(\d+|)d(\d+|f)(\+\d+|-\d+|)(a|d|)", args[1].lower())
        if dice_data:
            # checking for optional dice number
            if dice_data.group(1):
                num_dice = min(max(int(dice_data.group(1)), 1), 10000)
            else:
                num_dice = 1
            # support for fate dice. And probably some other kind of dice? Added roll_function to keep it streamlined
            if dice_data.group(2) != 'f':
                die_sides = min(max(int(dice_data.group(2)), 2), 10000)
                def roll_function(): return randint(1, die_sides)
            else:
                die_sides = "F"
                def roll_function(): return randint(1, 3) - 2
            if dice_data.group(3):
                modif = int(dice_data.group(3))
                modif_str = f" with a {'+' if modif > 0 else ''}{modif} modifier"
            else:
                modif = 0
                modif_str = ""
            t_adv = dice_data.group(4)
            dice_set_a = [roll_function() for _ in range(num_dice)]
            dice_set_b = [roll_function() for _ in range(num_dice)]
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

    @Command("RaceRole",
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

    @Command("GetRaceRole",
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

    @Command("ListRaceRoles",
             doc="Lists all approved race roles.",
             category="role_play")
    async def _listraceroles(self, msg):
        if not self.plugin_config.get("allow_race_requesting", False):
            return
        gid = str(msg.guild.id)
        self._initialize(gid)
        await split_output(msg, "**ANALYSIS: Currently approved race roles:**",
                           [x.name for x in msg.guild.roles if x.id in self.plugin_config[gid]["race_roles"]])

    @Command("ListBios",
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
                t_bio_list = [f"{k[:16].ljust(16)} : {v['name']}" for k, v in self.bios[gid].items()
                              if v.get("author", 0) == t_member.id]
                await split_output(msg, f"**ANALYSIS: User {t_member.display_name} has following characters:**",
                                   t_bio_list)
            else:
                raise CommandSyntaxError("Not a user or user not found.")
        else:
            await split_output(msg, "**ANALYSIS: Following character bios found:**",
                               [f"{k[:16].ljust(16)} : {v['name']}" for k, v in self.bios[gid].items()])

    @Command("Bio",
             doc="Prints the specified character bio.",
             syntax="(name)",
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
            args = " ".join(shlex.split(msg.clean_content)[1:])
        except ValueError as e:
            self.logger.warning("Unable to split {data.content}. {e}")
            raise CommandSyntaxError(e)
        except IndexError:
            raise CommandSyntaxError("Bio name required.")

        t_name = self._sanitise_name(args.lower())

        if t_name in self.bios[gid]:
            await respond(msg, None, embed=self._print_bio(msg.guild, t_name))
        else:
            raise CommandSyntaxError(f"No such character: {args}.")

    @Command("EditBio",
             doc="Edits the specified bio field, or creates the bio if it doesn't exist.",
             syntax="(bio) (field) (value or clear)",
             category="role_play")
    async def _editbio(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        try:
            args = shlex.split(msg.clean_content)
        except ValueError as e:
            self.logger.warning("Unable to split {data.content}. {e}")
            raise CommandSyntaxError(e)

        if len(args) < 4:
            raise CommandSyntaxError("Three arguments required.")

        t_name = self._sanitise_name(args[1].lower())
        if t_name in self.bios[gid]:
            if self.bios[gid][t_name].get("author", 0) != msg.author.id:
                raise UserPermissionError("Character belongs to other user.")
        else:
            if len(t_name) > 64:
                raise CommandSyntaxError("Character name too long. Maximum length is 64 characters.")
            self.bios[gid][t_name] = {
                "author": msg.author.id,
                "name": self._sanitise_name(args[1]),
                "race": "undefined",
                "gender": "undefined",
                "appearance": "undefined",
                "backstory": "undefined"
            }
            for f in self.fields:
                if f not in self.bios[gid][t_name]:
                    self.bios[gid][t_name][f] = ""
            await respond(msg, f"**ANALYSIS: created character {self._sanitise_name(args[1])}.**")
        t_field = args[2].lower()
        if t_field in self.fields:
            bio = self.bios[gid][t_name]
            if args[3].lower() == "clear":
                if t_field in self.mandatory_fields:
                    bio[t_field] = "undefined"
                else:
                    bio[t_field] = ""
                await respond(msg, f"**AFFIRMATIVE. {t_field.capitalize()} cleared.**")
            else:
                t_value = " ".join(args[3:])
                if t_field in ["race", "gender", "height", "age", "name"]:
                    if t_field == "name":
                        t_value = self._sanitise_name(t_value)
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
            raise CommandSyntaxError(f"Invalid field. Available fields: {', '.join(self.fields[1:])}.")
        self._save_bios()

    @Command("DeleteBio",
             doc="Deletes the specified bio. Requires you to be the author or have Manage Messages permission.",
             syntax="(bio)",
             category="role_play")
    async def _deletebio(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        try:
            args = " ".join(shlex.split(msg.clean_content)[1:])
        except ValueError as e:
            self.logger.warning("Unable to split {data.content}. {e}")
            raise CommandSyntaxError(e)

        if len(args) < 2:
            raise CommandSyntaxError("Bio name required.")

        t_name = self._sanitise_name(args.lower())
        if t_name in self.bios[gid]:
            if self.bios[gid][t_name].get("author", 0) == msg.author.id or \
                    msg.author.permissions_in(msg.channel).manage_messages or \
                    msg.author.id in self.config_manager.config.get("bot_maintainers", []):
                del self.bios[gid][t_name]
                await respond(msg, f"**AFFIRMATIVE. Character bio {t_name} was deleted.**")
            else:
                raise UserPermissionError("Character belongs to other user.")
        else:
            raise CommandSyntaxError(f"No such character: {t_name}.")
        self._save_bios()

    @Command("DumpBio",
             doc="Dumps the specified bio into a JSON file.",
             syntax="(bio)",
             category="role_play")
    async def _dumpbio(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        try:
            args = " ".join(shlex.split(msg.clean_content)[1:])
        except ValueError as e:
            self.logger.warning("Unable to split {data.content}. {e}")
            raise CommandSyntaxError(e)

        if len(args) < 2:
            raise CommandSyntaxError("Bio name required.")

        t_name = self._sanitise_name(args.lower())
        if t_name in self.bios[gid]:
            t_bio = self.bios[gid][t_name].copy()
            del t_bio["author"]
            t_bio["fullname"] = t_bio["name"]
            t_bio["name"] = t_name
            t_bio = json.dumps(t_bio, indent=2, ensure_ascii=False)
            async with msg.channel.typing():
                await respond(msg, "**AFFIRMATIVE. Completed file upload.**",
                              file=File(BytesIO(bytes(t_bio, encoding="utf-8")), filename=t_name + ".json"))
        else:
            raise CommandSyntaxError(f"No such character: {args[1]}.")

    @Command("RenameBio",
             doc="Renames the specified bio to the specified new name. Requires you to be the author.",
             syntax="(bio) (new name)",
             category="role_play")
    async def _renamebio(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        try:
            args = shlex.split(msg.clean_content)
        except ValueError as e:
            self.logger.warning("Unable to split {data.content}. {e}")
            raise CommandSyntaxError(e)

        if len(args) < 3:
            raise CommandSyntaxError("Bio name and new name required.")

        t_name = self._sanitise_name(args[1].lower())
        new_name = self._sanitise_name(args[2].lower())
        if t_name in self.bios[gid]:
            if self.bios[gid][t_name].get("author", 0) != msg.author.id:
                raise UserPermissionError("Character belongs to other user.")
        else:
            raise CommandSyntaxError(f"No such character: {t_name}.")
        if new_name in self.bios[gid]:
            raise CommandSyntaxError("Character ID already taken.")
        self.bios[gid][new_name] = self.bios[gid][t_name]
        del self.bios[gid][t_name]
        await respond(msg, f"**AFFIRMATIVE. Character bio {t_name} can now be accessed as {new_name}.**")

    @Command("UploadBio",
             doc="Parses a json file to update/create character bios.\n"
                 "See output of !bio (charname) dump for more details on file formatting.",
             syntax="(attach the file to the message, no arguments required)",
             category="role_play")
    async def _uploadbio(self, msg):
        """
        Takes a file or a code block and parses it as json, checking the field limits.
        """
        gid = str(msg.guild.id)
        self._initialize(gid)
        if msg.attachments:
            t_file = BytesIO()
            await msg.attachments[0].save(t_file)
            try:
                t_data = decode_json(t_file.getvalue())
            except ValueError as e:
                self.logger.exception("Could not decode bios.json! ", exc_info=True)
                raise CommandSyntaxError(e)
            except Exception as e:
                raise CommandSyntaxError(f"Not a valid JSON file: {e}")
        else:
            args = re.split(r"\s+", msg.content, 1)
            if len(args) == 1:
                raise CommandSyntaxError("File or code block required")
            t_search = re.search("```.*({.+}).*```", args[1], re.DOTALL)
            if t_search:
                try:
                    t_data = json.loads(t_search.group(1))
                except ValueError as e:
                    raise CommandSyntaxError(f"Not a valid JSON string. {e}")
            else:
                raise CommandSyntaxError("Not valid JSON code block.")

        if "name" not in t_data:
            raise CommandSyntaxError("Not a valid character file: No name.")

        t_data["name"] = self._sanitise_name(t_data["name"])

        t_bio = {}

        for field in [*self.fields, "fullname"]:  # don't want "fullname" to come up in the list of all possible fields
            t_field = t_data.get(field, "")
            if t_field:
                t_len = len(t_field)
                if field in ["name", "fullname", "race", "gender", "height", "age"] and t_len > 64:
                    raise CommandSyntaxError(f"Not a valid character file: field {field} too long (max 64 chars).")
                elif field in ["link", "theme"] and t_len > 256:
                    raise CommandSyntaxError(f"Not a valid character file: field {field} too long (max 256 chars).")
                elif t_len > 1024:
                    raise CommandSyntaxError(f"Not a valid character file: field {field} too long (max 1024 chars).")
                t_bio[field] = t_field

        t_name = t_bio["name"].lower()
        t_name_storage = t_bio["name"]
        if "fullname" in t_bio:
            t_bio["name"] = self._sanitise_name(t_bio["fullname"])
            del t_bio["fullname"]
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
            await respond(msg, f"**ANALYSIS: created character {t_name_storage}.**")
            self._save_bios()
        for field, value in t_bio.items():
            self.bios[gid][t_name][field] = value
        self._save_bios()
        await respond(msg, f"**AFFIRMATIVE. Character {t_name_storage} updated.**")

    @Command("ReloadBios",
             doc="Administrative function that reloads the bios from the file.",
             category="role_play",
             bot_maintainers_only=True)
    async def _reloadbios(self, msg):
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

            t_member = guild.get_member(bio["author"])
            if t_member:
                t_embed.set_footer(text=f"Character belonging to {t_member.display_name}",
                                   icon_url=t_member.avatar_url)

            t_s = "```\n"
            for i in range(1, 5):
                if bio.get(self.fields[i], ""):
                    t_s = f"{t_s}{self.fields[i].capitalize().ljust(7)}: {bio[self.fields[i]]}\n"
            t_s += "```\n"
            if bio.get("theme", ""):
                t_s = f"{t_s}[Theme song.]({bio['theme']})\n"
            if bio.get("link", ""):
                t_s = f"{t_s}[Extended bio.]({bio['link']})\n"

            if t_member:
                t_s = f"{t_s}Owner: {t_member.mention}"

            t_embed.description = t_s

            if bio.get("image", ""):
                t_embed.set_image(url=bio["image"])

            for field in self.fields[8:]:
                if bio.get(field, ""):
                    t_embed.add_field(name=field.capitalize(), value=bio[field])

            return t_embed
        else:
            return None

    def _save_bios(self):
        with open(self.plugin_config.bio_file, "w", encoding="utf8") as f:
            json.dump(self.bios, f, indent=2, ensure_ascii=False)

    def _sanitise_name(self, name):
        # remove leading/trailing whitespace, inner whitespace limited to one character, no newlines
        # SPECIALISED FUNCTION, meant to handle the empty names
        name = re.sub(r"^\s+|\s+$|\n|\r", "", name)
        name = re.sub(r"\s{2,}", " ", name)
        if name:
            return name
        else:
            raise CommandSyntaxError("Empty name provided.")
