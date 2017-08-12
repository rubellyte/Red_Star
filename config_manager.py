import json
import logging
import sys
from pathlib import Path
from shutil import copyfile
from utils import DotDict, dict_merge


class ConfigManager:
    """
    Manages the loading and modification of the configuration files.
    """
    def __init__(self):
        self.logger = logging.getLogger("red_star.config_manager")
        self.raw_config = None
        self.config = DotDict({})
        self._path = None

    def load_config(self, config_path):
        if not isinstance(config_path, Path):
            config_path = Path(config_path)
        try:
            with config_path.open(encoding="utf-8") as f:
                self.raw_config = f.read()
        except FileNotFoundError:
            self.logger.warning("Couldn't open config.json! Copying "
                                "config.json.default...")
            default_path = Path(str(config_path) + ".default")
            try:
                copyfile(str(default_path), str(config_path))
                with config_path.open("w", encoding="utf-8") as f:
                    self.raw_config = f.read()
            except FileNotFoundError:
                self.logger.error("Couldn't open config.json.default! Please "
                                  "verify config files.")
                sys.exit(1)
        self._path = config_path
        try:
            self.config = DotDict(json.loads(self.raw_config))
        except json.decoder.JSONDecodeError:
            self.logger.exception("Exception encountered while parsing "
                                  "config.json: ", exc_info=True)
            sys.exit(1)
        except TypeError:
            self.logger.error("Load of config.json failed!")
            sys.exit(1)
        if "plugins" not in self.config:
            self.config.plugins = DotDict({})

    def save_config(self, path=None):
        if not path:
            path = self._path
        temp_path = Path(str(path) + "_")
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(self.config, f, sort_keys=True, indent=2)
        path.unlink()
        temp_path.rename(path)
        self.logger.debug("Saved config file.")

    def get_plugin_config(self, name):
        if name not in self.config.plugins:
            self.config.plugins[name] = DotDict({})
        conf = self.config.plugins[name]
        return conf

    def init_plugin_config(self, name, conf):
        if name not in self.config.plugins:
            self.config.plugins[name] = DotDict({})
        self.config.plugins[name] = DotDict(dict_merge(conf, self.config.plugins[name]))
        self.save_config()
