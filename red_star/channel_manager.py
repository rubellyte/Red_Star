from red_star.rs_errors import ChannelNotFoundError


class ChannelManager:
    def __init__(self, client):
        self.client = client
        self.config_manager = client.config_manager
        try:
            self.conf = self.config_manager.config["channel_manager"]
        except AttributeError:
            self.config_manager.config["channel_manager"] = {}
            self.conf = self.config_manager.config["channel_manager"]
        self.default_config = {
            "channels": {},
            "categories": {}
        }

    def add_guild(self, guild):
        gid = str(guild.id)
        if gid not in self.conf:
            self.conf[gid] = self.default_config
            if guild.afk_channel:
                self.conf[gid].channels.voice_afk = guild.afk_channel.id
            self.config_manager.save_config()

    def get_channel(self, guild, chantype):
        gid = str(guild.id)
        chantype = chantype.lower()
        self.add_guild(guild)
        if chantype in self.conf[gid].channels:
            chan = self.conf[gid].channels[chantype]
            chan = self.client.get_channel(chan)
            if not chan:
                raise ChannelNotFoundError(chantype)
            return chan
        else:
            raise ChannelNotFoundError(chantype)

    def set_channel(self, guild, chantype, channel):
        gid = str(guild.id)
        chantype = chantype.lower()
        self.add_guild(guild)
        if channel:
            self.conf[gid].channels[chantype] = channel.id
            self.config_manager.save_config()
        elif chantype in self.conf[gid].channels:
            self.conf[gid].channels.pop(chantype)
            self.config_manager.save_config()

    def register_category(self, guild, category):
        gid = str(guild.id)
        category = category.lower()
        self.add_guild(guild)
        if category not in self.conf[gid].categories:
            self.conf[gid]["categories"][category] = []
        self.config_manager.save_config()

    def channel_in_category(self, guild, category, channel):
        gid = str(guild.id)
        category = category.lower()
        self.add_guild(guild)
        if category not in self.conf[gid].categories:
            return False
        if channel.id not in self.conf[gid]["categories"][category]:
            return False
        return True

    def add_channel_to_category(self, guild, category, channel):
        gid = str(guild.id)
        category = category.lower()
        self.add_guild(guild)
        if category not in self.conf[gid].categories:
            self.conf[gid].categories[category] = [channel.id]
            self.config_manager.save_config()
            return True
        elif channel.id not in self.conf[gid].categories[category]:
            self.conf[gid].categories[category].append(channel.id)
            self.config_manager.save_config()
            return True
        else:
            return False

    def remove_channel_from_category(self, guild, category, channel):
        gid = str(guild.id)
        category = category.lower()
        self.add_guild(guild)
        if category not in self.conf[gid].categories:
            return False
        elif channel.id not in self.conf[gid].categories[category]:
            return False
        else:
            self.conf[gid].categories[category].remove(channel.id)
            self.config_manager.save_config()
            return True
