import urllib
from plugin_manager import BasePlugin
from utils import Command, respond
from discord import InvalidArgument

class BotManagement(BasePlugin):
    name = "bot_management"

    @Command("shutdown",
             doc="Shuts down the bot.",
             syntax="N/A",
             category="bot_management",
             perms={"manage_server"})
    async def _shutdown(self, data):
        await respond(self.client, data, "**AFFIRMATIVE. SHUTTING DOWN.**")
        await self.client.stop_bot()

    @Command("update_avatar",
             doc="Updates the bot's avatar.",
             syntax="(URL)",
             category="bot_management",
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
            raise SyntaxError("No URL provided.")

    @Command("activate",
             doc="Activates an inactive plugin.",
             syntax="(plugin)",
             category="bot_management",
             perms={"manage_server"})
    async def _activate(self, data):
        plgname = " ".join(data.content.split()[1:]).lower()
        all_plugins = self.plugin_manager.plugins
        if plgname in all_plugins:
            if plgname not in self.plugins:
                await self.plugin_manager.activate(plgname)
                await respond(self.client, data, f"**ANALYSIS: Plugin {plgname} was activated successfully.**")
            else:
                await respond(self.client, data, f"**ANALYSIS: Plugin {plgname} is already activated.**")
        else:
            await respond(self.client, data, f"**WARNING: Could not find plugin {plgname}.**")

    @Command("deactivate",
             doc="Deactivates an active plugin.",
             syntax="(plugin)",
             category="bot_management",
             perms={"manage_server"})
    async def _deactivate(self, data):
        plgname = " ".join(data.content.split()[1:]).lower()
        if plgname == self.name:
            await respond(self.client, data, f"**WARNING: Cannot deactivate {self.name}.**")
        elif plgname in self.plugins:
            await self.plugin_manager.deactivate(plgname)
            await respond(self.client, data, f"**ANALYSIS: Plugin {plgname} was deactivated successfully.**")
        else:
            await respond(self.client, data, f"**ANALYSIS: Plugin {plgname} is not active.**")

    @Command("list_plugins",
             doc="Lists all plugins and their activation status.",
             syntax="(plugin)",
             category="bot_management",
             perms={"manage_server"})
    async def _list_plugins(self, data):
        active_plgs = ", ".join(self.plugins.keys())
        if not active_plgs:
            active_plgs = "None."
        all_plgs = list(self.plugin_manager.plugins.keys())
        inactive_plgs = ", ".join([x for x in all_plgs if x not in self.plugins])
        if not inactive_plgs:
            inactive_plgs = "None."
        await respond(self.client, data, f"**ANALYSIS: Plugins are as follows:**```\nActive: {active_plgs}\n"
                                         f"Inactive: {inactive_plgs}\n```")