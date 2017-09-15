import re
import json
import shlex
from random import randint
from rs_errors import CommandSyntaxError, UserPermissionError
from rs_utils import respond, Command, DotDict, find_role, is_positive
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
        """
        Roll a specified die with a specified bonus and advantage
        :param msg:
        :return:
        """

        args = msg.content.split(" ", 1)
        if len(args) < 2:
            raise CommandSyntaxError("Needs an argument, dumbass.")
        d_pattern = re.compile("(\d+|)d(\d+)(\+\d+|-\d+|)(a|d|)")
        d_data = d_pattern.search(args[1].lower())
        if d_data:
            if d_data.group(1):
                t_num = min(max(int(d_data.group(1)), 1), 10000)
            else:
                t_num = 1
            t_die = min(max(int(d_data.group(2)), 2), 10000)
            if d_data.group(3):
                t_bonus = int(d_data.group(3))
                t_b = f" with a {t_bonus} modifier"
            else:
                t_bonus = 0
                t_b = ""
            t_adv = d_data.group(4)
            if t_adv == 'a':
                t_s = "an advantageous"
                t_1 = t_2 = 0
                t_s1 = t_s2 = ""
                for i in range(t_num):
                    t_r = randint(1, t_die)
                    t_1 += t_r
                    t_s1 += f"[{t_r}] "
                    t_r = randint(1, t_die)
                    t_2 += t_r
                    t_s2 += f"[{t_r}] "
                if t_1 > t_2:
                    t_res = t_1 + t_bonus
                    t_r_s = t_s1
                else:
                    t_res = t_2 + t_bonus
                    t_r_s = t_s2
            elif t_adv == 'd':
                t_s = "a disadvantageous"
                t_1 = t_2 = 0
                t_s1 = t_s2 = ""
                for i in range(t_num):
                    t_r = randint(1, t_die)
                    t_1 += t_r
                    t_s1 += f"[{t_r}] "
                    t_r = randint(1, t_die)
                    t_2 += t_r
                    t_s2 += f"[{t_r}] "
                if t_1 < t_2:
                    t_res = t_1 + t_bonus
                    t_r_s = t_s1
                else:
                    t_res = t_2 + t_bonus
                    t_r_s = t_s2
            else:
                t_s = "a"
                t_res = 0
                t_r_s = ""
                for i in range(t_num):
                    t_r = randint(1, t_die)
                    t_res += t_r
                    t_r_s += f"[{t_r}] "

            if t_num > 1:
                t_r_s = f"\n**ANALYSIS: Rolled dice:** `{t_r_s}`"
            else:
                t_r_s = ""

            await respond(msg,
                          f"**ANALYSIS: {msg.author.display_name} has attempted {t_s} {t_num}D{t_die} roll{t_b}, "
                          f"getting {t_res}.**{t_r_s}")

    @Command("racerole",
             doc="Adds or removes roles from the list of race roles that are searched by the bio command.",
             syntax="add/remove (role mentions)",
             perms={"manage_messages"},
             category="role_play")
    async def _racerole(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        args = msg.content.split()
        if len(args) < 2:
            t_r = "**ANALYSIS: Current race roles registered:**\n```\n"
            for t_role in msg.guild.roles:
                if t_role.id in self.plugin_config[gid]["race_roles"]:
                    t_s = f"{t_role.name}\n"
                    if len(t_r)+len(t_s) > 1997:
                        await respond(msg, t_r+"```")
                        t_r = t_s
                    else:
                        t_r += t_s
            await respond(msg, t_r+"```")
        else:
            if args[1].lower() == "add":
                if msg.role_mentions:
                    for role in msg.role_mentions:
                        if role.id not in self.plugin_config[gid]["race_roles"]:
                            self.plugin_config[gid]["race_roles"].append(role.id)
                    await respond(msg, "**AFFIRMATIVE. Roles added to race list.**")
                else:
                    raise CommandSyntaxError("No roles mentioned.")
            elif args[1].lower() == "remove":
                if msg.role_mentions:
                    for role in msg.role_mentions:
                        if role.id not in self.plugin_config[gid]["race_roles"]:
                            self.plugin_config[gid]["race_roles"].remove(role.id)
                    await respond(msg, "**AFFIRMATIVE. Roles removed from race list.**")
                else:
                    raise CommandSyntaxError("No roles mentioned.")
            else:
                raise CommandSyntaxError(f"Unsupported mode {args[1].lower()}.")

    @Command("bio",
             doc="Adds, edits, prints, dumps or deletes character bios.\n"
                 "Each character name must be unique.\n"
                 "Fields: race/gender/height/age: limit 64 characters. theme/link: must be viable http(s) url. "
                 "appearance/equipment/skills/personality/backstory/interests: limit 1024 characters.\n"
                 "Setting 'race' to the same name as a registered character role will fetch the colour.\n"
                 "Be aware that the total length of the bio must not exceed 6000 characters.",
             syntax="\nediting/creating : (name) set (field) [value]\n"
                    "printing : (name)\n"
                    "dumping : (name) dump\n"
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
            raise CommandSyntaxError("At least one argument required")

        t_name = args[1].lower()

        if len(args) == 2:
            if t_name in self.bios[gid]:
                await respond(msg, None, embed=self._print_bio(msg.guild, t_name))
            else:
                raise CommandSyntaxError(f"No such character {args[1]}")
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
                    raise CommandSyntaxError(f"No such character {args[1]}")
                self._save_bios()
            elif args[2].lower() == "dump":
                if t_name in self.bios[gid]:
                    t_bio = self.bios[gid][t_name]
                    del t_bio["author"]
                    t_bio = json.dumps(t_bio, indent=2, ensure_ascii=False)
                    async with msg.channel.typing():
                        await respond(msg, "**AFFIRMATIVE. Completed file upload.**",
                                      file=File(BytesIO(bytes(t_bio, encoding="utf-8")), filename=t_name+".json"))
                else:
                    raise CommandSyntaxError(f"No such character {args[1]}")

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
                    if t_field in ["race", "gender", "height", "age"]:
                        if len(args[4]) > 64:
                            raise CommandSyntaxError(f"{t_field.capitalize()} too long. "
                                                     f"Maximum length is 64 characters.")
                        bio[t_field] = args[4]
                        await respond(msg, f"**AFFIRMATIVE. {t_field.capitalize()} set.**")
                    else:
                        if len(args[4]) > 1024:
                            raise CommandSyntaxError(f"{t_field.capitalize()} too long. "
                                                     f"Maximum length is 64 characters.")
                        bio[t_field] = args[4]
                        await respond(msg, f"**AFFIRMATIVE. {t_field.capitalize()} set.**")
            elif t_field not in self.fields:
                raise CommandSyntaxError(f"Available fields: {', '.join(self.fields)}")
            self._save_bios()

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
