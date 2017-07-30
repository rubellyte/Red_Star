import urllib
import re
import asyncio
from discord import InvalidArgument
from plugin_manager import BasePlugin
from utils import Command, respond


class AdminCommands(BasePlugin):
    name = "admin_commands"

    def activate(self):
        pass

    @Command("test")
    async def _test_command(self, data):
        await respond(self.client, data, "**AFFIRMATIVE. Confirming test, <usermention>.**")

    @Command("shutdown",
             perms={"manage_server"})
    async def _shutdown(self, data):
        await respond(self.client, data, "**AFFIRMATIVE. SHUTTING DOWN.**")
        raise SystemExit

    @Command("update_avatar",
             syntax="(URL)",
             perms={"manage_server"})
    async def _update_avatar(self, data):
        url = " ".join(data.content.split()[1:])
        if url:
            try:
                img = urllib.request.urlopen(url).read()
                await self.client.edit_profile(avatar=img)
                await respond(self.client, data, "**AVATAR UPDATED.**")
            except (urllib.request.URLError, ValueError) as e:
                self.logger.debug(e)
                await respond(self.client, data, "**WARNING: Invalid URL provided.**")
            except InvalidArgument:
                await respond(self.client, data, "**NEGATIVE. Image must be a PNG or JPG.**")
        else:
            await respond(self.client, data, "**NEGATIVE. No URL provided.**")

    @Command("purge",
             syntax="(count) [match]",
             perms={"manage_messages"})
    async def _purge(self, data):
        cnt = data.content.split()
        try:
            count = int(cnt[1])
            if count > 250:
                count = 250
            elif count < 0:
                raise ValueError
        except ValueError:
            raise SyntaxError
        if len(cnt) > 2:
            self.searchstr = " ".join(cnt[2:])
        else:
            self.searchstr = ""
        await self.client.delete_message(data)
        deleted = await self.client.purge_from(
            data.channel, limit=count, check=self.search)
        self.searchstr = ""
        fb = await respond(self.client, data, "**PURGE COMPLETE: {} messages purged.**".format(len(deleted)))
        await asyncio.sleep(5)
        await self.client.delete_message(fb)

    def search(self, data):
        if self.searchstr:
            if self.searchstr.startswith("re:"):
                search = self.searchstr[3:]
                self.logger.debug(search)
                return re.match(search, data.content)
            else:
                return self.searchstr in data.content
        else:
            return True
