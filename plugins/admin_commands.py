import re
from asyncio import sleep
from plugin_manager import BasePlugin
from utils import Command, respond, find_user
import shlex


class AdminCommands(BasePlugin):
    name = "admin_commands"

    @Command("purge", "prune",
             doc="Purges messages from the channel in bulk.",
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
            raise SyntaxError("No count to delete provided.")
        except ValueError:
            raise SyntaxError("Count to delete is not a valid number.")
        if len(args) > 2:
            searchstr = args[2]
        else:
            searchstr = None
        members = []
        if len(args) > 3:
            for s in args[3:]:
                members.append(find_user(msg.guild, s))
        await msg.delete()
        deleted = await msg.channel.purge(limit=count, check=lambda x: self.search(x, searchstr, members))
        fb = await respond(msg, f"**PURGE COMPLETE: {len(deleted)} messages purged.**")
        await sleep(5)
        await fb.delete()

    @staticmethod
    def search(msg, searchstr, members=None):
        if searchstr:
            if searchstr.startswith("re:"):
                search = searchstr[3:]
                t_find = re.match(search.lower(), msg.content.lower())
            else:
                t_find = searchstr.lower() in msg.content.lower()
            if members:
                return t_find and msg.author in members
            else:
                return t_find
        else:
            return True

