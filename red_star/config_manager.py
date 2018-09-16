import json
import logging
import sys
from pathlib import Path
from shutil import copyfile
from red_star.rs_utils import JsonFileDict


class ConfigManager:
    """
    Manages the loading and modification of the configuration files.
    """
    def __init__(self, config_path):
        self.logger = logging.getLogger("red_star.config_manager")
        self.logger.debug("Initialized config manager.")
        self.config = {}
        self.config_path = config_path
        self.config_file_path = config_path / "config.json"
        self.plugin_config_files = []
        self.load_config()

    def load_config(self):
        self.logger.debug("Loading configuration...")
        try:
            with self.config_file_path.open(encoding="utf-8") as fd:
                self.config = json.load(fd)
        except FileNotFoundError:
            self.logger.warning(f"Couldn't find {self.config_file_path}! Copying default configuration...")
            default_path = Path.cwd() / "_default_files/config.json.default"
            copyfile(str(default_path), str(self.config_file_path))
            self.logger.info(f"A default configuration has been copied to {self.config_path}.\n"
                             f"Please configure the bot before continuing.")
            sys.exit(1)
        except json.decoder.JSONDecodeError:
            self.logger.exception(f"The configuration file located at {self.config_file_path} is invalid!\n"
                                  f"Please correct the error below and restart.", exc_info=True)
            sys.exit(1)

        if "plugins" not in self.config:
            self.config["plugins"] = {}

    def save_config(self):
        temp_path = Path(str(self.config_file_path) + "_")
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(self.config, f, sort_keys=True, indent=2)
        self.config_file_path.unlink()
        temp_path.rename(self.config_file_path)
        for file in self.plugin_config_files:
            file.save()
        self.logger.debug("Saved config files.")

    def get_plugin_config(self, name):
        if name not in self.config["plugins"]:
            self.config["plugins"][name] = {}
        conf = self.config["plugins"][name]
        return conf

    def init_plugin_config(self, name, default_config):
        new_config = default_config.copy()
        current_config = self.config["plugins"].get(name, {})
        new_config.update(current_config)
        self.config["plugins"][name] = new_config

    def get_plugin_config_file(self, filename, json_save_args=None, json_load_args=None):
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
        self.plugin_config_files.append(file_obj)
        return file_obj
