import re
from asyncio import sleep
from plugin_manager import BasePlugin
from rs_utils import respond, find_user, RSArgumentParser
from command_dispatcher import Command
import shlex


class AdminCommands(BasePlugin):
    name = "admin_commands"

    @Command("Purge", "Prune",
             doc="Purges messages from the channel in bulk.\nUse -r option for regexp match filtering.\nWARNING: "
                 "some special characters such as \"\\\" may need to be escaped - eg, use \"\\\\\" or wrap match "
                 "into quotation marks instead.",
             syntax="(count) [match] [-u/--user mention/ID/Name] [-r/--regex] [-v/--verbose] [-e/--emulate/--dryrun]",
             run_anywhere=True,
             perms={"manage_messages"},
             category="admin")
    async def _tpurge(self, msg):

        parser = RSArgumentParser()
        parser.add_argument("command")
        parser.add_argument("count", type=int)
        parser.add_argument("match", default=False, nargs='*')
        parser.add_argument("-r", "--regex", action="store_true")
        parser.add_argument("-u", "--user", action="append")
        parser.add_argument("-v", "--verbose", action="store_true")
        parser.add_argument("-e", "--emulate", "--dryrun", action="store_true")

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

        await msg.delete()

        if not args['emulate']:
            # actual purging
            deleted = await msg.channel.purge(limit=args['count'],
                                              check=((lambda x: self.rsearch(x, args['match'], members)) if
                                                     args['regex'] else
                                                     (lambda x: self.search(x, args['match'], members))))
        else:
            # dry run to test your query
            deleted = []
            check = ((lambda x: self.rsearch(x, args['match'], members)) if args['regex'] else
                     (lambda x: self.search(x, args['match'], members)))
            async for m in msg.channel.history(limit=args['count']):
                if check(m):
                    deleted.append(m)

        # if you REALLY want those messages
        if args['verbose']:
            await self.plugin_manager.hook_event("on_log_event", msg.guild,
                                                 "**WARNING: Beginning verbose purge dump.**",
                                                 log_type="purge_event")
            for d in deleted[::-1]:
                await self.plugin_manager.hook_event("on_log_event", msg.guild,
                                                     f"{d.author}({d.author.id}) @ {d.created_at}:\n{d.content}",
                                                     log_type="purge_event")
            await self.plugin_manager.hook_event("on_log_event", msg.guild,
                                                 "**Verbose purge dump complete.**",
                                                 log_type="purge_event")

        fb = await respond(msg, f"**PURGE COMPLETE: {len(deleted)} messages purged.**" +
                           (f"\n**Purge query: **{args['match']}" if args['match'] else ""))
        await sleep(5)
        await fb.delete()

    @staticmethod
    def search(msg, searchstr, members=list()):
        return ((not searchstr) or (searchstr.lower() in msg.content.lower())) and \
               ((msg.author.id in members) or not members)

    @staticmethod
    def rsearch(msg, searchstr, members=list()):
        return ((not searchstr) or re.match(searchstr.lower(), msg.content.lower())) and \
               ((msg.author.id in members) or not members)
