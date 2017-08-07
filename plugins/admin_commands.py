import re
import asyncio
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
    async def _purge(self, data):
        cnt = data.content.split()
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
        await self.client.delete_message(data)
        deleted = await self.client.purge_from(
            data.channel, limit=count, check=lambda x: self.search(x, searchstr))
        self.searchstr = ""
        fb = await respond(self.client, data, f"**PURGE COMPLETE: {len(deleted)} messages purged.**")
        await asyncio.sleep(5)
        await self.client.delete_message(fb)

    def search(self, msg, searchstr):
        if searchstr:
            if searchstr.startswith("re:"):
                search = searchstr[3:]
                return re.match(search, msg.content)
            elif searchstr.startswith("author:"):
                search = searchstr[7:]
                return find_user(msg.server, search) == msg.author
            else:
                return searchstr in msg.content
        else:
            return True
