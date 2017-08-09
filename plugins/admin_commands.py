import re
from asyncio import sleep
from plugin_manager import BasePlugin
from utils import Command, respond, find_user


class AdminCommands(BasePlugin):
    name = "admin_commands"

    @Command("purge",
             doc="Purges messages from the channel in bulk.",
             syntax="(count) [match]",
             category="admin",
             run_anywhere=True,
             perms={"manage_messages"})
    async def _purge(self, msg):
        cnt = msg.content.split()
        try:
            count = int(cnt[1])
            if count > 250:
                count = 250
            elif count < 0:
                raise ValueError
        except IndexError:
            raise SyntaxError("No count to delete provided.")
        except ValueError:
            raise SyntaxError("Count to delete is not a valid number.")
        if len(cnt) > 2:
            searchstr = " ".join(cnt[2:])
        else:
            searchstr = ""
        await msg.delete()
        deleted = await msg.channel.purge(limit=count, check=lambda x: self.search(x, searchstr))
        fb = await respond(msg, f"**PURGE COMPLETE: {len(deleted)} messages purged.**")
        await sleep(5)
        await fb.delete()

    def search(self, msg, searchstr):
        if searchstr:
            if searchstr.startswith("re:"):
                search = searchstr[3:]
                return re.match(search, msg.content)
            elif searchstr.startswith("author:"):
                search = searchstr[7:]
                return find_user(msg.guild, search) == msg.author
            else:
                return searchstr in msg.content
        else:
            return True
