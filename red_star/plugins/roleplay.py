from __future__ import annotations
import re
import json
import shlex
import discord
from red_star.rs_errors import CommandSyntaxError, UserPermissionError
from red_star.rs_utils import respond, find_role, find_user, split_message, decode_json, RSArgumentParser
from red_star.command_dispatcher import Command
from red_star.plugin_manager import BasePlugin
from io import BytesIO
from dataclasses import dataclass, asdict


class Roleplay(BasePlugin):
    name = "roleplay"
    version = "1.2"
    author = "GTG3000"

    default_config = {
        "allow_race_requesting": False,
        "race_roles": [],
        "pinned_bios": {},
        "pinned_bios_channel": False
    }

    @dataclass
    class Bio:
        author: int
        name: str
        race: str
        gender: str
        appearance: str
        backstory: str
        height: str
        age: str
        theme: str
        link: str
        image: str
        equipment: str
        skills: str
        personality: str
        interests: str

        fields = ["author", "name", "race", "gender", "height", "age", "theme", "link", "image", "appearance",
                  "equipment", "skills", "personality", "backstory", "interests"]
        mandatory_fields = ["name", "race", "gender", "appearance", "backstory"]

        lim_64 = ["race", "gender", "height", "age", "name"]

        def set(self, field: str, value: str = None):
            _field = field.lower()
            if _field not in self.fields:
                raise KeyError(f"{_field} is not a valid field.")
            if value:
                if len(value) > (64 if _field in self.lim_64 else 1024):
                    raise ValueError('64' if _field in self.lim_64 else '1024')
                self.__dict__[_field] = self._name(value) if _field == 'name' else value
            else:
                self.__dict__[_field] = 'undefined' if _field in self.mandatory_fields else ''

        @classmethod
        def blank_bio(cls, author: int, name: str) -> Roleplay.Bio:
            new_bio_dict = dict(zip(cls.fields, [''] * 15))
            for field in cls.mandatory_fields:
                new_bio_dict[field] = 'undefined'

            new_bio_dict['author'] = author
            new_bio_dict['name'] = cls._name(name)

            return cls(**new_bio_dict)

        @staticmethod
        def _name(name: str) -> str:
            """
            removes trailing/leading whitespace, limits whitespace between words to one space, removes newlines.
            :param name:
            :return:
            """
            clean = re.sub(r'\s+', ' ', re.sub(r'^\s+|\s+$|\n|\r', '', name))
            if not clean:
                raise CommandSyntaxError('Empty name provided.')
            return clean[:64]

        def embed(self, guild: discord.Guild, roles: [discord.Role]) -> discord.Embed:
            """
            Generates a pretty discord embed of this role.
            :param guild: guild that the bio belongs to, for member and role searching
            :param roles: list of accepted race roles
            :return:
            """
            t_embed = discord.Embed(type="rich", colour=16711680)

            role = find_role(guild, self.race)

            t_embed.title = self.name

            if role and role.id in roles:
                t_embed.colour = role.colour

            t_member = guild.get_member(self.author)
            if t_member:
                t_embed.set_footer(text=f"Character belonging to {t_member.display_name}",
                                   icon_url=t_member.avatar.url)

            t_embed.description = "```\n" + \
                                  '\n'.join([f"{f.capitalize():<7}: {self.__dict__[f]}" for f in self.fields[2:6] if
                                             self.__dict__[f]]) \
                                  + "```\n" + \
                                  (f"[Theme song.]({self.theme})\n" if self.theme else '') + \
                                  (f"[Extended bio.]({self.link})\n" if self.link else '') + \
                                  (f"Owner: {t_member.mention}" if t_member else '')

            if self.image:
                t_embed.set_image(url=self.image)

            for field in (f for f in self.fields[9:] if self.__dict__[f]):
                t_embed.add_field(name=field.capitalize(), value=self.__dict__[field], inline=False)

            return t_embed

        def as_dict(self) -> dict:
            return {"__classhint__": "bio", **asdict(self)}

    def storage_load_args(self):
        return {"object_hook": self._load_bio}

    def storage_save_args(self):
        return {"default": lambda obj: obj.as_dict(), "indent": 2, "ensure_ascii": False}

    def _load_bio(self, obj: dict) -> Roleplay.Bio | dict:
        if obj.pop('__classhint__', None) == 'bio':
            return self.Bio(**obj)
        else:
            obj_set = {*obj}
            if obj_set.issubset(self.Bio.fields) and len(obj_set) >= 5:
                return self.Bio(**{**dict(zip(self.Bio.fields, [''] * 15)), **obj})
            else:
                return obj

    async def activate(self):
        self._port_old_storage()
        self.bios = self.storage.setdefault("bios", {})

    def _port_old_storage(self):
        old_storage_path = self.config_manager.config_path / "bios.json"
        if old_storage_path.exists():
            with old_storage_path.open(encoding="utf-8") as fp:
                old_storage = json.load(fp, **self.storage_load_args())
            for guild_id, data in old_storage.items():
                old_storage_guild = old_storage.get(guild_id, {})
                try:
                    guild_current_storage = self.config_manager.storage_files[guild_id][self.name]
                except KeyError:
                    self.logger.warn(f"Server with ID {guild_id} not found! Is the bot still in this server?\n"
                                     f"Skipping conversion of this server's bio storage...")
                    continue
                old_storage_guild.update(guild_current_storage.contents)
                guild_current_storage.contents = old_storage_guild
                guild_current_storage.save()
                guild_current_storage.load()
            old_storage_path = old_storage_path.replace(old_storage_path.with_suffix(".json.old"))
            self.logger.info(f"Old bio storage converted to new format. "
                             f"Old data now located at {old_storage_path} - you may delete this file.")

    @Command("RaceRole",
             doc="-a/--add   : Adds specified roles to the list of allowed race roles.\n"
                 "-r/--remove: Removes speficied roles from the list.\n"
                 "Calling it without any arguments prints the list.",
             syntax="[-a/--add (role mentions/ids/names)] [-r/--remove (role mentions/ids/names)]",
             perms={"manage_messages"},
             category="role_play")
    async def _racerole(self, msg: discord.Message):
        parser = RSArgumentParser()
        parser.add_argument("command")
        parser.add_argument("-a", "--add", default=[], nargs='+')
        parser.add_argument("-r", "--remove", default=[], nargs='+')

        args = parser.parse_args(shlex.split(msg.content))

        if not (args['add'] or args['remove']):
            approved_roles = "\n".join(x.name for x in msg.guild.roles if x.id in self.config["race_roles"])
            for split_msg in split_message(f"**ANALYSIS: Currently approved race roles:**```\n{approved_roles}```"):
                await respond(msg, split_msg)
        else:
            args['add'] = [r for r in [find_role(msg.guild, r) for r in args['add']] if r]
            args['remove'] = [r for r in [find_role(msg.guild, r) for r in args['remove']] if r]

            # for nice output
            added_roles = []
            removed_roles = []

            for role in args['add']:
                if role.id not in self.config["race_roles"]:
                    added_roles.append(role.name)
                    self.config["race_roles"].append(role.id)
            for role in args['remove']:
                if role.id in self.config["race_roles"]:
                    removed_roles.append(role.name)
                    self.config["race_roles"].remove(role.id)

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

    @Command("GetRaceRole",
             doc="Allows the user to request one of the approved race roles for themselves.",
             syntax="(role)",
             category="role_play")
    async def _getracerole(self, msg: discord.Message):
        if not self.config.get("allow_race_requesting", False):
            return
        args = msg.content.split(" ", 1)
        preexisting_roles = []
        for role in msg.author.roles:
            if role.id in self.config["race_roles"]:
                preexisting_roles.append(role)
        await msg.author.remove_roles(*preexisting_roles)
        if len(args) < 2:
            await respond(msg, "**AFFIRMATIVE. Race role removed.**")
        else:
            role = find_role(msg.guild, args[1])
            if role:
                if role.id in self.config["race_roles"]:
                    await msg.author.add_roles(role)
                    await respond(msg, f"**AFFIRMATIVE. Race role {role.name} granted.**")
                else:
                    raise CommandSyntaxError("Not an approved race role.")
            else:
                raise CommandSyntaxError("Not a role or role not found.")

    @Command("ListRaceRoles",
             doc="Lists all approved race roles.",
             category="role_play")
    async def _listraceroles(self, msg: discord.Message):
        if not self.config.get("allow_race_requesting", False):
            return
        approved_roles = "\n".join(x.name for x in msg.guild.roles if x.id in self.config["race_roles"])
        for split_msg in split_message(f"**ANALYSIS: Currently approved race roles:**```\n{approved_roles}```"):
            await respond(msg, split_msg)

    @Command("ListBios",
             doc="Lists all available bios in the database.",
             syntax="[user]",
             category="role_play")
    async def _listbio(self, msg: discord.Message):
        args = msg.content.split(" ", 1)
        if len(args) > 1:
            owner = find_user(msg.guild, args[1])
            if owner:
                result = "\n".join(f"{k[:16]:<16} : {v.name}" for k, v in self.bios.items()
                                   if v.author == owner.id)
                for split_msg in split_message(f"**ANALYSIS: User {owner.display_name} has following "
                                               f"characters:**```{result}```"):
                    await respond(msg, split_msg)
            else:
                raise CommandSyntaxError("Not a user or user not found.")
        else:
            bios = "\n".join(f"{k[:16]:<16} : {v.name}" for k, v in self.bios.items())
            for split_msg in split_message(f"**ANALYSIS: Following character bios found:**```\n{bios}```"):
                await respond(msg, split_msg)

    @Command("Bio",
             doc="Prints, edits, creates, destroys, renames or dumps character bios.\n"
                 "Each character name must be unique and will be stripped of excessive whitespace.\n"
                 "-s/--set   : changes a specified field to a specified value:\n"
                 "  Fields   : name/race/gender/height/age: limit 64 characters."
                 "theme/link: must be viable http(s) url. "
                 "  appearance/equipment/skills/personality/backstory/interests: limit 1024 characters.\n"
                 "  Setting 'race' to the same name as a registered character role will fetch the colour.\n"
                 "-c/--create: creates a new bio with the given name.\n"
                 "-d/--dump  : creates and uploads a JSON file of the bio, for backup and offline editing.\n"
                 "-r/--rename: changes the name by which the bio is referenced to a new one.\n"
                 "--delete   : deletes the bio."
                 "Be aware that the total length of the bio must not exceed 6000 characters.",
             syntax="(name) [-s/--set (field) [value]] [-c/--create] [-d/--dump] [-r/--rename (new name)] [--delete]",
             category="role_play",
             run_anywhere=True,
             optional_perms={"edit_others": {"manage_messages"}})
    async def _bio(self, msg: discord.Message):
        parser = RSArgumentParser()
        parser.add_argument('command')
        parser.add_argument('name', default=[], nargs="*")
        parser.add_argument('-s', '--set', default=[], nargs="+")
        parser.add_argument('-c', '--create', action='store_true')
        parser.add_argument('-d', '--dump', action='store_true')
        parser.add_argument('--delete', action='store_true')  # doesn't get a short flag for safety
        parser.add_argument('-r', '--rename', nargs="+")

        try:
            args = shlex.split(msg.clean_content)
        except ValueError as e:
            self.logger.warning("Unable to split {data.content}. {e}")
            raise CommandSyntaxError(e)

        args = parser.parse_args(args)

        if args['name']:
            args['name'] = self.Bio._name(' '.join(args['name']))
            char = args['name'].lower()
        else:
            raise CommandSyntaxError("No bio id given.")

        if char not in self.bios and not args['create']:
            raise CommandSyntaxError(f'No such character: {args["name"]}.')

        # manipulate the specified bio
        if args['set'] or args['create'] or args['delete'] or args['rename'] or args['dump']:
            # creating a bio with using the given character name
            if args['create']:
                if char in self.bios:
                    raise CommandSyntaxError(f"Character {args['name']} already exists.")
                else:
                    self.bios[char] = self.Bio.blank_bio(msg.author.id, args['name'])
                    await respond(msg, f"**AFFIRMATIVE. ANALYSIS: Created character {args['name']}.**")

            if not (self.bios[char].author == msg.author.id or args['dump'] or
                    self._bio.perms.check_optional_permissions("edit_others", msg.author, msg.channel)):
                raise UserPermissionError("Character belongs to another user.")

            # setting one field of the bio to a given value
            if args['set']:
                field, value = args['set'][0], ' '.join(args['set'][1:])
                try:
                    self.bios[char].set(field, value)
                    await self._update_bio_pin(msg.guild, char)
                    await respond(msg, f"**AFFIRMATIVE. {field.capitalize()} {'' if value else 're'}set.**")
                except ValueError as e:
                    raise CommandSyntaxError(f"Exceeded length of field {field.capitalize()}: {e} characters.")
                except KeyError as e:
                    raise CommandSyntaxError(e)

            self.storage_file.save()

            # compiling the bio into a json file for storage and editing
            if args['dump']:
                t_bio = asdict(self.bios[char])
                del t_bio['author']
                t_bio['fullname'] = t_bio['name']
                t_bio['name'] = char
                t_bio = json.dumps(t_bio, indent=2, ensure_ascii=False)
                async with msg.channel.typing():
                    await respond(msg, "**AFFIRMATIVE. Completed file upload.**",
                                  file=discord.File(BytesIO(bytes(t_bio, encoding="utf-8")), filename=char + ".json"))

            # changing the bio key in the storage dict, effectively renaming it
            if args['rename']:
                new_name = self.Bio._name(' '.join(args['rename'])).lower()
                if new_name in self.bios:
                    raise UserPermissionError(f"Character {new_name} already exists")

                self.bios[new_name] = self.bios[char]
                del self.bios[char]

                if char in self.config['pinned_bios']:
                    self.config['pinned_bios'][new_name] = self.config['pinned_bios'][char]
                    del self.config['pinned_bios'][char]

                await respond(msg, f"**AFFIRMATIVE. Character {char} can now be accessed as {new_name}.**")
                char = new_name
                self.storage_file.save()

            # deletes the specified bio.
            if args['delete']:
                del self.bios[char]
                if char in self.config['pinned_bios']:
                    bio_msg = await msg.guild.get_channel(self.config['pinned_bios_channel'])\
                        .fetch_message(self.config['pinned_bios'][char])
                    await bio_msg.delete()  # deleting the actual record happens in on_message_delete
                self.storage_file.save()
                await respond(msg, f"**AFFIRMATIVE. Character {char} has been deleted.**")

        else:
            await respond(msg, None,
                          embed=self.bios[char].embed(msg.guild, self.config['race_roles']))

    @Command("UploadBio",
             doc="Parses a JSON file or a JSON codeblock to update/create character bios.\n"
                 "See output of ",
             syntax="(attach file to the message, or put JSON contents into a code block following the command)",
             category="role_play")
    async def _uploadbio(self, msg: discord.Message):
        if msg.attachments:
            # there is a file uploaded with the message, grab and decode it.
            _file = BytesIO()

            await msg.attachments[0].save(_file)
            try:
                data = decode_json(_file.getvalue())
            except ValueError as e:
                self.logger.exception("Could not decode uploaded bio file!", exc_info=True)
                raise CommandSyntaxError(e)
            except Exception as e:
                raise CommandSyntaxError(f"Not a valid JSON file: {e}")
        else:
            # no file, let's see if user given us a code block.
            args = msg.content.split(None, 1)
            if len(args) == 1:
                raise CommandSyntaxError("File or code block required.")

            # This regexp searches for something in a codeblock, inside {} inclusive.
            # There can be any amount of space between the codeblock ticks and the figure brackets.
            data = re.search("```.*({.+}).*```", args[1], re.DOTALL)

            if data:
                try:
                    data = json.loads(data.group(1))
                except ValueError as e:
                    raise CommandSyntaxError(f"Not a valid JSON string: {e}")
            else:
                raise CommandSyntaxError("Not a valid JSON code block.")

        if "name" not in data:
            raise CommandSyntaxError("Not a valid character file: No name.")

        name = self.Bio._name(data['name']).lower()

        # 'fullname' key only exists for users' sake and must be dealt with specially
        try:
            data['name'] = data['fullname'] or data['name']
            del data['fullname']
        except KeyError:
            pass

        if name in self.bios and self.bios[name].author != msg.author.id:
            raise UserPermissionError("Character belongs to another user.")

        new_char = self.Bio.blank_bio(msg.author.id, data['name'])

        # the Bio.set() method includes all the checks for length that we may need, just gotta let it do its thing.
        for field, value in data.items():
            try:
                new_char.set(field, value)
            except ValueError as e:
                raise CommandSyntaxError(f"Exceeded length of field {field.capitalize()}: {e} characters.")
            except KeyError:
                continue

        # just for nicer output
        old = name in self.bios

        self.bios[name] = new_char
        self.storage_file.save()
        await self._update_bio_pin(msg.guild, name)

        await respond(msg, f"**AFFIRMATIVE. Character {new_char.name} was {'updated' if old else 'created'}.**")

    @Command("ReloadBios", "ReloadBio",
             doc="Administrative function that reloads the bios from the file.",
             category="role_play",
             bot_maintainers_only=True)
    async def _reloadbio(self, msg: discord.Message):
        self.storage_file.load()
        self.bios = self.storage["bios"]
        await respond(msg, "**AFFIRMATIVE. Bios reloaded from file.**")

    @Command("PinBio",
             doc="Generates an automatically updated bio post.\n"
                 "All such messages must be in the same channel, which is set by the first message.\n"
                 "To unpin a bio, simply delete the message.",
             syntax="(character)",
             perms={"manage_messages"},
             category="role_play",
             run_anywhere=True,
             delcall=True)
    async def _pinbio(self, msg):
        g_cfg = self.config

        if g_cfg.setdefault('pinned_bios_channel', msg.channel.id) != msg.channel.id:
            if g_cfg['pinned_bios']:
                raise CommandSyntaxError(f"Autopinned bios must all be in channel "
                                         f"<#{self.config['pinned_bios_channel']}>.")
            else:
                g_cfg['pinned_bios_channel'] = msg.channel.id

        try:
            char = self.Bio._name(msg.clean_content.split(None, 1)[1])
        except IndexError:
            raise CommandSyntaxError

        if char not in self.bios:
            raise CommandSyntaxError(f"No bio with id {char}.")

        if char in g_cfg.setdefault('pinned_bios', {}):
            raise CommandSyntaxError(f"Bio with id {char} is already pinned.")

        message = await respond(msg, None, embed=self.bios[char].embed(msg.guild, g_cfg['race_roles']))

        g_cfg['pinned_bios'][char] = message.id

    # util commands

    async def _update_bio_pin(self, guild: discord.Guild, char: str):
        g_cfg = self.config
        if char in g_cfg['pinned_bios']:
            bio_msg = await guild.get_channel(g_cfg['pinned_bios_channel']).fetch_message(g_cfg['pinned_bios'][char])
            await bio_msg.edit(embed=self.bios[char].embed(guild, g_cfg['race_roles']))

    async def on_message_delete(self, msg: discord.Message):
        g_cfg = self.config

        if 'pinned_bios' in g_cfg and msg.id in g_cfg['pinned_bios'].values():
            key = [k for k, v in g_cfg['pinned_bios'].items() if v == msg.id].pop()
            del g_cfg['pinned_bios'][key]
