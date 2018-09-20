import discord.utils
import datetime
import json
import math
import random
import re
from asyncio import ensure_future, sleep
from io import BytesIO
from red_star.plugin_manager import BasePlugin
from discord import Embed, File
from discord.errors import Forbidden
from red_star.command_dispatcher import Command
from red_star.rs_errors import CommandSyntaxError, UserPermissionError, CustomCommandSyntaxError
from red_star.rs_lisp import lisp_eval, parse, reprint, standard_env, get_args
from red_star.rs_utils import respond, find_user, split_output


# noinspection PyBroadException
class CustomCommands(BasePlugin):
    name = "custom_commands"
    version = "2.0"
    author = "GTG3000, medeor413"
    description = "A plugin that allows users to create custom commands using Red Star's " \
                  "custom RSLisp language dialect."
    default_config = {
        "default": {
            "cc_prefix": "!!",
            "cc_limit": 25
        },
        "rslisp_max_runtime": 5,
        "rslisp_minify": True
    }

    async def activate(self):
        self.ccs = self.config_manager.get_plugin_config_file("ccs.json")
        try:
            self.bans = self.ccs["bans"]
        except KeyError:
            self.bans = self.ccs["bans"] = {}

    # Event hooks

    async def on_message(self, msg):
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
                    except Forbidden:
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
    async def _reloadccs(self, msg):
        self.ccs.reload()
        await respond(msg, "**AFFIRMATIVE. CCS reloaded.**")

    @Command("CreateCC", "NewCC",
             doc="Creates a custom command.\n"
                 "RSLisp Documentation: https://github.com/medeor413/Red_Star/wiki/Custom-Commands",
             syntax="[-s/--source [name]](name) (content)",
             category="custom_commands")
    async def _createcc(self, msg: discord.Message):
        gid = str(msg.guild.id)
        self._initialize(gid)
        if msg.author.id in self.bans[gid]["cc_create_ban"]:
            raise UserPermissionError("You are banned from creating custom commands.")
        if msg.attachments:
            fp = BytesIO()
            await msg.attachments[0].save(fp)
            args = msg.clean_content.split()[1:]
            if args and args[0].lower() in ("-s", "--source"):
                name = args[1].lower() if len(args) > 1 else msg.attachments[0].filename.rsplit('.', 1)[0]
                content = fp.getvalue().decode()
            else:
                try:
                    jsdata = json.loads(fp.getvalue().decode())
                except json.JSONDecodeError:
                    raise CommandSyntaxError("Uploaded file is not valid JSON!")
                name = jsdata["name"].lower()
                content = jsdata["content"]
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
                    msg.author.permissions_in(msg.channel).manage_messages and user_cc_count >= cc_limit:
                raise UserPermissionError(f"Exceeded per-user custom command limit of {cc_limit}.")
            try:
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
    async def _dumpcc(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        if msg.author.id in self.bans[gid]["cc_create_ban"]:
            raise UserPermissionError("You are banned from editing custom commands.")
        try:
            name = msg.content.split(" ", 1)[1].lower()
        except IndexError:
            raise CommandSyntaxError("No name provided.")
        if name in self.ccs[gid]:
            cc = {
                "name": name,
                "content": self.ccs[gid][name]["content"]
            }
            cc = json.dumps(cc, indent=2, ensure_ascii=False)
            async with msg.channel.typing():
                await respond(msg, "**AFFIRMATIVE. Completed file upload.**",
                              file=File(BytesIO(bytes(cc, encoding="utf-8")), filename=name + ".json"))
        else:
            raise CommandSyntaxError(f"No such custom command {name}.")

    @Command("EditCC",
             doc="Edits a custom command you created.",
             syntax="[-s/--source [name]](name) (content)",
             category="custom_commands")
    async def _editcc(self, msg):
        gid = str(msg.guild.id)
        self._initialize(gid)
        if msg.author.id in self.bans[gid]["cc_create_ban"]:
            raise UserPermissionError("You are banned from editing custom commands.")
        if msg.attachments:
            fp = BytesIO()
            await msg.attachments[0].save(fp)
            args = msg.clean_content.split(None, 2)[1:]
            if args and args[0].lower() in ("-s", "--source"):
                name = args[1].lower() if len(args) > 1 else msg.attachments[0].filename.rsplit('.', 1)[0]
                content = fp.getvalue().decode()
            else:
                try:
                    jsdata = json.loads(fp.getvalue().decode())
                except json.JSONDecodeError:
                    raise CommandSyntaxError("Uploaded file is not valid JSON.")
                name = jsdata["name"].lower()
                content = jsdata["content"]
        else:
            try:
                name, content = msg.clean_content.split(" ", 2)
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
    async def _delcc(self, msg):
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
    async def _ccinfo(self, msg):
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
    async def _searchccs(self, msg):
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
            await split_output(msg, "**ANALYSIS: The following custom commands match your search:**", matched_ccs,
                               string_processor=lambda x: x + ", ")
        else:
            await respond(msg, "**WARNING: No results found for your search.**")

    @Command("LockCC",
             doc="Toggles lock on a custom command, preventing it from being used.",
             syntax="(name)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _lockcc(self, msg):
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
    async def _restrictcc(self, msg):
        gid = str(msg.guild.id)
        if gid not in self.ccs:
            self.ccs[gid] = {}
        try:
            name, category = msg.content.split(None, 2)
        except ValueError:
            raise CommandSyntaxError("Two arguments required.")
        if name in self.ccs[gid]:
            if "restricted" in self.ccs[gid][name]:
                if category not in self.ccs[gid][name]["restricted"]:
                    self.ccs[gid][name]["restricted"].append(category)
                    await respond(msg, f"**AFFIRMATIVE. Custom command {name} restricted to category {category}.**")
                else:
                    self.ccs[gid][name]["restricted"].remove(category)
                    await respond(msg, f"**AFFIRMATIVE. Custom command {name} no longer restricted to category "
                                       f"{category}.**")
            else:
                self.ccs[gid][name]["restricted"] = [category]
                await respond(msg, f"**AFFIRMATIVE. Custom command {name} restricted to category {category}.**")
        else:
            raise CommandSyntaxError(f"No custom command by name of {name}.")

    @Command("CCMute", "MuteCC",
             doc="Toggles users ability to use custom commands.",
             syntax="(user)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _mutecc(self, msg):
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
    async def _bancc(self, msg):
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
    async def _listccban(self, msg):
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
        await split_output(msg, "**ANALYSIS: Currently banned members:**", result_list)

    @Command("RPN",
             doc="Calculates an expression in extended reverse polish notation.\n"
                 "Binary operators: +, -, *, /, ^ (power), % (modulo), // (integer division), atan2, swap (swaps "
                 "two numbers in stack), log.\n"
                 "Unary operators: sin, cos, tan, ln, pop (remove number from stack), int, dup (duplicate number in "
                 "stack), drop, modf, round, rndint.\n"
                 "Constants: e, pi, tau, m2f (one meter in feet), m2i (one meter in inches), rnd.",
             run_anywhere=True)
    async def _rpncmd(self, msg):
        t_str = " | ".join([str(x) for x in self._parse_rpn(msg.content)])
        await respond(msg, "**Result : [ " + t_str + " ]**")

        # Custom command machinery

    @Command("EvalCC",
             doc="Evaluates the given string through RSLisp cc parser.",
             syntax="(custom command)",
             category="custom_commands",
             perms={"manage_messages"})
    async def _evalcc(self, msg):
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

    @staticmethod
    async def _rm_msg(msg):
        await sleep(1)
        await msg.delete()

    def _initialize(self, gid):
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.default_config["default"].copy()
            self.config_manager.save_config()
        if gid not in self.bans:
            self.bans[gid] = {
                "cc_create_ban": [],
                "cc_use_ban": []
            }

    @staticmethod
    def _parse_rpn(args):
        args = args.lower().split()
        if len(args) == 0:
            raise CustomCommandSyntaxError("<rpn> tag requires arguments.")
        stack = []
        out = []

        def _dup(x):
            stack.append(x)
            stack.append(x)

        def _swap(x, y):
            stack.append(x)
            stack.append(y)

        def _modf(x):
            v, v1 = math.modf(x)
            stack.append(v)
            stack.append(v1)

        binary_ops = {
            "+": lambda x, y: stack.append(x + y),
            "-": lambda x, y: stack.append(y - x),
            "*": lambda x, y: stack.append(x * y),
            "/": lambda x, y: stack.append(y / x),
            "^": lambda x, y: stack.append(y ** x),
            "%": lambda x, y: stack.append(y % x),
            "//": lambda x, y: stack.append(y // x),
            "log": lambda x, y: stack.append(math.log(y, x)),
            "atan2": lambda x, y: stack.append(math.atan2(y, x)),
            "swap": _swap,
            "min": lambda x, y: stack.append(min(x, y)),
            "max": lambda x, y: stack.append(max(x, y)),
        }
        unary_ops = {
            "sin": lambda x: stack.append(math.sin(x)),
            "cos": lambda x: stack.append(math.cos(x)),
            "tan": lambda x: stack.append(math.tan(x)),
            "ln": lambda x: stack.append(math.log(x)),
            "pop": lambda x: out.append(x),
            "int": lambda x: stack.append(int(x)),
            "dup": _dup,
            "drop": lambda x: x,
            "modf": _modf,
            "round": lambda x: stack.append(round(x)),
            "rndint": lambda x: stack.append(random.randint(0, x))
        }
        constants = {
            "e": lambda: stack.append(math.e),
            "pi": lambda: stack.append(math.pi),
            "tau": lambda: stack.append(math.tau),
            "m2f": lambda: stack.append(3.280839895),
            "m2i": lambda: stack.append(39.37007874),
            "rnd": lambda: stack.append(random.random())
        }
        for arg in args:
            try:
                value = int(arg, 0)
            except ValueError:
                try:
                    value = float(arg)
                except ValueError:
                    if arg in binary_ops and len(stack) > 1:
                        binary_ops[arg](stack.pop(), stack.pop())
                    elif arg in unary_ops and len(stack) >= 1:
                        unary_ops[arg](stack.pop())
                    elif arg in constants:
                        constants[arg]()
                else:
                    stack.append(value)
            else:
                stack.append(value)
        return [*out, *stack]

    async def run_cc(self, cmd, msg):
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

    def _env(self, msg):
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
        except AttributeError:
            env['authorname'] = env['authornick'] = '<Unknown user>'
        args = msg.clean_content.split(" ", 1)
        env['argstring'] = args[1] if len(args) > 1 else ''
        env['args'] = args[1].split(" ") if len(args) > 1 else []

        env['hasrole'] = lambda *x: self._hasrole(msg, *x)
        env['delcall'] = lambda: self._delcall(msg)
        env['embed'] = lambda *x: self._embed(msg, *get_args(x))

        return env

    def _delcall(self, msg):
        ensure_future(self._rm_msg(msg))

    @staticmethod
    def _hasrole(msg, *args):
        _args = map(str.lower, args)
        return any([x.name.lower() in _args for x in msg.author.roles])

    @staticmethod
    def _embed(msg, _, kwargs):
        embed = Embed(type="rich", colour=16711680)
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
            ensure_future(respond(msg, None, embed=embed))
