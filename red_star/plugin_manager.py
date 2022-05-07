from __future__ import annotations
import inspect
import logging
import importlib
import importlib.util
from sys import exc_info, modules
from types import ModuleType

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pathlib import Path
    from typing import Type
    from red_star.client import RedStar
    from red_star.channel_manager import ChannelManager
    from red_star.config_manager import ConfigManager


class PluginManager:
    """
    Manages the loading of plugins and dispatching of event hooks.
    """

    def __init__(self, client: RedStar):
        self.client = client
        self.config_manager = client.config_manager
        self.channel_manager = client.channel_manager
        self.command_dispatcher = client.command_dispatcher
        self.modules = {}
        self.plugins = {}
        self.active_plugins = {}
        self.logger = logging.getLogger("red_star.plugin_manager")
        self.logger.debug("Initialized plugin manager.")
        self.last_error = None
        self.plugin_package = ModuleType("red_star_plugins")
        self.plugin_package.__path__ = []
        modules["red_star_plugins"] = self.plugin_package

    def __repr__(self):
        return f"<PluginManager: Plugins: {self.plugins.keys()}, Active: {self.active_plugins}>"

    def load_all_plugins(self, plugin_paths: [Path]):
        self.logger.debug("Loading plugins...")
        self.plugin_package.__path__.extend(str(x) for x in plugin_paths)
        for path in plugin_paths:
            self._load_plugin_folder(path)
        self.config_manager.save_config()
        self.logger.info(f"Loaded {len(self.plugins)} plugins from {len(self.modules)} modules.")

    def _load_plugin_folder(self, plugin_path: Path):
        self.logger.debug(f"Loading plugins from {plugin_path}...")
        loaded = set()
        plugin_path.mkdir(parents=True, exist_ok=True)
        for file in plugin_path.iterdir():
            if file.stem.startswith(("_", ".")):
                continue
            if (file.suffix == ".py" or file.is_dir()) and file not in loaded:
                try:
                    modul = self._load_module(file.stem)
                    self.load_plugin(modul)
                    loaded.add(file)
                except (SyntaxError, ImportError):
                    self.logger.exception(f"Exception encountered loading plugin {file.stem}: ", exc_info=True)
                    continue
                except FileNotFoundError:
                    self.logger.error(f"File {file.stem} missing when load attempted!")
                    continue

    def _load_module(self, module_name: str):
        mod = importlib.import_module(f"red_star_plugins.{module_name}")
        self.modules[module_name] = mod
        self.logger.debug(f"Imported module {module_name}.")
        return mod

    def _get_plugin_class(self, plugin_module: ModuleType) -> set[Type["BasePlugin"]]:
        def predicate(cls):
            return inspect.isclass(cls) and issubclass(cls, BasePlugin) and cls is not BasePlugin

        class_list = set()
        for name, obj in inspect.getmembers(plugin_module, predicate=predicate):
            obj.client = self.client
            obj.config_manager = self.config_manager
            if obj.default_config:
                self.config_manager.init_plugin_config(obj.name, obj.default_config)
                obj.plugin_config = self.config_manager.get_plugin_config(obj.name)
            obj.channel_manager = self.channel_manager
            if obj.channel_types:
                self.channel_manager.channel_types |= obj.channel_types
            if obj.channel_categories:
                self.channel_manager.channel_categories |= obj.channel_categories
            obj.plugin_manager = self
            obj.plugins = self.active_plugins
            obj.logger = logging.getLogger("red_star.plugin." + obj.name)
            class_list.add(obj)
        return class_list

    def load_plugin(self, plugin_module: ModuleType):
        classes = self._get_plugin_class(plugin_module)
        for cls in classes:
            self.plugins[cls.name] = cls()
            self.logger.debug(f"Loaded plugin {cls.name}")

    async def activate_all(self):
        self.logger.info("Activating plugins.")
        if "disabled_plugins" not in self.config_manager.config:
            self.config_manager.config["disabled_plugins"] = []
            self.config_manager.save_config()
        disabled_plugins = self.config_manager.config["disabled_plugins"]
        for name, plugin in self.plugins.items():
            if name not in self.active_plugins and name not in disabled_plugins:
                self.logger.info("Activating " + plugin.name)
                # noinspection PyBroadException
                try:
                    await plugin.activate()
                    self.active_plugins[name] = plugin
                    self.command_dispatcher.register_plugin(plugin)
                except Exception:
                    self.logger.exception(f"Error occurred while activating plugin {plugin.name}: ", exc_info=True)
        await self.hook_event("on_all_plugins_loaded")

    async def deactivate_all(self):
        self.logger.info("Deactivating plugins.")
        for n, plugin in self.plugins.items():
            if n in self.active_plugins:
                self.logger.info("Deactivating " + plugin.name)
                # noinspection PyBroadException
                try:
                    await plugin.deactivate()
                except Exception:
                    self.logger.exception(f"Error occurred while deactivating plugin {plugin.name}: ", exc_info=True)
                del self.active_plugins[n]
                self.command_dispatcher.deregister_plugin(plugin)

    async def activate(self, name: str):
        try:
            plg = self.plugins[name]
            if name not in self.active_plugins:
                self.logger.info(f"Activating plugin {name}.")
                # noinspection PyBroadException
                try:
                    await plg.activate()
                    self.active_plugins[name] = plg
                    self.command_dispatcher.register_plugin(plg)
                    await self.hook_event("on_plugin_activated", name)
                except Exception:
                    self.logger.exception(f"Error occurred while activating plugin {name}: ", exc_info=True)
            else:
                self.logger.warning(f"Attempted to activate already active plugin {name}.")
        except KeyError:
            self.logger.error(f"Attempted to activate non-existent plugin {name}.")

    async def deactivate(self, name: str):
        try:
            plg = self.plugins[name]
            if name in self.active_plugins:
                self.logger.info(f"Deactivating plugin {name}.")
                # noinspection PyBroadException
                try:
                    await plg.deactivate()
                except Exception:
                    self.logger.exception(f"Error occurred while deactivating plugin {name}: ", exc_info=True)
                del self.active_plugins[name]
                self.command_dispatcher.deregister_plugin(plg)
                await self.hook_event("on_plugin_deactivated", name)
            else:
                self.logger.warning(f"Attempted to deactivate already inactive plugin {name}.")
        except KeyError:
            self.logger.error(f"Attempted to deactivate non-existent plugin {name}.")

    async def reload_plugin(self, name: str):
        try:
            self.logger.info(f"Reloading plugin module {name}.")
            was_active = False
            if name in self.active_plugins:
                was_active = True
                await self.deactivate(name)
            del self.plugins[name]
            modul = self.modules[name]
            importlib.reload(modul)
            self.load_plugin(modul)
            if was_active:
                await self.activate(name)
        except KeyError:
            self.logger.error(f"Attempted to reload non-existent plugin module {name}.")

    async def hook_event(self, event: str, *args, **kwargs):
        """
        Dispatches an event, with its data, to all plugins.
        :param event: The name of the event. Should match the calling function.
        :param args: Everything that gets passed to the calling function
        should be passed through to this function.
        """
        plugins = set(self.active_plugins.values())
        for plugin in plugins:
            hook = getattr(plugin, event, None)
            if hook:
                # noinspection PyBroadException
                try:
                    await hook(*args, **kwargs)
                except Exception:
                    self.last_error = exc_info()
                    self.logger.exception(f"Exception encountered in plugin {plugin.name} on event {event}: ",
                                          exc_info=True)


class BasePlugin:
    """
    The base plugin class from which all plugin classes must inherit in order to be detected by the plugin manager.
    It is recommended you set all meta-fields (name, description, version, author), but only name is necessary.
    In most circumstances you're going to want the plugin name and the module name to be the same.
    The plugin manager will install various useful things to the class.
    """
    # Metadata fields
    name: str = "Base Plugin"
    description: str = "This is a template class for plugins. Name *must* be filled, other meta-fields are optional."
    version: str = "1.0"
    author: str = "Unknown"
    # Attributes added by plugin manager
    plugins: dict = {}
    plugin_config: dict = {}
    client: RedStar
    config_manager: ConfigManager
    channel_manager: ChannelManager
    plugin_manager: PluginManager
    logger = logging.Logger
    # User-defined attributes for use internally
    default_config: dict = {}
    channel_types: set = set()
    channel_categories: set = set()

    async def activate(self):
        """
        The method called when the plugin is initialized. Should be used to get all the Discord-related
        initialization out of the way.
        Raise an exception in this method to cancel activation, say if a required package isn't installed.
        """

    async def deactivate(self):
        """
        The method called when the plugin is uninitalized. Should be used to perform any necessary cleanup.
        """

    def __str__(self):
        """
        Method to return something a little less nasty.
        :return: string: The string to return when str() is called on this object.
        """
        return f"<Plugin {self.name} (Version {self.version})>"

    def __repr__(self):
        """
        Method to return something a little less nasty.
        :return: string: The string to return when repr() is called on this object.
        """
        return f"<Plugin {self.name} (Version {self.version})>"
