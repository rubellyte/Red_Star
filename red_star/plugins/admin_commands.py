import re
import shlex
import discord
from red_star.plugin_manager import BasePlugin
from red_star.rs_utils import respond, find_user, RSArgumentParser, prompt_for_confirmation
from red_star.rs_errors import CommandSyntaxError
from red_star.command_dispatcher import Command


class AdminCommands(BasePlugin):
    name = "admin_commands"
    version = "1.1.1"
    author = "medeor413"
    description = "A plugin that adds useful administrative commands. Currently only features Purge."
    log_events = {"purge_event"}

    @Command("Purge", "Prune",
             doc="Purges messages from the channel in bulk.\nUse -r option for regexp match filtering.\nWARNING: "
                 "some special characters such as \"\\\" may need to be escaped - eg, use \"\\\\\" or wrap match "
                 "into quotation marks instead.",
             syntax="(count) [match] [-u/--user mention/ID/Name] [-r/--regex] [-v/--verbose] [-e/--emulate/--dryrun]"
                    "[-b/--before message_id] [-a/--after message_id]",
             run_anywhere=True,
             delete_call=True,
             perms={"manage_messages"},
             category="admin")
    async def _purge(self, msg: discord.Message):

        parser = RSArgumentParser()
        parser.add_argument("command")
        parser.add_argument("count", type=int)
        parser.add_argument("match", default=False, nargs='*')
        parser.add_argument("-r", "--regex", action="store_true")
        parser.add_argument("-u", "--user", action="append")
        parser.add_argument("-v", "--verbose", action="store_true")
        parser.add_argument("-e", "--emulate", "--dryrun", action="store_true")
        parser.add_argument("-b", "--before", type=int, default=None)
        parser.add_argument("-a", "--after", type=int, default=None)

        args = parser.parse_args(shlex.split(msg.content))

        if not 0 < args.count <= 250:
            raise CommandSyntaxError("Count must be between 1 and 250.")

        if args['match']:
            args['match'] = ' '.join(args['match'])

        # find all possible members mentioned
        members = []
        if args['user']:
            for q in args['user']:
                u = find_user(msg.guild, q)
                if u:
                    members.append(u.id)

        if args['before']:
            try:
                before_msg = await msg.channel.fetch_message(args['before'])
            except discord.NotFound:
                raise CommandSyntaxError(f"No message in channel with ID {args['before']}.")
        else:
            before_msg = msg

        if args['after']:
            try:
                after_msg = await msg.channel.fetch_message(args['after'])
            except discord.NotFound:
                raise CommandSyntaxError(f"No message in channel with ID {args['before']}.")
        else:
            after_msg = None

        def check(check_msg: discord.Message):
            if members and check_msg.author.id not in members:
                return False
            if args.regex:
                return self.match_regex(check_msg, args.match)
            else:
                return self.match_simple(check_msg, args.match)

        deleted = [message async for message in msg.channel.history(limit=args['count'], before=before_msg,
                                                                    after=after_msg) if check(message)]
        if not args['emulate'] and len(deleted) > 0:
            # actual purging
            prompt_text = f"You are about to delete {len(deleted)} messages. Continue?"
            confirmed = await prompt_for_confirmation(msg, prompt_text=prompt_text)
            if not confirmed:
                return
            if not msg.channel.permissions_for(msg.guild.me).manage_messages:
                raise discord.Forbidden
            deleted = await msg.channel.purge(limit=args['count'], before=before_msg, after=after_msg, check=check)

        # if you REALLY want those messages
        if args['verbose']:
            await self.plugin_manager.hook_event("on_log_event",
                                                 "**WARNING: Beginning verbose purge dump.**",
                                                 log_type="purge_event")
            for d in deleted[::-1]:
                await self.plugin_manager.hook_event("on_log_event",
                                                     f"`{d.author}({d.author.id}) @ {d.created_at}:`\n{d.content}",
                                                     log_type="purge_event")
            await self.plugin_manager.hook_event("on_log_event",
                                                 "**Verbose purge dump complete.**",
                                                 log_type="purge_event")

        await respond(msg, f"**PURGE COMPLETE: {len(deleted)} messages purged.**" +
                      (f"\n**Purge query: **{args['match']}" if args['match'] else ""), delete_after=5)

    @staticmethod
    def match_simple(msg: discord.Message, search_substr: str):
        return not search_substr or search_substr.lower() in msg.content.lower()

    @staticmethod
    def match_regex(msg: discord.Message, search_substr: str):
        return not search_substr or re.match(search_substr.lower(), msg.content.lower())
