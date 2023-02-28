from __future__ import annotations

import json
import logging

from red_star.rs_errors import ChannelNotFoundError

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import discord
    from red_star.client import RedStar


class ChannelManager:
    name = "channel_manager"
    channel_types = {"commands"}
    channel_categories = {"no_read"}

    def __init__(self, client: RedStar, guild: discord.Guild):
        self.client = client
        self.guild = guild
        self.logger = logging.getLogger(f"red_star.{self.name}.{guild.id}")
        self.config_manager = client.config_manager
        self.default_config = {
            "channels": {},
            "categories": {}
        }
        self.storage_file = self.config_manager.get_plugin_storage(self)

        self._port_old_storage()

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
        self.storage_file.save()

    @property
    def conf(self):
        return self.storage_file.contents

    @conf.setter
    def conf(self, value):
        self.storage_file.contents = value

    def _port_old_storage(self):
        old_storage_path = self.config_manager.config_path / "channel_manager.json"
        if old_storage_path.exists():
            with old_storage_path.open(encoding="utf-8") as fp:
                old_storage = json.load(fp)
            for guild_id, channel_data in old_storage.items():
                try:
                    new_storage = self.config_manager.storage_files[guild_id][self.name]
                except KeyError:
                    self.logger.warning(f"Server with ID {guild_id} not found! Is the bot still in this server?\n"
                                        f"Skipping conversion of this server's channel manager storage...")
                    continue
                new_storage.contents = channel_data
                new_storage.save()
                new_storage.load()
            old_storage_path = old_storage_path.replace(old_storage_path.with_suffix(".json.old"))
            self.logger.info(f"Old channel manager storage converted to new format. "
                             f"Old data now located at {old_storage_path} - you may delete this file.")

    def storage_save_args(self):
        return {}

    def storage_load_args(self):
        return {}

    def get_channel(self, channel_type: str):
        channel_type = channel_type.lower()
        chan = self.guild.get_channel(self.conf["channels"][channel_type])
        if not chan:
            raise ChannelNotFoundError(channel_type)
        return chan

    def set_channel(self, channel_type: str, channel: discord.abc.GuildChannel):
        channel_type = channel_type.lower()
        if channel:
            self.conf["channels"][channel_type] = channel.id
        else:
            self.conf["channels"][channel_type] = None
        self.storage_file.save()

    def get_category(self, category: str):
        return self.conf["categories"].get(category.lower())

    def channel_in_category(self, category: str, channel: discord.abc.GuildChannel):
        return channel in self.conf["categories"].get(category.lower(), {})

    def add_channel_to_category(self, category: str, channel: discord.abc.GuildChannel):
        category = self.conf["categories"].setdefault(category.lower(), [])
        if channel.id not in category:
            category.append(channel.id)
            self.storage_file.save()
            return True
        else:
            return False

    def remove_channel_from_category(self, category: str, channel: discord.abc.GuildChannel):
        category = category.lower()
        if self.channel_in_category(category, channel):
            self.conf["categories"][category].remove(channel.id)
            self.storage_file.save()
            return True
        else:
            return False
