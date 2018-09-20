from datetime import datetime, timedelta
from discord import AuditLogAction
from red_star.plugin_manager import BasePlugin
from red_star.rs_errors import ChannelNotFoundError, CommandSyntaxError
from red_star.rs_utils import split_message, respond
from red_star.command_dispatcher import Command


class DiscordLogger(BasePlugin):
    name = "logger"
    version = "1.3"
    author = "medeor413, GTG3000"
    description = "A plugin that logs certain events and prints them to a defined log channel " \
                  "in an easily-readable manner."
    default_config = {
        "default": {
            "log_event_blacklist": [
            ]
        }
    }

    async def activate(self):
        self.log_items = {}

    async def on_global_tick(self, *_):
        for guild in self.client.guilds:
            gid = str(guild.id)
            try:
                logchan = self.channel_manager.get_channel(guild, "logs")
            except ChannelNotFoundError:
                continue
            if gid in self.log_items and self.log_items[gid]:
                logs = "\n".join(self.log_items[gid])
                for msg in split_message(logs, splitter="\n"):
                    await logchan.send(msg)
                self.log_items[gid].clear()

    async def on_message_delete(self, msg):
        gid = str(msg.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "message_delete" not in self.plugin_config[gid]["log_event_blacklist"] and msg.author != self.client.user:
            user_name = str(msg.author)
            contents = msg.clean_content if msg.clean_content else msg.system_content
            msgtime = msg.created_at.strftime("%Y-%m-%d @ %H:%M:%S")
            attaches = ""
            if msg.attachments:
                links = ", ".join([x.url for x in msg.attachments])
                attaches = f"\n**Attachments:** `{links}`"
            self.logger.debug(f"User {user_name}'s message at {msgtime} in {msg.channel.name} of {msg.guild.name} was "
                              f"deleted.\nContents: {contents}\nAttachments: {links}")
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**WARNING: User {user_name}'s message at `{msgtime}` in {msg.channel.mention}"
                                       f" was deleted. ANALYSIS: Contents:**\n{contents}{attaches}")

    async def on_message_edit(self, before, after):
        gid = str(after.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "message_edit" not in self.plugin_config[gid]["log_event_blacklist"] and after.author != self.client.user:
            old_contents = before.clean_content
            contents = after.clean_content
            if old_contents == contents:
                return
            msgtime = after.created_at.strftime("%Y-%m-%d @ %H:%M:%S")
            user_name = str(after.author)
            self.logger.debug(f"User {user_name} edited their message at {msgtime} in {after.channel.name} of "
                              f"{after.guild.name}. \n"
                              f"Old contents: {old_contents}\nNew contents: {contents}")
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**WARNING: User {user_name} edited their message at `{msgtime}` in "
                                       f"{after.channel.mention}. ANALYSIS:**\n"
                                       f"**Old contents:** {old_contents}\n**New contents:** {contents}")

    async def on_member_update(self, before, after):
        gid = str(after.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "member_update" not in self.plugin_config[gid]["log_event_blacklist"]:
            discord_string = ""
            console_string = ""
            if before.name != after.name or before.discriminator != after.discriminator:
                discord_string = f"{discord_string}`Old username: `{before}\n`New username: `{after}\n"
                console_string = f"{discord_string}Old username: {before} New username: {after}\n"
            if before.avatar != after.avatar:
                discord_string = f"{discord_string}`New avatar: `{after.avatar_url}\n"
                console_string = f"{discord_string}New avatar: {after.avatar_url}\n"
            if before.nick != after.nick:
                discord_string = f"{discord_string}`Old nick: `{before.nick}\n`New nick: `{after.nick}\n"
                console_string = f"{discord_string}Old nick: {before.nick} New nick: {after.nick}\n"
            if before.roles != after.roles:
                old_roles = ", ".join([str(x) for x in before.roles])
                new_roles = ", ".join([str(x) for x in after.roles])
                discord_string = f"{discord_string}**Old roles:**```[ {old_roles} ]```\n" \
                                 f"**New roles:**```[ {new_roles} ]```\n"
                console_string = f"{discord_string}Old roles: [ {old_roles} ]\nNew roles:[ {new_roles} ]\n"
            if discord_string == "":
                return
            self.logger.debug(f"User {after} was modified:\n{console_string}")
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**ANALYSIS: User {after} was modified:**\n{discord_string}")

    async def on_guild_channel_pins_update(self, channel, last_pin):
        gid = str(channel.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "guild_channel_pins_update" not in self.plugin_config[gid]["log_event_blacklist"]:
            try:
                new_pin = (datetime.utcnow() - last_pin < timedelta(seconds=5))
            except TypeError:  # last_pin can be None if the last pin in a channel was unpinned
                new_pin = False
            if new_pin:  # Get the pinned message if it's a new pin; can't get the unpinned messages sadly
                msg = (await channel.pins())[0]
                pin_contents = f"\n**Message: {str(msg.author)}:** {msg.clean_content}"
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.log_items[gid].append(f"**ANALYSIS: A message was {'' if new_pin else 'un'}pinned in "
                                       f"{channel.mention}.**{pin_contents if new_pin else ''}")

    async def on_member_ban(self, guild, member):
        gid = str(guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "on_member_ban" not in self.plugin_config[gid]["log_event_blacklist"]:
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.logger.info(f"User {member} was banned on server {member.guild}")
            self.log_items[gid].append(f"**ANALYSIS: User {member} was banned.**")

    async def on_member_unban(self, guild, member):
        gid = str(guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "on_member_unban" not in self.plugin_config[gid]["log_event_blacklist"]:
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.logger.info(f"User {member} was unbanned on server {member.guild}")
            self.log_items[gid].append(f"**ANALYSIS: Ban was lifted from user {member}.**")

    async def on_member_join(self, member):
        gid = str(member.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "on_member_join" not in self.plugin_config[gid]["log_event_blacklist"]:
            if gid not in self.log_items:
                self.log_items[gid] = []
            self.logger.info(f"User {member} has joined server {member.guild}")
            self.log_items[gid].append(f"**ANALYSIS: User {member} has joined the server. User id: `{member.id}`**")

    async def on_member_remove(self, member):
        gid = str(member.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "on_member_remove" not in self.plugin_config[gid]["log_event_blacklist"]:
            t_time = datetime.utcnow()
            # find audit log entries for kicking of member with our ID, created in last five seconds.
            # Hopefully five seconds is enough
            kicker = [f"{str(log_item.user)} for reasons: {log_item.reason or 'None'}"
                      async for log_item in member.guild.audit_logs(action=AuditLogAction.kick)
                      if log_item.target.id == member.id and (t_time - log_item.created_at < timedelta(seconds=5))]
            if gid not in self.log_items:
                self.log_items[gid] = []
            if kicker:
                self.logger.info(f"User {member} ({member.id}) was kicked by {kicker[0]} from {str(member.guild)}.")
                self.log_items[gid].append(f"**ANALYSIS: User {str(member)} was kicked from the server by {kicker[0]}."
                                           f" User id: `{member.id}`**")
            else:
                self.logger.info(f"User {member} ({member.id}) left {str(member.guild)}.")
                self.log_items[gid].append(f"**ANALYSIS: User {str(member)} has left the server. "
                                           f"User id: `{member.id}`**")

    async def on_guild_role_update(self, before, after):
        gid = str(before.guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if "on_guild_role_update" not in self.plugin_config[gid]["log_event_blacklist"]:
            if gid not in self.log_items:
                self.log_items[gid] = []
            diff = []
            audit_event = [log_item async for log_item in after.guild.audit_logs(action=AuditLogAction.role_update) if
                           log_item.target.id == after.id and
                           (datetime.utcnow() - log_item.created_at < timedelta(seconds=5))]

            if audit_event:
                editor_user = str(audit_event[0].user)
            else:
                editor_user = "Unknown"

            if before == after:
                if audit_event:
                    before_dict = audit_event[0].changes.before.__dict__
                    before.name = before_dict.get("name", after.name)
                    before.colour = before_dict.get("colour", after.colour)
                    before.hoist = before_dict.get("hoist", after.hoist)
                    before.mentionable = before_dict.get("mentionable", after.mentionable)
                    before.permissions = before_dict.get("permissions", after.permissions)
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
                before_perms = {x: y for x, y in before.permissions}
                after_perms = {x: y for x, y in after.permissions}
                perm_diff = "Added permissions: " + ", ".join([x.upper() for x, y in after.permissions if y and not
                before_perms[x]])
                perm_diff = perm_diff + "\nRemoved permissions: " \
                            + ", ".join([x.upper() for x, y in before.permissions if y and not after_perms[x]])
                diff.append(perm_diff)
            diff = '\n'.join(diff)
            result = f"**ANALYSIS: Role {before.name} was changed by {editor_user}:**```\n{diff}```"
            self.logger.info(f"Role {before.name} of {str(before.guild)} was changed by {editor_user}:\n{diff}")
            self.log_items[gid].append(result)

    async def on_log_event(self, guild, string, *, log_type="log_event"):
        gid = str(guild.id)
        if gid not in self.plugin_config:
            self.plugin_config[gid] = self.plugin_config["default"]
        if log_type not in self.plugin_config[gid]["log_event_blacklist"]:
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
        cfg = self.plugin_config[gid]["log_event_blacklist"]
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
