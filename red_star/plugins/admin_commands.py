import re
import shlex
from discord import NotFound, Forbidden
from red_star.plugin_manager import BasePlugin
from red_star.rs_utils import respond, find_user, RSArgumentParser
from red_star.rs_errors import CommandSyntaxError
from red_star.command_dispatcher import Command


class AdminCommands(BasePlugin):
    name = "admin_commands"
    version = "1.1.1"
    author = "medeor413"
    description = "A plugin that adds useful administrative commands. Currently only features Purge."

    @Command("Purge", "Prune",
             doc="Purges messages from the channel in bulk.\nUse -r option for regexp match filtering.\nWARNING: "
                 "some special characters such as \"\\\" may need to be escaped - eg, use \"\\\\\" or wrap match "
                 "into quotation marks instead.",
             syntax="(count) [match] [-u/--user mention/ID/Name] [-r/--regex] [-v/--verbose] [-e/--emulate/--dryrun]"
                    "[-b/--before message_id] [-a/--after message_id]",
             run_anywhere=True,
             delcall=True,
             perms={"manage_messages"},
             category="admin")
    async def _purge(self, msg):

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
                before_msg = await msg.channel.get_message(args['before'])
            except NotFound:
                raise CommandSyntaxError(f"No message in channel with ID {args['before']}.")
        else:
            before_msg = msg

        if args['after']:
            try:
                after_msg = await msg.channel.get_message(args['after'])
            except NotFound:
                raise CommandSyntaxError(f"No message in channel with ID {args['before']}.")
        else:
            after_msg = None

        def check(check_msg):
            if members and check_msg.author.id not in members:
                return False
            if args.regex:
                return self.match_regex(check_msg, args.match)
            else:
                return self.match_simple(check_msg, args.match)

        if not args['emulate']:
            # actual purging
            if not msg.channel.permissions_for(msg.guild.me).manage_messages:
                raise Forbidden
            deleted = await msg.channel.purge(limit=args['count'], before=before_msg, after=after_msg, check=check)
        else:
            # dry run to test your query
            deleted = [m async for m in msg.channel.history(limit=args['count'], before=before_msg,
                                                            after=after_msg).filter(check)]

        # if you REALLY want those messages
        if args['verbose']:
            await self.plugin_manager.hook_event("on_log_event", msg.guild,
                                                 "**WARNING: Beginning verbose purge dump.**",
                                                 log_type="purge_event")
            for d in deleted[::-1]:
                await self.plugin_manager.hook_event("on_log_event", msg.guild,
                                                     f"`{d.author}({d.author.id}) @ {d.created_at}:`\n{d.content}",
                                                     log_type="purge_event")
            await self.plugin_manager.hook_event("on_log_event", msg.guild,
                                                 "**Verbose purge dump complete.**",
                                                 log_type="purge_event")

        await respond(msg, f"**PURGE COMPLETE: {len(deleted)} messages purged.**" +
                      (f"\n**Purge query: **{args['match']}" if args['match'] else ""), delete_after=5)

    @staticmethod
    def match_simple(msg, searchstr):
        return not searchstr or searchstr.lower() in msg.content.lower()

    @staticmethod
    def match_regex(msg, searchstr):
        return not searchstr or re.match(searchstr.lower(), msg.content.lower())
