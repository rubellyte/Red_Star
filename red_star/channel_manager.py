from __future__ import annotations
from red_star.rs_errors import ChannelNotFoundError

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import discord
    from red_star.client import RedStar


class ChannelManager:
    def __init__(self, client: RedStar):
        self.client = client
        self.config_manager = client.config_manager
        self.conf = self.config_manager.get_plugin_config_file("channel_manager.json")
        self.channel_types = {"commands"}
        self.channel_categories = {"no_read"}
        if "channel_manager" in self.config_manager.config:  # Port from the old config.json storage
            self.conf.update(self.config_manager.config["channel_manager"])
            del self.config_manager.config["channel_manager"]
            self.config_manager.save_config()
        self.default_config = {
            "channels": {},
            "categories": {}
        }

    def add_guild(self, gid: str):
        if gid not in self.conf:
            self.client.logger.info(f"Registered new guild: {gid}")
            self.conf[gid] = self.default_config.copy()
        guild_conf = self.conf[gid]
        new_channels = {i: None for i in self.channel_types}
        new_channels.update(guild_conf["channels"])
        guild_conf["channels"] = new_channels
        new_categories = {i: [] for i in self.channel_categories}
        new_categories.update(guild_conf["categories"])
        guild_conf["categories"] = new_categories
        self.conf.save()

    def get_channel(self, guild: discord.Guild, chantype: str):
        gid = str(guild.id)
        chantype = chantype.lower()
        chan = self.conf[gid]["channels"][chantype]
        chan = self.client.get_channel(chan)
        if not chan:
            raise ChannelNotFoundError(chantype)
        return chan

    def set_channel(self, guild: discord.Guild, chantype: str, channel: discord.abc.GuildChannel):
        gid = str(guild.id)
        chantype = chantype.lower()
        if channel:
            self.conf[gid]["channels"][chantype] = channel.id
        else:
            self.conf[gid]["channels"][chantype] = None
        self.conf.save()

    def get_category(self, guild: discord.Guild, category: str):
        guild_categories = self.conf[str(guild.id)]["categories"]
        if category.lower() in guild_categories:
            return guild_categories[category.lower()]
        else:
            return None

    def channel_in_category(self, guild: discord.Guild, category: str, channel: discord.abc.GuildChannel):
        guild_categories = self.conf[str(guild.id)]["categories"]
        if category.lower() not in guild_categories:
            return False
        if channel.id not in guild_categories[category.lower()]:
            return False
        return True

    def add_channel_to_category(self, guild: discord.Guild, category: str, channel: discord.abc.GuildChannel):
        category = self.conf[str(guild.id)]["categories"].setdefault(category.lower(), [])
        if channel.id not in category:
            category.append(channel.id)
            self.conf.save()
            return True
        else:
            return False

    def remove_channel_from_category(self, guild: discord.Guild, category: str, channel: discord.abc.GuildChannel):
        gid = str(guild.id)
        category = category.lower()
        if self.channel_in_category(guild, category, channel):
            self.conf[gid]["categories"][category].remove(channel.id)
            self.conf.save()
            return True
        else:
            return False
