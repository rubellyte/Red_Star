import inspect
import logging
import importlib
import asyncio
from rs_utils import DotDict, Cupboard


class PluginManager:
    """
    Manages the loading of plugins and dispatching of event hooks.
    """

    def __init__(self, client, config_manager):
        self.client = client
        self.config_manager = config_manager
        self.plugins = DotDict({})
        self.active_plugins = DotDict({})
        self.logger = logging.getLogger("red_star.plugin_manager")
        self.shelve_path = self.config_manager.config.shelve_path
        self.shelve = None
        asyncio.ensure_future(self._write_to_shelve())

    def __repr__(self):
        return f"<PluginManager: Plugins: {self.plugins.keys()}, Active: {self.active_plugins}>"

    def load_from_path(self, plugin_path):
        ignores = ("__init__", "__pycache__")
        loaded = set()
        for file in plugin_path.iterdir():
            if file.stem in ignores:
                continue
            if (file.suffix == ".py" or file.is_dir()) \
                    and str(file) not in loaded \
                    and not file.stem.startswith("_"):
                try:
                    self.load_plugin(file)
                    loaded.add(str(file))
                except (SyntaxError, ImportError):
                    self.logger.exception(f"Exception encounter loading plugin {file.stem}: ", exc_info=True)
                except FileNotFoundError:
                    self.logger.error(f"File {file.stem} missing when load attempted!")

    def _load_module(self, module_path):
        if module_path.is_dir():
            module_path /= "__init__.py"
        if not module_path.exists():
            raise FileNotFoundError(f"{module_path} does not exist.")
        name = "plugins." + module_path.stem
        loader = importlib.machinery.SourceFileLoader(name, str(module_path))
        modul = loader.load_module(name)
        return modul

    def _get_plugin_class(self, modul):
        class_list = set()
        for name, obj in inspect.getmembers(modul, predicate=inspect.isclass):
            if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                obj.client = self.client
                obj.config_manager = self.config_manager
                obj.plugin_manager = self
                obj.logger = logging.getLogger("red_star.plugin." + obj.name)
                class_list.add(obj)
        return class_list

    def load_plugin(self, plugin_path):
        modul = self._load_module(plugin_path)
        classes = self._get_plugin_class(modul)
        for i in classes:
            self.plugins[i.name] = i()

    def final_load(self):
        try:
            self.shelve = Cupboard(self.shelve_path)
        except OSError:
            self.logger.exception("Exception occurred while opening shelve! ", exc_info=True)
            raise SystemExit
        except AttributeError:
            self.logger.error("shelve_path not defined in config!")
            raise SystemExit
        for plugin in self.plugins.values():
            plugin.plugins = self.active_plugins
            if plugin.name not in self.shelve:
                self.shelve[plugin.name] = {}
            plugin.storage = self.shelve[plugin.name]
            if plugin.default_config:
                self.config_manager.init_plugin_config(plugin.name, plugin.default_config)
                plugin.plugin_config = self.config_manager.get_plugin_config(plugin.name)

    async def activate_all(self):
        self.logger.info("Activating plugins.")
        if "disabled_plugins" not in self.config_manager.config:
            self.config_manager.config.disabled_plugins = []
            self.config_manager.save_config()
        to_load = self.config_manager.config.disabled_plugins
        for n, plugin in self.plugins.items():
            if n not in self.active_plugins and n not in to_load:
                self.logger.info("Activated " + plugin.name)
                await plugin.activate()
                self.active_plugins[n] = plugin
        await self.hook_event("on_all_plugins_loaded")

    async def deactivate_all(self):
        self.logger.info("Deactivating plugins.")
        for n, plugin in self.plugins.items():
            if n in self.active_plugins:
                self.logger.info("Deactivated " + plugin.name)
                await plugin.deactivate()
                del self.active_plugins[n]

    async def activate(self, name):
        try:
            plg = self.plugins[name]
            if name not in self.active_plugins:
                self.logger.info(f"Activating plugin {name}.")
                await plg.activate()
                self.active_plugins[name] = plg
                await self.hook_event("on_plugin_activated", name)
            else:
                self.logger.warning(f"Attempted to activate already active plugin {name}.")
        except KeyError:
            self.logger.error(f"Attempted to activate non-existent plugin {name}.")

    async def deactivate(self, name):
        try:
            plg = self.plugins[name]
            if name in self.active_plugins:
                self.logger.info(f"Deactivating plugin {name}.")
                await plg.deactivate()
                del self.active_plugins[name]
                await self.hook_event("on_plugin_deactivated", name)
            else:
                self.logger.warning(f"Attempted to deactivate already inactive plugin {name}.")
        except KeyError:
            self.logger.error(f"Attempted to deactivate non-existent plugin {name}.")

    async def hook_event(self, event, *args, **kwargs):
        """
        Dispatches an event, with its data, to all plugins.
        :param event: The name of the event. Should match the calling function.
        :param args: Everything that gets passed to the calling function
        should be passed through to this function.
        """
        plugins = set(self.active_plugins.values())
        for plugin in plugins:
            hook = getattr(plugin, event, False)
            if hook:
                try:
                    await hook(*args, **kwargs)
                except Exception:
                    self.logger.exception(f"Exception encountered in plugin {plugin.name} on event {event}: ",
                                          exc_info=True)

    async def _write_to_shelve(self):
        """
        A looping coroutine that saves the shelf to file on a configured interval.
        :return: None.
        """
        try:
            time = self.config_manager.config.shelve_save_interval
        except AttributeError:
            time = 60
        await asyncio.sleep(time)
        self.logger.debug("Writing to shelve...")
        try:
            self.shelve.sync()
        except Exception:
            self.logger.exception("Error writing to shelve. ", exc_info=True)
        await self._write_to_shelve()


class BasePlugin:
    """
    Base plugin class from which all plugins should inherit from. Remember to
    change the "name" variable, or else you'll have some serious issues! Note
    that the ConfigManager, PluginManager, and logger are inserted on load.
    """
    name = "Base Plugin"
    description = "This is a template class for plugins. Name *must* be"
    "filled, other meta-fields are optional."
    version = "1.0"
    default_config = DotDict({})
    plugins = set()
    client = None
    config_manager = None
    plugin_manager = None
    logger = None
    storage = None

    def __init__(self):
        self.plugin_config = self.config_manager.get_plugin_config(self.name)

    async def activate(self):
        pass

    async def deactivate(self):
        pass

    def __str__(self):
        """
        Method to return something a little less nasty.
        :return: String: The string to return when str() is called on this object.
        """
        return f"<Plugin {self.name} (Version {self.version})>"

    def __repr__(self):
        """
        Method to return something a little less nasty.
        :return: String: The string to return when str() is called on this object.
        """
        return f"<Plugin {self.name} (Version {self.version})>"
