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
    def _test_command(self, data):
        yield from respond(self.client, data, "**Test confirmed, <usermention>.**")

    @Command("shutdown",
             perms={"manage_server"})
    def _shutdown(self, data):
        yield from respond(self.client, data, "**Shutting down.**")
        raise SystemExit

    @Command("update_avatar",
             syntax="(URL)",
             perms={"manage_server"})
    def _update_avatar(self, data):
        url = " ".join(data.content.split()[1:])
        if url:
            try:
                img = urllib.request.urlopen(url).read()
                yield from self.client.edit_profile(avatar=img)
                yield from respond(self.client, data, "**Avatar updated.**")
            except (urllib.request.URLError, ValueError) as e:
                self.logger.debug(e)
                yield from respond(self.client, data, "**Invalid URL provided.**")
            except InvalidArgument:
                yield from respond(self.client, data, "**Image must be a PNG or JPG.**")
        else:
            yield from respond(self.client, data, "**No URL provided.**")

    @Command("purge",
             syntax="(count) [match]",
             perms={"manage_messages"},
             delcall=True)
    def _purge(self, data):
        cnt = data.content.split()
        try:
            count = int(cnt[1])
            if count > 250:
                count = 250
        except ValueError:
            count = 100
        if len(cnt) > 2:
            self.searchstr = " ".join(cnt[2:])
        else:
            self.searchstr = ""
        deleted = yield from self.client.purge_from(
            data.channel, limit=count, check=self.search)
        self.searchstr = ""
        fb = yield from respond(self.client, data,
            "**PURGE COMPLETE: purged {} messages.**"
            .format(len(deleted)))
        yield from asyncio.sleep(5)
        yield from self.client.delete_message(fb)

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