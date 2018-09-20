import re
import shlex
from discord import NotFound
from red_star.plugin_manager import BasePlugin
from red_star.rs_utils import respond, find_user, RSArgumentParser
from red_star.rs_errors import CommandSyntaxError
from red_star.command_dispatcher import Command


class AdminCommands(BasePlugin):
    name = "admin_commands"

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

        # Clamp the count. No negatives (duh), not more than 250 (don't get trigger happy)
        args['count'] = min(max(args['count'], 0), 250)

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

        if not args['emulate']:
            # actual purging
            deleted = await msg.channel.purge(limit=args['count'], before=before_msg, after=after_msg,
                                              check=((lambda x: self.rsearch(x, args['match'], members)) if
                                                     args['regex'] else
                                                     (lambda x: self.search(x, args['match'], members))))
        else:
            # dry run to test your query
            deleted = []
            check = ((lambda x: self.rsearch(x, args['match'], members)) if args['regex'] else
                     (lambda x: self.search(x, args['match'], members)))
            async for m in msg.channel.history(limit=args['count'], before=before_msg, after=after_msg):
                if check(m):
                    deleted.append(m)

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
    def search(msg, searchstr, members=None):
        if not members:
            members = []
        return ((not searchstr) or (searchstr.lower() in msg.content.lower())) and \
               ((msg.author.id in members) or not members)

    @staticmethod
    def rsearch(msg, searchstr, members=None):
        if not members:
            members = []
        return ((not searchstr) or re.match(searchstr.lower(), msg.content.lower())) and \
               ((msg.author.id in members) or not members)
