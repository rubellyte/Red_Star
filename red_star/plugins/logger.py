import discord
import discord.utils
import datetime
from discord.ext import tasks
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import ChannelNotFoundError, CommandSyntaxError
from red_star.rs_utils import split_message, respond, close_markdown
from red_star.command_dispatcher import Command


class DiscordLogger(BasePlugin):
    name = "logger"
    version = "1.6"
    author = "medeor413, GTG3000"
    description = "A plugin that logs certain events and prints them to a defined log channel " \
                  "in an easily-readable manner."
    default_config = {
        "log_output_interval": 15,
        "log_event_blacklist": [
        ]
    }
    channel_types = {"logs"}
    log_events = {"message_delete", "message_edit", "member_update", "pin_update", "member_ban", "member_unban",
                  "member_join", "member_leave", "role_update"}

    async def activate(self):
        self.log_message_queue = []
        self.print_log_messages.change_interval(seconds=self.config["log_output_interval"])
        self.print_log_messages.start()

    async def deactivate(self):
        self.print_log_messages.cancel()
        await self.print_log_messages()

    async def on_all_plugins_loaded(self):
        for plg in self.plugins.values():
            if plg is self:
                continue
            plg_log_events = getattr(plg, "log_events", None)
            if plg_log_events:
                self.log_events |= plg_log_events
                self.logger.debug(f"Registered log events {', '.join(plg_log_events)} from {plg.name}.")

    @tasks.loop(seconds=15)  # Note that this value is loaded from config and altered at runtime.
    async def print_log_messages(self):
        if self.log_message_queue:
            try:
                log_channel = self.channel_manager.get_channel("logs")
            except ChannelNotFoundError:
                self.log_message_queue.clear()
                return
            log_message = "\n".join(self.log_message_queue)
            for msg in split_message(log_message):
                if msg and not msg.isspace():
                    await log_channel.send(discord.utils.escape_mentions(msg))
            self.log_message_queue.clear()

    async def on_message_delete(self, msg: discord.Message):
        blacklist = self.config["log_event_blacklist"]
        if "message_delete" not in blacklist and msg.author != self.client.user:
            contents, _ = close_markdown(msg.clean_content if msg.clean_content else msg.system_content)
            msgtime = msg.created_at.strftime("%Y-%m-%d @ %H:%M:%S")
            attaches = ""
            if msg.attachments:
                links = ", ".join([x.proxy_url or x.url for x in msg.attachments])
                attaches = f"\n**Attachments:** `{links}`"
            self.emit_log(f"**ANALYSIS: User {msg.author}'s message at `{msgtime}` in {msg.channel.mention}"
                          f" was deleted. ANALYSIS: Contents:**\n{contents}{attaches}")

            self.logger.info(f"{msg.author}'s message at {msgtime} in {msg.channel} of {msg.guild} was deleted:\n"
                             f"Contents:\n{contents}{attaches.replace('**','')}")

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        blacklist = self.config["log_event_blacklist"]
        if "message_edit" not in blacklist and after.author != self.client.user:
            old_contents, _ = close_markdown(before.clean_content)
            contents, _ = close_markdown(after.clean_content)
            if old_contents == contents:
                return
            msgtime = after.created_at.strftime("%Y-%m-%d @ %H:%M:%S")
            self.emit_log(f"**ANALYSIS: User {after.author} edited their message at `{msgtime}` in "
                          f"{after.channel.mention}. ANALYSIS:**\n**Old contents:** {old_contents}\n"
                          f"**New contents:** {contents}")

            self.logger.info(f"User {after.author} edited their message "
                             f"at {msgtime} in {after.channel} of {after.guild}.\n"
                             f"Old contents:\n{old_contents}\nNew contents:\n{contents}")

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        blacklist = self.config["log_event_blacklist"]
        if "member_update" not in blacklist:
            diff_str = log_str = ""
            if before.name != after.name or before.discriminator != after.discriminator:
                diff_str = f"`Old username: `{before}\n`New username: `{after}\n"
                log_str = f"Old username: {before}\nNew username: {after}\n"
            if before.avatar != after.avatar:
                diff_str = f"{diff_str}`New avatar: `{after.avatar.url}\n"
                log_str = f"{log_str}New avatar: {after.avatar.url}\n"
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
            self.emit_log(f"**ANALYSIS: User {after} was modified:**\n{diff_str}")
            self.logger.info(f"User {after} was modified:\n{log_str}")

    async def on_guild_channel_pins_update(self, channel: discord.TextChannel, last_pin: datetime.datetime):
        blacklist = self.config["log_event_blacklist"]
        if "pin_update" not in blacklist:
            cnt = None
            try:
                new_pin = (discord.utils.utcnow() - last_pin < datetime.timedelta(seconds=5))
            except TypeError:  # last_pin can be None if the last pin in a channel was unpinned
                new_pin = False
            if new_pin:  # Get the pinned message if it's a new pin; can't get the unpinned messages sadly
                msg = (await channel.pins())[0]
                cnt = msg.author, msg.clean_content
            self.emit_log(f"**ANALYSIS: A message was {'' if new_pin else 'un'}pinned in {channel.mention}.**\n"
                          f"{f'**Message: {cnt[0]}:** {cnt[1]}' if new_pin else ''}")
            self.logger.info(f"A message was {'' if new_pin else 'un'}pinned in {channel} of {channel.guild}\n"
                             f"{f'Message: {cnt[0]}: {cnt[1]}' if new_pin else ''}")

    async def on_member_ban(self, guild: discord.Guild, member: discord.Member):
        blacklist = self.config["log_event_blacklist"]
        if "member_ban" not in blacklist:
            self.emit_log(f"**ANALYSIS: User {member} was banned.**")
            self.logger.info(f"User {member} was benned in {guild}.")

    async def on_member_unban(self, guild: discord.Guild, member: discord.Member):
        blacklist = self.config["log_event_blacklist"]
        if "member_unban" not in blacklist:
            self.emit_log(f"**ANALYSIS: Ban was lifted from user {member}.**")
            self.logger.info(f"Ban was lifted from user {member} in {guild}")

    async def on_member_join(self, member: discord.Member):
        blacklist = self.config["log_event_blacklist"]
        if "member_join" not in blacklist:
            self.emit_log(f"**ANALYSIS: User {member} has joined the server. User id: `{member.id}`**")
            self.logger.info(f"User {member} has joined {member.guild}. User id: {member.id}.")

    async def on_member_remove(self, member: discord.Member):
        blacklist = self.config["log_event_blacklist"]
        if "member_leave" not in blacklist:
            try:
                # find audit log entries for kicking of member with our ID, created in last five seconds.
                # Hopefully five seconds is enough
                latest_logs = member.guild.audit_logs(action=discord.AuditLogAction.kick, limit=1)
                kick_event = await discord.utils.get(latest_logs, target__id=member.id)
            except discord.Forbidden:
                kick_event = None
            if kick_event:
                kicker = kick_event.user
                reason_str = f"Reason: {kick_event.reason}; " if kick_event.reason else ""
                self.emit_log(f"**ANALYSIS: User {member} was kicked from the server by {kicker}. "
                              f"{reason_str}User id: `{member.id}`**")
                self.logger.info(f"User {member} was kicked from {member.guild} by {kicker}. "
                                 f"{reason_str}User ud: {member.id}")
            else:
                self.emit_log(f"**ANALYSIS: User {member} has left the server. User id: `{member.id}`**")
                self.logger.info(f"User {member} has left {member.guild}. User id: {member.id}.")

    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        blacklist = self.config["log_event_blacklist"]
        if "role_update" not in blacklist:
            diff = []
            try:
                audit_event = await discord.utils.get(
                        after.guild.audit_logs(action=discord.AuditLogAction.role_update, limit=1))
            except discord.Forbidden:
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
                          f"```\n{diff}```\n")
            self.logger.info(f"Role {before.name} was changed by "
                             f"{audit_event.user if audit_event else 'someone'}:\n"
                             f"{diff}")

    async def on_log_event(self, string: str, *, log_type="log_event"):
        blacklist = self.config["log_event_blacklist"]
        if log_type not in blacklist:
            self.emit_log(string)
            self.logger.info(string)

    def emit_log(self, log_str: str):
        self.log_message_queue.append(log_str)

    @Command("LogEvent",
             doc="Adds or removes the events to be logged.",
             syntax="[add|remove type]",
             category="bot_management",
             perms={"manage_guild"})
    async def _logevent(self, msg: discord.Message):
        cfg = self.config["log_event_blacklist"]
        try:
            action, event_type = msg.clean_content.lower().split(" ", 2)[1:]
            if event_type not in self.log_events:
                await respond(msg, f"**Log event {event_type} does not exist.\n"
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
