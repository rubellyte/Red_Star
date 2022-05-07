import datetime
import json
import re
import discord
from asyncio import sleep, create_task
from io import BytesIO
from os import remove, path
from red_star.plugin_manager import BasePlugin
from red_star.command_dispatcher import Command
from red_star.rs_errors import CommandSyntaxError, UserPermissionError, CustomCommandSyntaxError
from red_star.rs_utils import respond, find_user, decode_json, group_items
from .rs_lisp import lisp_eval, parse, reprint, standard_env, get_args
from dataclasses import dataclass, astuple
from subprocess import Popen, PIPE, TimeoutExpired
from sys import executable


@dataclass
class CCFileMetadata:
    owner: int
    size: int
    desc: str


# noinspection PyBroadException
class CustomCommands(BasePlugin):
    name = "custom_commands"
    version = "2.1"
    author = "GTG3000, medeor413"
    description = "A plugin that allows users to create custom commands using Red Star's " \
                  "custom RSLisp language dialect."
    default_config = {
        "default": {
            "cc_prefix": "!!",
            "cc_limit": 25
        },
        "rslisp_max_runtime": 5,
        "rslisp_minify": True,
        "cc_file_quota": 1024 * 1024,  # one megabyte
    }
    channel_categories = {"no_cc"}
    log_events = {"cc_event"}
    rpn_path = None

    async def activate(self):
        self.ccs = self.config_manager.get_plugin_config_file("ccs.json", json_save_args={'ensure_ascii': False})
        save_args = {'default': lambda o: astuple(o), 'ensure_ascii': False}
        load_args = {'object_pairs_hook': lambda obj: {k: CCFileMetadata(*v) for k, v in obj}}
        self.ccfdata = self.config_manager.get_plugin_config_file("cc_storage.json", json_save_args=save_args,
                                                                  json_load_args=load_args)
        self.ccfolder = self.client.storage_dir / "ccfiles"
        self.ccfolder.mkdir(parents=True, exist_ok=True)

        for rpn_exec in (directory / "rpn_executor.py" for directory in self.client.plugin_directories):
            if path.isfile(rpn_exec):
                self.rpn_path = rpn_exec
                break

        try:
            self.bans = self.ccs["bans"]
        except KeyError:
            self.bans = self.ccs["bans"] = {}

    # Event hooks

    async def on_message(self, msg: discord.Message):
        gid = str(msg.guild.id)
        self._initialize(gid)
        deco = self.plugin_config[gid]["cc_prefix"]
        if msg.author != self.client.user:
            cnt = msg.content
            if cnt.startswith(deco):
                if msg.author.id in self.bans[gid]["cc_use_ban"]:
                    try:
                        await msg.author.send(f"**WARNING: You are banned from usage of custom commands on this "
                                              f"server.**")
                    except discord.Forbidden:
                        pass
                    return
                elif self.channel_manager.channel_in_category(msg.guild, "no_cc", msg.channel):
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
                            if self.channel_manager.channel_in_category(msg.guild, t_cat, msg.channel):
                                break
                        else:
                            await self.plugin_manager.hook_event("on_log_event", msg.guild,
                                                                 f"**WARNING: Attempted CC use outside of it's "
                                                                 f"categories in {msg.channel.mention} by: "
                                                                 f"{msg.author}.**",
                                                                 log_type="cc_event")
                            return
                    await self.run_cc(cmd, msg)

    # Commands

    @Command("ReloadCCs",
             doc="Reloads custom commands from file.",
             category="custom_commands",
             bot_maintainers_only=True)
    async def _reloadccs(self, msg: discord.Message):
        self.ccs.reload()
        await respond(msg, "**AFFIRMATIVE. CCS reloaded.**")

    @Command("CreateCC", "NewCC",
             doc="Creates a custom command.\n"
                 "RSLisp Documentation: https://github.com/medeor413/Red_Star/wiki/Custom-Commands",
             syntax="(name) (content, in plain text or in an attached file)",
             category="custom_commands")
    async def _createcc(self, msg: discord.Message):
        gid = str(msg.guild.id)
        self._initialize(gid)
        if msg.author.id in self.bans[gid]["cc_create_ban"]:
            raise UserPermissionError("You are banned from creating custom commands.")
        if msg.attachments:
            fp = BytesIO()
            await msg.attachments[0].save(fp)
            args = msg.clean_content.split()
            name = args[1].lower() if len(args) > 1 else msg.attachments[0].filename.rsplit('.', 1)[0]
            content = fp.getvalue().decode()
        else:
            try:
                args = msg.clean_content.split(None, 2)[1:]
                name = args[0].lower()
            except IndexError:
                raise CommandSyntaxError("No name provided.")
            try:
                content = args[1]
            except IndexError:
                raise CommandSyntaxError("No content provided.")
        if gid not in self.ccs:
            self.ccs[gid] = {}
        if name in self.ccs[gid]:
            await respond(msg, f"**WARNING: Custom command {name} already exists.**")
        else:
            user_cc_count = len([True for cc in self.ccs[gid].values() if cc["author"] == msg.author.id])
            cc_limit = self.plugin_config[gid].get("cc_limit", 100)

            if msg.author.id not in self.config_manager.config.get("bot_maintainers", []) and not \
                    msg.channel.permissions_for(msg.author).manage_messages and user_cc_count >= cc_limit:
                raise UserPermissionError(f"Exceeded per-user custom command limit of {cc_limit}.")
            try:
                # check to see if there's something inside parenthesis floating in all the whitespace
                if not re.match(r"^\s*\(.*\)\s*$", content, re.DOTALL):
                    content = content.replace('"', '\\"')
                    content = f'"{content}"'
                parse(content)
            except Exception as err:
                await respond(msg, f"**WARNING: Custom command is invalid. Error: {err}**")
                return
            newcc = {
                "name": name,
                "content": reprint(parse(content)) if self.plugin_config['rslisp_minify'] else content,
                "author": msg.author.id,
                "date_created": datetime.datetime.now().strftime("%Y-%m-%d @ %H:%M:%S"),
                "last_edited": None,
                "locked": False,
                "restricted": [],
                "times_run": 0
            }
            self.ccs[gid][name] = newcc
            self.ccs.save()
            await respond(msg, f"**ANALYSIS: Custom command {name} created successfully.**")

    @Command("DumpCC",
             doc="Uploads the contents of the specified custom command as a text file.",
             syntax="(name)",
             category="custom_commands")
    async def _dumpcc(self, msg: discord.Message):
        gid = str(msg.guild.id)
        self._initialize(gid)
        if msg.author.id in self.bans[gid]["cc_create_ban"]:
            raise UserPermissionError("You are banned from editing custom commands.")
        try:
            name = msg.content.split(" ", 1)[1].lower()
        except IndexError:
            raise CommandSyntaxError("No name provided.")
        if name in self.ccs[gid]:
            async with msg.channel.typing():
                await respond(msg, "**AFFIRMATIVE. Completed file upload.**",
                              file=discord.File(BytesIO(bytes(self.ccs[gid][name]["content"], encoding="utf-8")),
                                                filename=name + ".lisp"))
        else:
            raise CommandSyntaxError(f"No such custom command {name}.")

    @Command("EditCC",
             doc="Edits a custom command you created.",
             syntax="(name) (content, in plain text or in an attached file)",
             category="custom_commands")
    async def _editcc(self, msg: discord.Message):
        gid = str(msg.guild.id)
        self._initialize(gid)
        if msg.author.id in self.bans[gid]["cc_create_ban"]:
            raise UserPermissionError("You are banned from editing custom commands.")
        if msg.attachments:
            fp = BytesIO()
            await msg.attachments[0].save(fp)
            try:
                name = msg.clean_content.split(None, 2)[1].lower()
            except IndexError:
                name = msg.attachments[0].filename.rsplit('.', 1)[0]
            content = fp.getvalue().decode()
        else:
            try:
                _, name, content = msg.clean_content.split(" ", 2)
            except ValueError:
                raise CommandSyntaxError
        if gid not in self.ccs:
            self.ccs[gid] = {}
        if name in self.ccs[gid]:
            cc_data = self.ccs[gid][name]
            if cc_data["author"] == msg.author.id or msg.author.guild_permissions.manage_messages:
                try:
                    parse(content)
                except Exception as err:
                    await respond(msg, f"**WARNING: Custom command is invalid. Error: {err}**")
                    return
                cc_data["content"] = reprint(parse(content)) if self.plugin_config['rslisp_minify'] else content
                cc_data["last_edited"] = datetime.datetime.now().strftime("%Y-%m-%d @ %H:%M:%S")
                self.ccs[gid][name] = cc_data
                self.ccs.save()
                await respond(msg, f"**ANALYSIS: Custom command {name} edited successfully.**")
            else:
                raise UserPermissionError(f"You don't own custom command {name}.")
        else:
            await respond(msg, f"**WARNING: No such custom command {name}.**")

    @Command("DeleteCC", "DelCC", "RMCC",
             doc="Deletes a custom command.",
             syntax="(name)",
             category="custom_commands")
    async def _delcc(self, msg: discord.Message):
        gid = str(msg.guild.id)
        self._initialize(gid)
        if msg.author.id in self.bans[gid]["cc_create_ban"]:
            raise UserPermissionError("You are banned from deleting custom commands.")
        try:
            name = msg.clean_content.split(None, 1)[1].lower()
        except IndexError:
            raise CommandSyntaxError("No name provided.")
        if gid not in self.ccs:
            self.ccs[gid] = {}
        if name in self.ccs[gid]:
            if self.ccs[gid][name]["author"] == msg.author.id or msg.author.guild_permissions.manage_messages:
                del self.ccs[gid][name]
                self.ccs.save()
                await respond(msg, f"**ANALYSIS: Custom command {name} deleted successfully.**")
            else:
                raise UserPermissionError(f"You don't own custom command {name}.")
        else:
            await respond(msg, f"**WARNING: No such custom command {name}.**")

    @Command("CCInfo",
             doc="Displays information about a custom command.",
             syntax="(name)",
             category="custom_commands")
    async def _ccinfo(self, msg: discord.Message):
        try:
            name = msg.clean_content.split(None, 1)[1].lower()
        except IndexError:
            raise CommandSyntaxError("No name provided.")
        gid = str(msg.guild.id)
        if gid not in self.ccs:
            self.ccs[gid] = {}
        if name in self.ccs[gid]:
            cc_data = self.ccs[gid][name]
            last_edited = f"Last Edited: {cc_data['last_edited']}\n" if cc_data["last_edited"] else ""
            cc_locked = "Yes" if cc_data["locked"] else "No"
            author = discord.utils.get(msg.guild.members, id=cc_data["author"])
            if author:
                author = str(author)
            else:
                author = "<Unknown user>"
            datastr = f"**ANALYSIS: Information for custom command {name}:**```\nName: {name}\nAuthor: {author}\n" \
                      f"Date Created: {cc_data['date_created']}\n{last_edited}Locked: {cc_locked}\n" \
                      f"Times Run: {cc_data['times_run']}```"
            await respond(msg, datastr)
        else:
            await respond(msg, f"**WARNING: No such custom command {name}.**")

    @Command("SearchCCs", "SearchCC", "ListCCs", "ListCC",
             doc="Searches CCs by name or author.",
             syntax="(name, author, or */all)",
             category="custom_commands")
    async def _searchccs(self, msg: discord.Message):
        search = msg.content.split(None, 1)[1].lower()
        if not search:
            raise CommandSyntaxError("No search provided.")
        user = find_user(msg.guild, search)
        gid = str(msg.guild.id)
        if gid not in self.ccs:
            self.ccs[gid] = {}
        ccs_list = list(self.ccs[gid].keys())
        if search in ("*", "all"):
            matched_ccs = ccs_list
        elif user:
            matched_ccs = filter(lambda x: self.ccs[gid][x]["author"] == user.id, ccs_list)
        else:
            matched_ccs = filter(lambda x: search in x.lower(), ccs_list)
        if matched_ccs:
            for split_msg in group_items(matched_ccs, "**ANALYSIS: The following custom commands match your "
                                                      "search:**", joiner=', '):
                await respond(msg, split_msg)

        else:
            await respond(msg, "**WARNING: No results found for your search.**")

    @Command("LockCC",
             doc="Toggles lock on a custom command, preventing it from being used.",
             syntax="(name)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _lockcc(self, msg: discord.Message):
        try:
            name = msg.clean_content.split(None, 1)[1].lower()
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

    @Command("RestrictCC",
             doc="Restricts specified custom command to a specified category of channels, or removes said "
                 "restriction.",
             syntax="(name) (category)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _restrictcc(self, msg: discord.Message):
        gid = str(msg.guild.id)
        if gid not in self.ccs:
            self.ccs[gid] = {}
        try:
            _, name, category = msg.content.split(None, 2)
        except ValueError:
            raise CommandSyntaxError("Two arguments required.")
        if name in self.ccs[gid]:
            whitelist = self.ccs[gid][name].setdefault("restricted", [])

            if self.channel_manager.get_category(msg.guild, category):
                if category not in whitelist:
                    whitelist.append(category)
                    await respond(msg, f"**AFFIRMATIVE. Custom command {name} restricted to category {category}.**")
                else:
                    whitelist.remove(category)
                    await respond(msg, f"**AFFIRMATIVE. Custom command {name} no longer restricted to category "
                                       f"{category}.**")
            else:
                raise CommandSyntaxError(f"No channel category by name of {category}.")
        else:
            raise CommandSyntaxError(f"No custom command by name of {name}.")

    @Command("CCMute", "MuteCC",
             doc="Toggles users ability to use custom commands.",
             syntax="(user)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _mutecc(self, msg: discord.Message):
        gid = str(msg.guild.id)
        self._initialize(gid)
        user = find_user(msg.guild, msg.content.split(None, 1)[1])
        if not user:
            raise CommandSyntaxError("Not a user, or user not found.")
        if user.id in self.bans[gid]["cc_use_ban"]:
            self.bans[gid]["cc_use_ban"].remove(user.id)
            await respond(msg, f"**AFFIRMATIVE. User {user} was allowed the usage of custom commands.**")
        else:
            self.bans[gid]["cc_use_ban"].append(user.id)
            await respond(msg, f"**AFFIRMATIVE. User {user} was banned from using custom commands.**")

    @Command("CCBan", "BanCC",
             doc="Toggles users ability to create and alter custom commands.",
             syntax="(user)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _bancc(self, msg: discord.Message):
        gid = str(msg.guild.id)
        self._initialize(gid)
        user = find_user(msg.guild, msg.content.split(None, 1)[1])
        if not user:
            raise CommandSyntaxError("Not a user, or user not found.")
        if user.id in self.bans[gid]["cc_create_ban"]:
            self.bans[gid]["cc_create_ban"].remove(user.id)
            await respond(msg, f"**AFFIRMATIVE. User {user} was allowed creation of custom commands.**")
        else:
            self.bans[gid]["cc_create_ban"].append(user.id)
            await respond(msg, f"**AFFIRMATIVE. User {user} was banned from creating custom commands.**")

    @Command("ListCCbans",
             doc="Lists users banned from using or creating CCs",
             syntax="(user)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _listccban(self, msg: discord.Message):
        gid = str(msg.guild.id)
        self._initialize(gid)
        banned_users = {}
        for uid in self.bans[gid]["cc_create_ban"]:
            if uid in self.bans[gid]["cc_use_ban"]:
                banned_users[uid] = (True, True)
            else:
                banned_users[uid] = (True, False)
        for uid in self.bans[gid]["cc_use_ban"]:
            if uid not in banned_users:
                banned_users[uid] = (False, True)
        result_list = [f"{msg.guild.get_member(k).display_name:<32} | {str(v[0]):<5)} | "
                       f"{str(v[1]):<5}\n" for k, v in banned_users.items()]
        result_list.insert(0, f"{'Username'.ljust(32)} |  Ban  |  Mute")
        for split_msg in group_items(result_list, "**ANALYSIS: Currently banned members:**"):
            await respond(msg, split_msg)

    @Command("RPN",
             doc="Calculates an expression in extended reverse polish notation.\n"
                 "Binary operators: +, -, *, /, ^ (power), % (modulo), // (integer division), atan2, swap (swaps "
                 "two numbers in stack), log.\n"
                 "Unary operators: sin, cos, tan, ln, pop (remove number from stack), int, dup (duplicate number in "
                 "stack), drop, modf, round, rndint.\n"
                 "Constants: e, pi, tau, m2f (one meter in feet), m2i (one meter in inches), rnd.",
             run_anywhere=True)
    async def _rpncmd(self, msg: discord.Message):
        if self.rpn_path is None:
            return

        # sanitizing the input. Couldn't figure out a way to exploit Popen but *just in case*.
        num = re.compile(r"\d*\.\d+|\d+\.|0[xbo]\d+")
        ops = ("+", "-", "*", "/", "^", "%", "//", "log", "atan2", "swap", "min", "max", "sin", "cos", "tan", "ln",
               "pop", "int", "dup", "drop", "modf", "round", "rndint", "e", "pi", "tau", "m2f", "m2i", "rnd")

        args = [executable, str(self.rpn_path)] + [a for a in msg.content.lower().split()
                                                   if a in ops or a.isnumeric() or num.match(a)]

        # a convoluted way to run the RPN in such a way that plugging 3 3 3 3 ^ ^ ^ or something like that into the bot
        # doesn't make it lock up.
        # TODO: figure out if we can make multiprocessing work after all, this is kind of a hack.
        process = Popen(args, stdout=PIPE, stderr=PIPE, encoding="utf-8")
        try:
            output, err = process.communicate(timeout=self.plugin_config.get('rslisp_max_runtime', 5))
            process.wait()
            if err:
                raise CommandSyntaxError(output)
            result = output.split()
        except TimeoutExpired:
            process.kill()
            raise CommandSyntaxError("Command ran too long.")

        await respond(msg, f"**Result : [ {' | '.join([str(x) for x in result])} ]**")

    # Custom command machinery

    @Command("EvalCC",
             doc="Evaluates the given string through RSLisp cc parser.",
             syntax="(custom command)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _evalcc(self, msg: discord.Message):
        program = msg.content.split(None, 1)[1]
        try:
            program = parse(program)
        except Exception as e:
            await respond(msg, f"**WARNING: Syntax error in custom command:** {e}")
        try:
            env = self._env(msg)
            result = lisp_eval(program, env)
        except Exception as e:
            await respond(msg, f"**WARNING: Runtime error in custom command:** {e}")
        else:
            if env['_rsoutput']:
                await respond(msg, str(env['_rsoutput']))
            elif result:
                await respond(msg, str(result))

    @Command("UploadCCData",
             doc="Uploads a cc-accessible data file in a json format.\n"
                 "File id must be one word with no dots/slashes that is up to 20 symbols.\n"
                 "Description is mandatory and needs to describe the contents of the file.\n"
                 "File itself must be valid JSON.",
             syntax="(file id) (description) +json file",
             category="custom_commands")
    async def _uploadccdata(self, msg: discord.Message):
        try:
            _, fid, desc = msg.clean_content.split(None, 2)
            fp = BytesIO()
            await msg.attachments[0].save(fp)

            # poor man's deflating. We're still storing JSON, but we want to store the least JSON possible.
            content = json.dumps(decode_json(fp.getvalue()), separators=(',', ':'), ensure_ascii=False)
        except json.decoder.JSONDecodeError as e:
            raise CommandSyntaxError(e)
        except (ValueError, IndexError):
            raise CommandSyntaxError

        fid = fid.lower()[:20]

        # since the fid string will just be slapped onto the end of a path, it's a good idea to make sure users
        # can't just point at whatever they see fit and go "that's my file"
        if not fid.isidentifier():
            raise CommandSyntaxError("Illegal characters in file ID.")

        total_size = sum([x.size for x in self.ccfdata.values() if x.owner == msg.author.id])

        if fid in self.ccfdata:
            if self.ccfdata[fid].owner != msg.author.id:
                raise UserPermissionError
            total_size -= self.ccfdata[fid].size

        size = len(content)
        if total_size + size > self.plugin_config['cc_file_quota'] \
                and not self.config_manager.is_maintainer(msg.author):
            raise UserPermissionError("File exceeds size quota. Remaining quota: "
                                      f"{self.plugin_config['cc_file_quota']-total_size} bytes.")

        self.ccfdata[fid] = CCFileMetadata(msg.author.id, size, desc.replace('\r', ''))

        total_size = self.plugin_config['cc_file_quota'] - total_size - size

        with (self.ccfolder / (fid + '.json')).open('w', encoding='utf8') as fp:
            fp.write(content)

        await respond(msg, f"**AFFIRMATIVE. CC data file {fid} now available.\nRemaining quota: {total_size} bytes.**")

    @Command("ListCCData",
             doc="Prints a list of all available data files, including first line of description (shortened to 50 "
                 "characters), owner and size.",
             category="custom_commands")
    async def _listccdata(self, msg: discord.Message):
        # since the descriptions may be multiline, it's nice to remove any possible newlines and what comes after.
        def desc(v: CCFileMetadata):
            return v.desc.split('\n')[0][:50]

        items = (f"{k:20} : {desc(v):50} : {str(self.client.get_user(v.owner))} : {v.size} bytes"
                 for k, v in self.ccfdata.items())

        for split in group_items(items, "**ANALYSIS: Following data files available:**"):
            await respond(msg, split)

    @Command("DeleteCCData",
             doc="Removes a data file.",
             syntax="(file id)",
             category="custom_commands")
    async def _delccdata(self, msg: discord.Message):
        try:
            fid = msg.clean_content.split(None, 1)[1].lower()[:20]

            if fid in self.ccfdata:
                if self.ccfdata[fid].owner != msg.author.id and not self.config_manager.is_maintainer(msg.author):
                    raise UserPermissionError("File belongs to another user.")
                del self.ccfdata[fid]
                remove(self.ccfolder / (fid + '.json'))
                await respond(msg, f"**AFFIRMATIVE. File {fid} removed.**")
            else:
                raise CommandSyntaxError(f"No file {fid} found.")
        except IndexError:
            raise CommandSyntaxError
        except OSError:
            raise CommandSyntaxError("Error while deleting file. Please contact the bot maintainer.")

    @Command("CCData",
             doc="Prints out the information associated with a data file, including person uploading, "
                 "size and description.",
             syntax="(file id)",
             category="custom_commands")
    async def _ccdata(self, msg: discord.Message):
        try:
            fid = msg.clean_content.split()[1].lower()[:20]
            if fid in self.ccfdata:
                f = self.ccfdata[fid]
                await respond(msg, f"`{fid} uploaded by {self.client.get_user(f.owner)} ({f.size}b)`\n\n{f.desc}")
            else:
                raise CommandSyntaxError(f"No file {fid} found.")
        except IndexError:
            raise CommandSyntaxError

    @Command("EditCCData",
             doc="Changes the description associated to one given.",
             syntax="(file id) (description)",
             category="custom_commands")
    async def _editccdata(self, msg: discord.Message):
        try:
            _, fid, desc = msg.clean_content.split(None, 2)
            if fid in self.ccfdata:
                if self.ccfdata[fid].owner != msg.author.id and not self.config_manager.is_maintainer(msg.author):
                    raise UserPermissionError
                self.ccfdata[fid].desc = desc.replace('\r', '')
                await respond(msg, "**AFFIRMATIVE. Description updated.**")
            else:
                raise CommandSyntaxError(f"No file {fid} found.")
        except ValueError:
            raise CommandSyntaxError

    @Command("DumpCCData",
             doc="Uploads the specified data file",
             syntax="(file id)",
             category="custom_commands")
    async def _dumpccdata(self, msg: discord.Message):
        try:
            _, fid = msg.clean_content.split(None, 1)
            fid = fid.lower()[:20]
            if fid in self.ccfdata:
                async with msg.channel.typing():
                    await respond(msg, "**AFFIRMATIVE.**",
                                  file=discord.File((self.ccfolder / (fid + '.json')).resolve().as_posix(),
                                                    filename=fid + ".json"))
            else:
                raise CommandSyntaxError(f"No file {fid} found.")
        except ValueError:
            raise CommandSyntaxError

    @staticmethod
    async def _rm_msg(msg: discord.Message):
        await sleep(1)
        await msg.delete()

    def _initialize(self, gid: str):
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.default_config["default"].copy()
            self.config_manager.save_config()
        if gid not in self.bans:
            self.bans[gid] = {
                "cc_create_ban": [],
                "cc_use_ban": []
            }

    async def run_cc(self, cmd: str, msg: discord.Message):
        gid = str(msg.guild.id)
        if self.ccs[gid][cmd]["locked"] and not msg.author.guild_permissions.manage_messages:
            await respond(msg, f"**WARNING: Custom command {cmd} is locked.**")
        else:
            env = self._env(msg)

            cc_data = self.ccs[gid][cmd]["content"]
            try:
                res = lisp_eval(parse(cc_data), env)
            except CustomCommandSyntaxError as e:
                err = e if e else "Syntax error."
                await respond(msg, f"**WARNING: Author made syntax error: {err}**")
            except CommandSyntaxError as e:
                err = e if e else "Syntax error."
                await respond(msg, f"**WARNING: {err}**")
            except Exception as e:
                err = e if e else "Syntax error."
                self.logger.exception("Exception occurred in custom command: ", exc_info=True)
                await respond(msg, f"**WARNING: An error occurred while running the custom command: {err}**")
            else:
                if env['_rsoutput']:
                    await respond(msg, env['_rsoutput'])
                elif res:
                    await respond(msg, str(res))
                self.ccs[gid][cmd]["times_run"] += 1
                self.ccs.save()

    #  tag functions that *require* the discord machinery

    def _env(self, msg: discord.Message):
        gid = str(msg.guild.id)
        cmd = msg.content[len(self.plugin_config[gid]["cc_prefix"]):].split()[0].lower()
        env = standard_env(max_runtime=self.plugin_config.get('rslisp_max_runtime', 0))

        env['username'] = msg.author.name
        env['usernick'] = msg.author.display_name
        env['usermention'] = msg.author.mention
        try:
            author = discord.utils.get(msg.guild.members, id=self.ccs[gid][cmd]['author'])
            env['authorname'] = author.name
            env['authornick'] = author.display_name
        except (AttributeError, KeyError):
            env['authorname'] = env['authornick'] = '<Unknown user>'
        args = msg.clean_content.split(" ", 1)
        env['argstring'] = args[1] if len(args) > 1 else ''
        env['args'] = args[1].split(" ") if len(args) > 1 else []

        env['hasrole'] = lambda *x: self._hasrole(msg, *x)
        env['delcall'] = lambda: self._delcall(msg)
        env['embed'] = lambda *x: self._embed(msg, *get_args(x))
        env['file'] = lambda x: self._file(x)

        return env

    def _delcall(self, msg: discord.Message):
        create_task(self._rm_msg(msg))

    @staticmethod
    def _hasrole(msg: discord.Message, *args: [str]) -> bool:
        _args = map(str.lower, args)
        return any([x.name.lower() in _args for x in msg.author.roles])

    @staticmethod
    def _embed(msg: discord.Message, _, kwargs: dict[str, str | int | list]):
        embed = discord.Embed(type="rich", colour=16711680)
        can_post = False
        for name, value in kwargs.items():
            can_post = True
            if name.lower() == "!title":
                embed.title = value
            elif name.lower() in ["!color", "!colour"]:
                try:
                    embed.colour = value if isinstance(value, int) else discord.Colour(int(value, 16))
                except ValueError:
                    pass
            elif name.lower() == "!url":
                embed.url = value
            elif name.lower() == "!thumbnail":
                embed.set_thumbnail(url=value)
            elif name.lower() == "!image":
                embed.set_image(url=value)
            elif name.lower() in ["!desc", "!description"]:
                embed.description = value
            elif name.lower() == "!footer":
                embed.set_footer(text=value)
            else:
                if type(value) == list:
                    content = value[0]
                    is_inline = value[1]
                else:
                    content = value
                    is_inline = False
                embed.add_field(name=name, value=content, inline=is_inline)
        if can_post:
            create_task(respond(msg, None, embed=embed))

    def _file(self, filename: str):
        if not filename.isidentifier():
            raise CustomCommandSyntaxError(f"file error: illegal filename {filename}")
        try:
            with (self.ccfolder / (filename + '.json')).open() as fp:
                return json.load(fp)
        except FileNotFoundError:
            raise CustomCommandSyntaxError(f"file error: no file named {filename}")
        except json.decoder.JSONDecodeError:
            raise CustomCommandSyntaxError(f"json error: file {filename} is invalid json")
