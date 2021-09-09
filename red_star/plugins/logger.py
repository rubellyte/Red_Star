from datetime import datetime, timedelta
from discord import AuditLogAction, Forbidden
from discord.utils import escape_mentions
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import ChannelNotFoundError, CommandSyntaxError
from red_star.rs_utils import split_message, respond, close_markdown
from red_star.command_dispatcher import Command


class DiscordLogger(BasePlugin):
    name = "logger"
    version = "1.5"
    author = "medeor413, GTG3000"
    description = "A plugin that logs certain events and prints them to a defined log channel " \
                  "in an easily-readable manner."
    default_config = {
        "default": {
            "log_event_blacklist": [
            ]
        }
    }
    channel_types = {"logs"}
    log_events = {"message_delete", "message_edit", "member_update", "pin_update", "member_ban", "member_unban",
                  "member_join", "member_leave", "role_update"}

    async def activate(self):
        self.log_items = {}

    async def on_all_plugins_loaded(self):
        for plg in self.plugins.values():
            if plg is self:
                continue
            plg_log_events = getattr(plg, "log_events", None)
            if plg_log_events:
                self.log_events |= plg_log_events
                self.logger.debug(f"Registered log events {', '.join(plg_log_events)} from {plg.name}.")

    async def on_global_tick(self, *_):
        for guild in self.client.guilds:
            gid = str(guild.id)
            try:
                log_channel = self.channel_manager.get_channel(guild, "logs")
            except ChannelNotFoundError:
                continue
            if gid in self.log_items and self.log_items[gid]:
                logs = "\n".join(self.log_items[gid])
                if not logs:
                    continue
                for msg in split_message(logs, splitter="\n"):
                    if msg and not msg.isspace():
                        await log_channel.send(escape_mentions(msg))
                self.log_items[gid].clear()

    async def on_message_delete(self, msg):
        blacklist = self.plugin_config.setdefault(str(msg.guild.id),
                                                  self.plugin_config["default"])["log_event_blacklist"]
        if "message_delete" not in blacklist and msg.author != self.client.user:
            contents, _ = close_markdown(msg.clean_content if msg.clean_content else msg.system_content)
            msgtime = msg.created_at.strftime("%Y-%m-%d @ %H:%M:%S")
            attaches = ""
            if msg.attachments:
                links = ", ".join([x.proxy_url or x.url for x in msg.attachments])
                attaches = f"\n**Attachments:** `{links}`"
            self.emit_log(f"**ANALYSIS: User {msg.author}'s message at `{msgtime}` in {msg.channel.mention}"
                          f" was deleted. ANALYSIS: Contents:**\n{contents}{attaches}", msg.guild)

            self.logger.info(f"{msg.author}'s message at {msgtime} in {msg.channel} of {msg.guild} was deleted:\n"
                             f"Contents:\n{contents}{attaches.replace('**','')}")

    async def on_message_edit(self, before, after):
        blacklist = self.plugin_config.setdefault(str(after.guild.id),
                                                  self.plugin_config["default"])["log_event_blacklist"]
        if "message_edit" not in blacklist and after.author != self.client.user:
            old_contents, _ = close_markdown(before.clean_content)
            contents, _ = close_markdown(after.clean_content)
            if old_contents == contents:
                return
            msgtime = after.created_at.strftime("%Y-%m-%d @ %H:%M:%S")
            self.emit_log(f"**ANALYSIS: User {after.author} edited their message at `{msgtime}` in "
                          f"{after.channel.mention}. ANALYSIS:**\n**Old contents:** {old_contents}\n"
                          f"**New contents:** {contents}", after.guild)

            self.logger.info(f"User {after.author} edited their message "
                             f"at {msgtime} in {after.channel} of {after.guild}.\n"
                             f"Old contents:\n{old_contents}\nNew contents:\n{contents}")

    async def on_member_update(self, before, after):
        blacklist = self.plugin_config.setdefault(str(after.guild.id),
                                                  self.plugin_config["default"])["log_event_blacklist"]
        if "member_update" not in blacklist:
            diff_str = log_str = ""
            if before.name != after.name or before.discriminator != after.discriminator:
                diff_str = f"`Old username: `{before}\n`New username: `{after}\n"
                log_str = f"Old username: {before}\nNew username: {after}\n"
            if before.avatar != after.avatar:
                diff_str = f"{diff_str}`New avatar: `{after.avatar_url}\n"
                log_str = f"{log_str}New avatar: {after.avatar_url}\n"
            if before.nick != after.nick:
                diff_str = f"{diff_str}`Old nick: `{before.nick}\n`New nick: `{after.nick}\n"
                log_str = f"{log_str}Old nick: {before.nick}\nNew nick: {after.nick}\n"
            if before.roles != after.roles:
                old_roles = ", ".join([str(x) for x in before.roles])
                new_roles = ", ".join([str(x) for x in after.roles])
                diff_str = f"{diff_str}**Old roles:**```[ {old_roles} ]```\n**New roles:**```[ {new_roles} ]```"
                log_str = f"{log_str}Old roles: [ {old_roles} ]\nNew roles: [ {new_roles} ]"
            if not diff_str:
                return
            self.emit_log(f"**ANALYSIS: User {after} was modified:**\n{diff_str}", after.guild)
            self.logger.info(f"User {after} was modified:\n{log_str}")

    async def on_guild_channel_pins_update(self, channel, last_pin):
        blacklist = self.plugin_config.setdefault(str(channel.guild.id),
                                                  self.plugin_config["default"])["log_event_blacklist"]
        if "pin_update" not in blacklist:
            cnt = None
            try:
                new_pin = (datetime.utcnow() - last_pin < timedelta(seconds=5))
            except TypeError:  # last_pin can be None if the last pin in a channel was unpinned
                new_pin = False
            if new_pin:  # Get the pinned message if it's a new pin; can't get the unpinned messages sadly
                msg = (await channel.pins())[0]
                cnt = msg.author, msg.clean_content
            self.emit_log(f"**ANALYSIS: A message was {'' if new_pin else 'un'}pinned in {channel.mention}.**\n"
                          f"{f'**Message: {cnt[0]}:** {cnt[1]}' if new_pin else ''}", channel.guild)
            self.logger.info(f"A message was {'' if new_pin else 'un'}pinned in {channel} of {channel.guild}\n"
                             f"{f'Message: {cnt[0]}: {cnt[1]}' if new_pin else ''}")

    async def on_member_ban(self, guild, member):
        blacklist = self.plugin_config.setdefault(str(guild.id), self.plugin_config["default"])["log_event_blacklist"]
        if "member_ban" not in blacklist:
            self.emit_log(f"**ANALYSIS: User {member} was banned.**", guild)
            self.logger.info(f"User {member} was benned in {guild}.")

    async def on_member_unban(self, guild, member):
        blacklist = self.plugin_config.setdefault(str(guild.id), self.plugin_config["default"])["log_event_blacklist"]
        if "member_unban" not in blacklist:
            self.emit_log(f"**ANALYSIS: Ban was lifted from user {member}.**", guild)
            self.logger.info(f"Ban was lifted from user {member} in {guild}")

    async def on_member_join(self, member):
        blacklist = self.plugin_config.setdefault(str(member.guild.id),
                                                  self.plugin_config["default"])["log_event_blacklist"]
        if "member_join" not in blacklist:
            self.emit_log(f"**ANALYSIS: User {member} has joined the server. User id: `{member.id}`**", member.guild)
            self.logger.info(f"User {member} has joined {member.guild}. User id: {member.id}.")

    async def on_member_remove(self, member):
        blacklist = self.plugin_config.setdefault(str(member.guild.id),
                                                  self.plugin_config["default"])["log_event_blacklist"]
        if "member_leave" not in blacklist:
            try:
                # find audit log entries for kicking of member with our ID, created in last five seconds.
                # Hopefully five seconds is enough
                latest_logs = member.guild.audit_logs(action=AuditLogAction.kick, limit=1)
                kick_event = await latest_logs.get(target__id=member.id)
            except Forbidden:
                kick_event = None
            if kick_event:
                kicker = kick_event.user
                reason_str = f"Reason: {kick_event.reason}; " if kick_event.reason else ""
                self.emit_log(f"**ANALYSIS: User {member} was kicked from the server by {kicker}. "
                              f"{reason_str}User id: `{member.id}`**", member.guild)
                self.logger.info(f"User {member} was kicked from {member.guild} by {kicker}. "
                                 f"{reason_str}User ud: {member.id}")
            else:
                self.emit_log(f"**ANALYSIS: User {member} has left the server. User id: `{member.id}`**", member.guild)
                self.logger.info(f"User {member} has left {member.guild}. User id: {member.id}.")

    async def on_guild_role_update(self, before, after):
        blacklist = self.plugin_config.setdefault(str(after.guild.id),
                                                  self.plugin_config["default"])["log_event_blacklist"]
        if "role_update" not in blacklist:
            diff = []
            try:
                audit_event = await after.guild.audit_logs(action=AuditLogAction.role_update, limit=1).get()
            except Forbidden:
                audit_event = None

            if before.name == after.name \
                    and before.colour == after.colour \
                    and before.hoist == after.hoist \
                    and before.mentionable == after.mentionable  \
                    and before.permissions == after.permissions \
                    and before.position == after.position:
                if audit_event is not None and audit_event.target == after:
                    before_dict = audit_event.changes.before.__dict__
                    before.name = before_dict.get("name", after.name)
                    before.colour = before_dict.get("colour", after.colour)
                    before.hoist = before_dict.get("hoist", after.hoist)
                    before.mentionable = before_dict.get("mentionable", after.mentionable)
                    before.permissions = before_dict.get("permissions", after.permissions)
                    before.position = before_dict.get("position", after.position)
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
                before_perms = [x for x, y in before.permissions if y]
                after_perms = [x for x, y in after.permissions if y]
                perm_diff = "Added permissions: " + ", ".join(x.upper() for x in after_perms if x not in before_perms)
                perm_diff += "\nRemoved permissions: " + \
                             ", ".join(x.upper() for x in before_perms if x not in after_perms)
                diff.append(perm_diff)

            if not diff or (len(diff) == 1 and before.position != after.position):
                return

            diff = '\n'.join(diff)

            self.emit_log(f"**ANALYSIS: Role {before.name} was changed by "
                          f"{audit_event.user if audit_event else 'someone'}:**\n"
                          f"```\n{diff}```\n", after.guild)
            self.logger.info(f"Role {before.name} was changed by "
                             f"{audit_event.user if audit_event else 'someone'}:\n"
                             f"{diff}")

    async def on_log_event(self, guild, string, *, log_type="log_event"):
        blacklist = self.plugin_config.setdefault(str(guild.id), self.plugin_config["default"])["log_event_blacklist"]
        if log_type not in blacklist:
            self.emit_log(string, guild)
            self.logger.info(string)

    def emit_log(self, log_str, guild):
        guild_log_queue = self.log_items.setdefault(str(guild.id), [])
        guild_log_queue.append(log_str)

    @Command("LogEvent",
             doc="Adds or removes the events to be logged.",
             syntax="[add|remove type]",
             category="bot_management",
             perms={"manage_guild"})
    async def _logevent(self, msg):
        cfg = self.plugin_config.setdefault(str(msg.guild.id), self.plugin_config["default"])["log_event_blacklist"]
        try:
            action, event_type = msg.clean_content.lower().split(" ", 2)[1:]
            if event_type not in self.log_events:
                await respond(f"**Log event {event_type} does not exist.\n"
                              f"Valid events:** `{', '.join(self.log_events)}`")
                return
        except ValueError:
            if len(msg.clean_content.split(" ")) == 1:
                enabled = ", ".join(self.log_events - set(cfg)) or "None"
                await respond(msg, f"**ANALYSIS: Enabled log events:** `{enabled}`\n"
                                   f"**Disabled log events:** {', '.join(cfg) or 'None'}")
                return
            else:
                raise CommandSyntaxError("Invalid number of arguments.")
        if action == "remove":
            if event_type not in cfg:
                cfg.append(event_type)
                self.config_manager.save_config()
                await respond(msg, f"**ANALYSIS: No longer logging events of type {event_type}.**")
            else:
                await respond(msg, f"**ANALYSIS: Event type {event_type} is already disabled.**")
        elif action == "add":
            if event_type in cfg:
                cfg.remove(event_type)
                self.config_manager.save_config()
                await respond(msg, f"**ANALYSIS: Now logging events of type {event_type}.**")
            else:
                await respond(msg, f"**ANALYSIS: Event type {event_type} is already logged.**")
        else:
            raise CommandSyntaxError(f"Action {action} is not a valid action.")
