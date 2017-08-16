import asyncio
from plugin_manager import BasePlugin
from plugins.channel_manager import ChannelNotFoundError
from utils import split_message, Command, respond


class DiscordLogger(BasePlugin):
    name = "logger"
    default_config = {
        "default": {
            "log_events": [
            ]
        }
    }

    async def activate(self):
        self.log_items = {}
        self.active = True
        asyncio.ensure_future(self._dump_logs())

    async def deactivate(self):
        self.active = False

    async def _dump_logs(self):
        while self.active:
            await asyncio.sleep(1)
            if not self.active:
                return
            for guild in self.client.guilds:
                gid = str(guild.id)
                try:
                    logchan = self.plugins.channel_manager.get_channel(guild, "logs")
                except ChannelNotFoundError:
                    continue
                except AttributeError:
                    self.logger.error("Failed to get channel.")
                    return
                if gid in self.log_items and self.log_items[gid]:
                    logs = "\n".join(self.log_items[gid])
                    for msg in split_message(logs, splitter="\n"):
                        await logchan.send(msg)
                    self.log_items[gid] = []

    async def on_message_delete(self, msg):
        gid = str(msg.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "message_delete" not in self.plugin_config[gid].log_events and msg.author != self.client.user:
            uname = str(msg.author)
            contents = msg.clean_content
            msgtime = msg.created_at.strftime("%Y-%m-%d @ %H:%M:%S")
            attaches = ""
            links = ""
            if msg.attachments:
                links = ", ".join([x.url for x in msg.attachments])
                attaches = f"\n**Attachments:** `{links}`"
            self.logger.debug(f"User {uname}'s message at {msgtime} in {msg.channel.name} was deleted.\n"
                              f"Contents: {contents}\nAttachments: {links}")
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**WARNING: User {uname}'s message at `{msgtime}` in {msg.channel.mention} was"
                                       f" deleted. ANALYSIS: Contents:**\n{contents}{attaches}")

    async def on_message_edit(self, before, after):
        gid = str(after.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "message_edit" not in self.plugin_config[gid].log_events and after.author != self.client.user:
            uname = str(after.author)
            old_contents = before.clean_content
            contents = after.clean_content
            msgtime = after.created_at.strftime("%Y-%m-%d @ %H:%M:%S")
            if old_contents == contents:
                return
            self.logger.debug(f"User {uname} edited their message at {msgtime} in {after.channel.name}. \n"
                              f"Old contents: {old_contents}\nNew contents: {contents}")
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**WARNING: User {uname} edited their message at `{msgtime}` in "
                                       f"{after.channel.mention}. ANALYSIS:**\n"
                                       f"**Old contents:** {old_contents}\n**New contents:** {contents}")

    async def on_member_join(self, member):
        gid = str(member.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "member_join" not in self.plugin_config[gid].log_events:
            uname = str(member)
            self.logger.debug(f"User {uname} joined {member.guild.name}.")
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**NEW USER DETECTED: {uname}.**")

    async def on_member_remove(self, member):
        gid = str(member.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "member_remove" not in self.plugin_config[gid].log_events:
            uname = str(member)
            self.logger.debug(f"User {uname} left {member.guild.name}.")
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**WARNING: User {uname} has left the server.**")

    async def on_member_update(self, before, after):
        gid = str(after.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "member_update" not in self.plugin_config[gid].log_events:
            uname = str(after)
            t_str = ""
            if before.avatar != after.avatar:
                t_str = f"{t_str}`New avatar : `{after.avatar_url}\n"
            if before.nick != after.nick:
                t_str = f"{t_str}`Old nick: `{before.nick}\n`New nick : `{after.nick}\n"
            if before.roles != after.roles:
                o_role = ", ".join([str(x) for x in before.roles])
                n_role = ", ".join([str(x) for x in after.roles])
                t_str = f"{t_str}**Old roles :**```[ {o_role.replace('@','')} ]```\n" \
                        f"**New roles :**```[ {n_role.replace('@','')} ]```\n"
            if t_str == "":
                return
            self.logger.debug(f"User {uname} was modified:\n{t_str}".replace("```", " ").replace("**", ""))
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**WARNING. User {uname} was modified:**\n{t_str}")

    async def on_log_event(self, guild, string, *, log_type="log_event"):
        gid = str(guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if log_type not in self.plugin_config[gid].log_events:
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(string)

    @Command("logevent",
             doc="Adds or removes the events to be logged.",
             syntax="(add/remove) (type)",
             category="bot_management",
             perms={"manage_guild"})
    async def _logevent(self, msg):
        gid = str(msg.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        cfg = self.plugin_config[gid].log_events
        args = msg.clean_content.split(" ", 2)
        if len(args) > 2:
            if args[1].lower() == "remove":
                if args[2].lower() not in cfg:
                    cfg.append(args[2].lower())
                    await respond(msg, f"**ANALYSIS: No longer logging events of type {args[2].lower()}.**")
                else:
                    await respond(msg, f"**ANALYSIS: Event type {args[2].lower()} is already disabled.**")
            elif args[1].lower() == "add":
                if args[2].lower() in cfg:
                    cfg.remove(args[2].lower())
                    await respond(msg, f"**ANALYSIS: Now logging events of type {args[2].lower()}.**")
                else:
                    await respond(msg, f"**ANALYSIS: Event type {args[2].lower()} is already logged.**")
        elif len(args) == 2:
            raise SyntaxError
        else:
            disabled = ", ".join(cfg)
            await respond(msg, f"**ANALYSIS: Disabled log events: **`{disabled}`")