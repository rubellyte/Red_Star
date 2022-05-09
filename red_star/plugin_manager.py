from __future__ import annotations
import inspect
import logging
import importlib
import importlib.util
from sys import exc_info, modules
from types import ModuleType
import discord
from red_star.channel_manager import ChannelManager
from red_star.command_dispatcher import CommandDispatcher

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pathlib import Path
    from typing import Type
    from red_star.client import RedStar
    from red_star.config_manager import ConfigManager


class PluginManager:
    """
    Manages the loading of plugins and dispatching of event hooks.
    """

    def __init__(self, client: RedStar):
        self.client = client
        self.config_manager = client.config_manager
        # self.channel_manager = client.channel_manager
        # self.command_dispatcher = client.command_dispatcher
        self.modules = {}
        self.plugins: dict[discord.Guild, dict[str, BasePlugin | ChannelManager | CommandDispatcher]] = {}
        self.plugin_classes: dict[str, Type[BasePlugin]] = {}
        self.active_plugins = {}
        self.logger = logging.getLogger("red_star.plugin_manager")
        self.logger.debug("Initialized plugin manager.")
        self.last_error = None
        self.plugin_package = ModuleType("red_star_plugins")
        self.plugin_package.__path__ = []
        self.default_server_config = {"disabled_plugins": []}
        modules["red_star_plugins"] = self.plugin_package

    def __repr__(self):
        return f"<PluginManager: Plugins: {self.plugin_classes.keys()}, Active: {self.active_plugins}>"

    def load_all_plugins(self, plugin_paths: [Path]):
        """
        Loads all plugins from all specified folders and places them into the `red_star_plugins` module for
        cross-plugins access.
        :param plugin_paths:
        :return:
        """
        self.logger.debug("Loading plugins...")
        self.plugin_package.__path__.extend(str(x) for x in plugin_paths)
        for path in plugin_paths:
            self._load_plugin_folder(path)
        self.config_manager.save_config()
        self.logger.info(f"Loaded {len(self.plugin_classes)} plugins from {len(self.modules)} modules.")

    def _load_plugin_folder(self, plugin_path: Path):
        """
        Loads all plugins in a folder and initializes them for use.
        :param plugin_path:
        :return:
        """
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

    def _load_module(self, module_name: str) -> ModuleType:
        """
        Imports Python modules containing plugins and adds them to the module list.
        :param module_name: the name of the module to be imported.
        :return: The module object.
        """
        mod = importlib.import_module(f"red_star_plugins.{module_name}")
        self.modules[module_name] = mod
        self.logger.debug(f"Imported module {module_name}.")
        return mod

    def _get_plugin_class(self, plugin_module: ModuleType) -> set[Type[BasePlugin]]:
        """
        Extracts the plugin classes from a module and assigns them several class-level properties.
        :param plugin_module: The module containing the plugin classes to be extracted.
        :return: The extracted plugin classes, with class properties assigned.
        """
        def predicate(cls):
            return inspect.isclass(cls) and issubclass(cls, BasePlugin) and cls is not BasePlugin

        class_list = set()
        for name, obj in inspect.getmembers(plugin_module, predicate=predicate):
            obj.client = self.client
            obj.config_manager = self.config_manager
            self.config_manager.get_global_config(name, default_config=obj.default_global_config)
            obj.plugin_manager = self
            ChannelManager.channel_types.update(obj.channel_types)
            ChannelManager.channel_categories.update(obj.channel_categories)
            class_list.add(obj)
        return class_list

    def load_plugin(self, plugin_module: ModuleType):
        """
        Extracts the plugin classes from a module and creates instances of them for use,
        placing them in the plugins list.
        :param plugin_module: The module containing the plugin classes to be extracted.
        :return:
        """
        classes = self._get_plugin_class(plugin_module)
        for cls in classes:
            self.plugin_classes[cls.name] = cls
            self.logger.debug(f"Loaded plugin {cls.name}")

    async def activate_all(self):
        """
        Activates enabled plugins by running their activate() function and placing them in the active plugins list.
        Runs the on_all_plugins_loaded hook after loading all plugins.
        :return:
        """
        self.logger.info("Activating plugins.")
        for guild in self.client.guilds:
            await self.activate_server_plugins(guild)

    async def activate_server_plugins(self, guild: discord.Guild):
        channel_manager = ChannelManager(self.client, guild)
        command_dispatcher = CommandDispatcher(self.client, guild, channel_manager)
        self.plugins[guild] = {"channel_manager": channel_manager, "command_dispatcher": command_dispatcher}
        disabled_plugins = self.config_manager.get_server_config(guild, "plugin_manager",
                                                                 self.default_server_config)["disabled_plugins"]
        for name, plugin in self.plugin_classes.items():
            if name in disabled_plugins:
                continue
            await self.activate(guild, name)
        await self.hook_event("on_all_plugins_loaded", guild)

    async def activate(self, guild: discord.Guild, name: str):
        guild_plugins = self.plugins[guild]
        try:
            plugin = self.plugin_classes[name]
            if name not in guild_plugins:
                self.logger.info(f"Activating plugin {name}.")
                # noinspection PyBroadException
                try:
                    plugin_inst = plugin(guild,
                                         self.config_manager.get_server_config(guild, name, plugin.default_config),
                                         guild_plugins["channel_manager"], guild_plugins)
                    await plugin_inst.activate()
                    guild_plugins["command_dispatcher"].register_plugin(plugin_inst)
                    guild_plugins[name] = plugin_inst
                except Exception:
                    self.logger.exception(
                        f"Error occurred while activating plugin {plugin.name} for server {guild.id}: ",
                        exc_info=True)
            else:
                self.logger.warning(f"Attempted to activate already active plugin {name}.")
        except KeyError:
            self.logger.error(f"Attempted to activate non-existent plugin {name}.")

    async def deactivate_all(self):
        """
        Deactivates all enabled plugins, typically in preparation for shutdown. Removes them from the active plugins
        list and runs their deactivate() function.
        :return:
        """
        self.logger.info("Deactivating plugins.")
        for guild in self.client.guilds:
            await self.deactivate_server_plugins(guild)

    async def deactivate_server_plugins(self, guild):
        guild_plugins = self.plugins[guild]
        for name, plugin in guild_plugins.items():
            if name in ("command_dispatcher", "channel_manager"):
                continue
            await self.deactivate(guild, name)
            del guild_plugins["command_dispatcher"]
            del guild_plugins["channel_manager"]

    async def deactivate(self, guild: discord.Guild, name: str):
        guild_plugins = self.plugins[guild]
        try:
            if name in guild_plugins:
                plugin = guild_plugins[name]
                self.logger.info(f"Deactivating plugin {name}.")
                # noinspection PyBroadException
                try:
                    await plugin.deactivate()
                except Exception:
                    self.logger.exception(f"Error occurred while deactivating plugin {name}: ", exc_info=True)
                guild_plugins["command_dispatcher"].deregister_plugin(plugin)
                del guild_plugins[name]
                await self.hook_event("on_plugin_deactivated", name)
            else:
                self.logger.warning(f"Attempted to deactivate already inactive plugin {name}.")
        except KeyError:
            self.logger.error(f"Attempted to deactivate non-existent plugin {name}.")

    async def reload_plugin(self, name: str):
        """
        Reloads a plugin from its source file.
        :param name: The plugin to be reloaded.
        :return:
        """
        try:
            self.logger.info(f"Reloading plugin module {name}.")
            servers_active_on = set()
            for guild, plugins in self.plugins.items():
                if name in plugins:
                    servers_active_on.add(guild)
                    await self.deactivate(guild, name)
            del self.plugin_classes[name]
            modul = self.modules[name]
            importlib.reload(modul)
            self.load_plugin(modul)
            for guild in servers_active_on:
                await self.activate(guild, name)
        except KeyError:
            self.logger.error(f"Attempted to reload non-existent plugin module {name}.")

    async def hook_event(self, event: str, guild, *args, **kwargs):
        """
        Dispatches an event, with its data, to all plugins.
        :param event: The name of the event. Should match the calling function.
        :param guild: The guild to which the event belongs.
        :param args: Everything that gets passed to the calling function
        should be passed through to this function.
        """
        for name, plugin in self.plugins[guild].items():
            hook = getattr(plugin, event, None)
            if hook:
                # noinspection PyBroadException
                try:
                    await hook(*args, **kwargs)
                except Exception:
                    self.last_error = exc_info()
                    self.logger.exception(f"Exception encountered in plugin {name} on event {event}: ",
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
    # plugins: dict = {}
    # plugin_config: dict = {}
    client: RedStar
    config_manager: ConfigManager
    # channel_manager: ChannelManager
    plugin_manager: PluginManager
    # logger = logging.Logger
    # User-defined attributes for use internally
    default_config: dict = {}
    default_global_config: dict = {}
    global_plugin_config: dict = {}
    channel_types: set = set()
    channel_categories: set = set()

    def __init__(self, guild: discord.Guild, plugin_config: dict, channel_manager: ChannelManager,
                 plugins: dict[str, BasePlugin]):
        self.guild = guild
        self.config = plugin_config
        self.channel_manager = channel_manager
        self.plugins = plugins
        self.logger = logging.getLogger(f"red_star.plugin.{self.name}.{guild.id}")

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
        return f"<Plugin {self.name} (Version {self.version}) for server {self.guild.id}>"

    def __repr__(self):
        """
        Method to return something a little less nasty.
        :return: string: The string to return when repr() is called on this object.
        """
        return f"<Plugin {self.name} (Version {self.version}) for server {self.guild.id}>"
