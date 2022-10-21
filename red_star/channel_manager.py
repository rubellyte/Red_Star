from __future__ import annotations
from red_star.rs_errors import ChannelNotFoundError

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import discord
    from red_star.client import RedStar


class ChannelManager:
    channel_types = {"commands"}
    channel_categories = {"no_read"}

    def __init__(self, client: RedStar, guild: discord.Guild):
        self.client = client
        self.guild = guild
        self.config_manager = client.config_manager
        self.default_config = {
            "channels": {},
            "categories": {}
        }
        self.conf = self.config_manager.get_plugin_config_file("channel_manager.json", self.guild)

        if not self.conf:
            self.conf = {
                "channels": {i: None for i in self.channel_types},
                "categories": {i: [] for i in self.channel_categories}
            }

        if not set(self.conf["channels"].keys()) >= self.channel_types:
            defaults_added_dict = {x: None for x in self.channel_types}.update(self.conf["channels"])
            self.conf["channels"] = defaults_added_dict
        if not set(self.conf["categories"].keys()) >= self.channel_categories:
            defaults_added_dict = {x: [] for x in self.channel_categories}.update(self.conf["categories"])
            self.conf["categories"] = defaults_added_dict

    def get_channel(self, chantype: str):
        chantype = chantype.lower()
        chan = self.guild.get_channel(self.conf["channels"][chantype])
        if not chan:
            raise ChannelNotFoundError(chantype)
        return chan

    def set_channel(self, chantype: str, channel: discord.abc.GuildChannel):
        chantype = chantype.lower()
        if channel:
            self.conf["channels"][chantype] = channel.id
        else:
            self.conf["channels"][chantype] = None

    def get_category(self, category: str):
        return self.conf["categories"].get(category.lower())

    def channel_in_category(self, category: str, channel: discord.abc.GuildChannel):
        return channel in self.conf["categories"].get(category.lower(), {})

    def add_channel_to_category(self, category: str, channel: discord.abc.GuildChannel):
        category = self.conf["categories"].setdefault(category.lower(), [])
        if channel.id not in category:
            category.append(channel.id)
            return True
        else:
            return False

    def remove_channel_from_category(self, category: str, channel: discord.abc.GuildChannel):
        category = category.lower()
        if self.channel_in_category(category, channel):
            self.conf["categories"][category].remove(channel.id)
            return True
        else:
            return False
