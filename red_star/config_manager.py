from __future__ import annotations
import json
import logging
import shutil
import sys
from pathlib import Path
from shutil import copyfile

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import discord


JsonValues = None | bool | str | int | float | list | dict


class ConfigManager:
    """
    Manages the loading and modification of the configuration files.
    """
    def __init__(self, config_path: Path):
        self.logger = logging.getLogger("red_star.config_manager")
        self.logger.debug("Initialized config manager.")
        self.config = {}
        self.config_path = config_path
        self.config_file_path = config_path / "config.json"
        self.plugin_config_files = {}
        self.load_config()

    def load_config(self):
        temp_path = Path(str(self.config_file_path) + "_bak")
        self.logger.debug("Loading configuration...")
        try:
            with self.config_file_path.open(encoding="utf-8") as fd:
                self.config = json.load(fd)
        except FileNotFoundError:
            if temp_path.exists():
                temp_path.rename(self.config_file_path)
                self.logger.warning(f"Couldn't find {self.config_file_path}!\n"
                                    f"A backup from an interrupted save was found. Attempting to load...")
                return self.load_config()
            self.logger.warning(f"Couldn't find {self.config_file_path}! Copying default configuration...")
            default_path = Path.cwd() / "_default_files/config.json.default"
            self.config_path.mkdir(parents=True, exist_ok=True)
            copyfile(str(default_path), str(self.config_file_path))
            self.logger.info(f"A default configuration has been copied to {self.config_path}.\n"
                             f"Please configure the bot before continuing.")
            sys.exit(1)
        except json.decoder.JSONDecodeError:
            if temp_path.exists():
                self.config_file_path.unlink()
                temp_path.rename(self.config_file_path)
                self.logger.warning(f"The configuration file located at {self.config_file_path} is invalid!\n"
                                    f"A backup from an interrupted save was found. Attempting to load...")
                return self.load_config()
            self.logger.exception(f"The configuration file located at {self.config_file_path} is invalid!\n"
                                  f"Please correct the error below and restart.", exc_info=True)
            sys.exit(1)

        if self.config.get("global", {}).get("__config_version", 0) < 2:
            self._port_config_to_v2()

    def _port_config_to_v2(self):
        # Function to reorganize from plugin-first heirarchy to server-first heirarchy. Plugins that use their own
        # config files will have to manage this themselves.
        self.logger.warning("Porting configuration to newer format. Backup will be created.")
        backup_path = self.config_file_path.with_stem(self.config_file_path.stem + "_old_v1")
        shutil.copyfile(str(self.config_file_path), str(backup_path))
        new_config = {
            "global": {
                "__config_version": 2,
                "bot_maintainers": self.config["bot_maintainers"],
                "token": self.config["token"]
            },
            "default": {}
        }
        for plugin, config in self.config["plugins"].items():
            for k, v in config.items():
                if k.isdigit():
                    new_config[k] = {plugin: v}
                elif k == "default":
                    new_config["default"][plugin] = v
                else:
                    new_config["global"][plugin] = {k: v}
        self.config = new_config
        self.save_config()

    def save_config(self):
        temp_path = Path(str(self.config_file_path) + "_bak")
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(self.config, f, sort_keys=True, indent=2)
        self.config_file_path.unlink()
        temp_path.rename(self.config_file_path)
        for file in self.plugin_config_files.values():
            file.save()
        self.logger.debug("Saved config files.")

    def get_global_config(self, plugin: str, default_config=None):
        if default_config is None:
            default_config = {}
        return ConfigDict(self.config["global"].setdefault(plugin, default_config), default_config)

    def get_server_config(self, guild: discord.Guild, plugin: str, default_config=None):
        if default_config is None:
            default_config = {}
        default_config = self.config["default"].setdefault(plugin, default_config)
        return ConfigDict(self.config.setdefault(str(guild.id), {}).setdefault(plugin, default_config),
                          default_config)

    def get_plugin_config_file(self, filename: str, json_save_args: dict = None,
                               json_load_args: dict = None) -> JsonFileDict:
        if filename in self.plugin_config_files:
            file_obj = self.plugin_config_files[filename]
        else:
            file_path = self.config_path / filename
            if not file_path.exists():
                default_config = Path.cwd() / "_default_files" / (filename + ".default")
                if default_config.exists():
                    copyfile(str(default_config), str(file_path))
                    self.logger.debug(f"Copied default configuration for {filename} to {file_path}.")
                else:
                    with file_path.open("w", encoding="utf-8") as fd:
                        fd.write("{}")
                    self.logger.debug(f"Created config file {file_path}.")
            file_obj = JsonFileDict(file_path, json_save_args, json_load_args)
            self.plugin_config_files[filename] = file_obj
        return file_obj

    def is_maintainer(self, user: discord.abc.User):
        return user.id in self.config.get('bot_maintainers', [])

# Utility classes


class ConfigDict(dict):

    def __init__(self, config: dict[str, JsonValues], default_config: dict[str, JsonValues]):
        super().__init__()
        new_dict = default_config | config
        for k, v in new_dict.items():
            if isinstance(v, dict):
                self[k] = ConfigDict(v, default_config.get(k, {}))
            else:
                self[k] = v


class JsonFileDict(dict):
    """
    Dictionary subclass that handles saving the file on edits automatically.
    Try not to instantiate this class directly; instead, use the config_manager's factory method,
    ConfigManager.get_plugin_config_file.
    :param Path path: The path that should be saved to.
    """

    def __init__(self, path: Path, json_save_args: dict = None, json_load_args: dict = None, **kwargs):
        super().__init__(**kwargs)
        self.path = path
        self.json_save_args = {} if json_save_args is None else json_save_args
        self.json_load_args = {} if json_load_args is None else json_load_args
        self.reload()

    def __setitem__(self, key: str, value: JsonValues):
        super().__setitem__(key, value)
        self.save()

    def __delitem__(self, key: str):
        super().__delitem__(key)
        self.save()

    def save(self):
        with self.path.open("w", encoding="utf-8") as fd:
            json.dump(self, fd, **self.json_save_args)

    def reload(self):
        with self.path.open(encoding="utf-8") as fd:
            self.update(json.load(fd, **self.json_load_args))