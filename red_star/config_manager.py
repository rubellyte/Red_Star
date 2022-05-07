from __future__ import annotations
import json
import logging
import sys
from pathlib import Path
from shutil import copyfile
from red_star.rs_utils import JsonFileDict

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import discord


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

        if "plugins" not in self.config:
            self.config["plugins"] = {}

    def save_config(self):
        temp_path = Path(str(self.config_file_path) + "_bak")
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(self.config, f, sort_keys=True, indent=2)
        self.config_file_path.unlink()
        temp_path.rename(self.config_file_path)
        for file in self.plugin_config_files.values():
            file.save()
        self.logger.debug("Saved config files.")

    def get_plugin_config(self, name: str):
        if name not in self.config["plugins"]:
            self.config["plugins"][name] = {}
        conf = self.config["plugins"][name]
        return conf

    def init_plugin_config(self, name: str, default_config: dict):
        new_config = default_config.copy()
        current_config = self.config["plugins"].get(name, {})
        new_config.update(current_config)
        self.config["plugins"][name] = new_config

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
