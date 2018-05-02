import re
from asyncio import sleep
from plugin_manager import BasePlugin
from rs_errors import CommandSyntaxError
from rs_utils import respond, find_user
from command_dispatcher import Command
import shlex


class AdminCommands(BasePlugin):
    name = "admin_commands"

    @Command("Purge", "Prune", "RPurge", "RPrune",
             doc="Purges messages from the channel in bulk.\nUse R- variant for regexp match filtering.\nWARNING: "
                 "some special characters such as \"\\\" may need to be escaped - eg, use \"\\\\\" or wrap match "
                 "into quotation marks instead.",
             syntax="(count) [match] [user mention/user id/user name]",
             category="admin",
             run_anywhere=True,
             perms={"manage_messages"})
    async def _purge(self, msg):
        args = shlex.split(msg.content)
        try:
            count = int(args[1])
            if count > 250:
                count = 250
            elif count < 0:
                raise ValueError
        except IndexError:
            raise CommandSyntaxError("No count to delete provided.")
        except ValueError:
            raise CommandSyntaxError("Count to delete is not a valid number.")
        if len(args) > 2:
            searchstr = args[2]
        else:
            searchstr = None
        members = []
        if len(args) > 3:
            for s in args[3:]:
                members.append(find_user(msg.guild, s))
        await msg.delete()
        # check if regexp version is used
        args[0] = args[0].lower().endswith('rpurge') or args[0].lower().endswith('rprune')
        deleted = await msg.channel.purge(limit=count,
                                          check=((lambda x: self.rsearch(x, searchstr, members)) if
                                                 args[0] else (lambda x: self.search(x, searchstr, members))))
        fb = await respond(msg, f"**PURGE COMPLETE: {len(deleted)} messages purged.**")
        await sleep(5)
        await fb.delete()

    @staticmethod
    def search(msg, searchstr, members=None):
        if searchstr:
            t_find = searchstr.lower() in msg.content.lower()
            if members:
                return t_find and msg.author in members
            else:
                return t_find
        else:
            return True

    @staticmethod
    def rsearch(msg, searchstr, members=None):
        if searchstr:
            t_find = re.match(searchstr.lower(), msg.content.lower())
            if members:
                return t_find and msg.author in members
            else:
                return t_find
        else:
            return True
