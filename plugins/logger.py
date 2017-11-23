import asyncio
from plugin_manager import BasePlugin
from rs_errors import ChannelNotFoundError, CommandSyntaxError
from rs_utils import split_message, respond
from command_dispatcher import Command
from discord import AuditLogAction
from datetime import datetime, timedelta


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
                    logchan = self.channel_manager.get_channel(guild, "logs")
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
            self.logger.debug(f"User {uname}'s message at {msgtime} in {msg.channel.name} of {msg.guild.name} was "
                              f"deleted.\n"
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
            self.logger.debug(f"User {uname} edited their message at {msgtime} in {after.channel.name} of "
                              f"{after.guild.name}. \n"
                              f"Old contents: {old_contents}\nNew contents: {contents}")
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**WARNING: User {uname} edited their message at `{msgtime}` in "
                                       f"{after.channel.mention}. ANALYSIS:**\n"
                                       f"**Old contents:** {old_contents}\n**New contents:** {contents}")

    async def on_member_update(self, before, after):
        gid = str(after.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "member_update" not in self.plugin_config[gid].log_events:
            uname = str(after)
            t_str = ""
            t_log = ""
            if before.name != after.name or before.discriminator != after.discriminator:
                t_str = f"{t_str}`Old username : `{str(before)}\n`New username : `{uname}\n"
                t_log = f"{t_str}Old username : {str(before)} New username : {uname}\n"
            if before.avatar != after.avatar:
                t_str = f"{t_str}`New avatar : `{after.avatar_url}\n"
                t_log = f"{t_str}New avatar : {after.avatar_url}\n"
            if before.nick != after.nick:
                t_str = f"{t_str}`Old nick: `{before.nick}\n`New nick : `{after.nick}\n"
                t_log = f"{t_str}Old nick: {before.nick} New nick : {after.nick}\n"
            if before.roles != after.roles:
                o_role = ", ".join([str(x) for x in before.roles])
                n_role = ", ".join([str(x) for x in after.roles])
                t_str = f"{t_str}**Old roles :**```[ {o_role.replace('@','')} ]```\n" \
                        f"**New roles :**```[ {n_role.replace('@','')} ]```\n"
                t_log = f"{t_str}Old roles : [ {o_role.replace('@','')} ]\n" \
                        f"New roles :[ {n_role.replace('@','')} ]\n"
            if t_str == "":
                return
            self.logger.debug(f"User {uname} was modified:\n{t_log}")
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**WARNING. User {uname} was modified:**\n{t_str}")

    async def on_guild_channel_pins_update(self, channel, last_pin):
        gid = str(channel.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "guild_channel_pins_update" not in self.plugin_config[gid]["log_events"]:
            updtime = last_pin.strftime("%Y-%m-%d @ %H:%M:%S")
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**ANALYSIS: A message was pinned in {channel.mention} at `{updtime}`**")

    async def on_member_ban(self, guild, member):
        gid = str(guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "on_member_ban" not in self.plugin_config[gid]["log_events"]:
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.logger.info(f"User {str(member)} was banned on server {str(member.guild)}")
            self.log_items[gid].append(f"**ANALYSIS: User {str(member)} was banned.**")

    async def on_member_unban(self, guild, member):
        gid = str(guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "on_member_unban" not in self.plugin_config[gid]["log_events"]:
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.logger.info(f"User {str(member)} was unbanned on server {str(member.guild)}")
            self.log_items[gid].append(f"**ANALYSIS: Ban was lifted from user {str(member)}.**")

    async def on_member_join(self, member):
        gid = str(member.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "on_member_join" not in self.plugin_config[gid]["log_events"]:
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.logger.info(f"User {member} has joined server {str(member.guild)}")
            self.log_items[gid].append(f"**ANALYSIS: User {str(member)} has joined the server. "
                                       f"User id: `{member.id}`**")

    async def on_member_remove(self, member):
        gid = str(member.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "on_member_remove" not in self.plugin_config[gid]["log_events"]:
            t_time = datetime.utcnow()
            # find audit log entries for kicking of member with our ID, created in last five seconds.
            # Hopefully five seconds is enough
            audit = [f"{str(l.user)} for reasons: {l.reason or 'None'}" async for l in member.guild.audit_logs(
                    action=AuditLogAction.kick)
                     if l.target.id == member.id and (t_time - l.created_at < timedelta(seconds=5))]
            if gid not in self.log_items:
                self.log_items[gid] = []
            if audit:
                self.logger.info(f"User {member} ({member.id}) was kicked by {audit[0]} from {str(member.guild)}.")
                self.log_items[gid].append(f"**ANALYSIS: User {str(member)} was kicked from the server by {audit[0]}. "
                                           f"User id: `{member.id}`**")
            else:
                self.logger.info(f"User {member} ({member.id}) left {str(member.guild)}.")
                self.log_items[gid].append(f"**ANALYSIS: User {str(member)} has left the server. "
                                           f"User id: `{member.id}`**")

    async def on_guild_role_update(self, before, after):
        gid = str(before.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "on_guild_role_update" not in self.plugin_config[gid]["log_events"]:
            if gid not in self.log_items:
                self.log_items[gid] = []
            diff = []
            audit = [l async for l in
                     after.guild.audit_logs(action=AuditLogAction.role_update) if l.target.id == after.id and
                     (datetime.utcnow() - l.created_at < timedelta(seconds=5))]

            if audit:
                t_aud = str(audit[0].user)
            else:
                t_aud = "Unknown"

            if before == after:
                if audit:
                    t_b = audit[0].changes.before.__dict__
                    before.name = t_b.get("name", after.name)
                    before.colour = t_b.get("colour", after.colour)
                    before.hoist = t_b.get("hoist", after.hoist)
                    before.mentionable = t_b.get("mentionable", after.mentionable)
                    before.permissions = t_b.get("permissions", after.permissions)
                else:
                    return

            if before.name != after.name:
                diff.append(f"Name changed from {before.name} to {after.name}")
            if before.position != after.position:
                diff.append(f"Position changed from {before.position} to {after.position}")
            if before.colour != after.colour:
                diff.append(f"Colour changed from {before.colour} to {after.colour}")
            if before.hoist != after.hoist:
                diff.append("Is now displayed separately." if after.hoist else "Is no longer displayed separately.")
            if before.mentionable != after.mentionable:
                diff.append("Can now be mentioned." if after.mentionable else "Can no longer be mentioned.")
            if before.permissions != after.permissions:
                # comparing both sets of permissions, PITA
                d_before = {x: y for x, y in before.permissions}
                d_after = {x: y for x, y in after.permissions}
                t_str = "Added permissions: " + ", ".join([x.upper() for x, y in after.permissions if y and not
                                                          d_before[x]])
                t_str = t_str + "\nRemoved permissions: " \
                    + ", ".join([x.upper() for x, y in before.permissions if y and not d_after[x]])
                diff.append(t_str)
            t_res = f"**ANALYSIS: Role {before.name} was changed by {t_aud}:**\n```\n" + "\n".join(diff) + "```"
            self.logger.info(f"Role {before.name} of {str(before.guild)} was changed by {t_aud}:\n"+"\n".join(diff))
            self.log_items[gid].append(t_res)

    async def on_log_event(self, guild, string, *, log_type="log_event"):
        gid = str(guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if log_type not in self.plugin_config[gid].log_events:
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(string)

    @Command("LogEvent",
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
                    self.config_manager.save_config()
                    await respond(msg, f"**ANALYSIS: No longer logging events of type {args[2].lower()}.**")
                else:
                    await respond(msg, f"**ANALYSIS: Event type {args[2].lower()} is already disabled.**")
            elif args[1].lower() == "add":
                if args[2].lower() in cfg:
                    cfg.remove(args[2].lower())
                    self.config_manager.save_config()
                    await respond(msg, f"**ANALYSIS: Now logging events of type {args[2].lower()}.**")
                else:
                    await respond(msg, f"**ANALYSIS: Event type {args[2].lower()} is already logged.**")
        elif len(args) == 2:
            raise CommandSyntaxError
        else:
            disabled = ", ".join(cfg)
            await respond(msg, f"**ANALYSIS: Disabled log events: **`{disabled}`")
