import asyncio
import inspect
import logging
import importlib
from utils import DotDict


class PluginManager:
    """
    Manages the loading of plugins and dispatching of event hooks.
    """

    def __init__(self, client, config_manager):
        self.client = client
        self.config_manager = config_manager
        self.plugins = DotDict({})
        self.active_plugins = set()
        self.logger = logging.getLogger("red_star.plugin_manager")

    def __repr__(self):
        return "<PluginManager: Plugins: {}, Active: >".format(
            self.plugins.keys(), self.active_plugins())

    def load_from_path(self, plugin_path):
        ignores = ("__init__", "__pycache__")
        loaded = set()
        for file in plugin_path.iterdir():
            if file.stem in ignores:
                continue
            if (file.suffix == ".py" or file.is_dir()) and str(file) not in loaded:
                try:
                    self.load_plugin(file)
                    loaded.add(str(file))
                except (SyntaxError, ImportError) as e:
                    self.logger.exception("Exception encounter loading plugin "
                                          "{}: ".format(file.stem), exc_info=True)
                except FileNotFoundError:
                    self.logger.error("File {} missing when load attempted!".format(file.stem))

    def _load_module(self, module_path):
        if module_path.is_dir():
            module_path /= "__init__.py"
        if not module_path.exists():
            raise FileNotFoundError("{} does not exist.".format(module_path))
        name = "plugins." + module_path.stem
        loader = importlib.machinery.SourceFileLoader(name, str(module_path))
        module = loader.load_module(name)
        return module

    def _get_plugin_class(self, module):
        class_list = set()
        for name, obj in inspect.getmembers(module, predicate=inspect.isclass):
            if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                obj.client = self.client
                obj.config = self.config_manager
                obj.manager = self
                obj.logger = logging.getLogger("red_star.plugin." + obj.name)
                class_list.add(obj)
        return class_list

    def load_plugin(self, plugin_path):
        module = self._load_module(plugin_path)
        classes = self._get_plugin_class(module)
        for i in classes:
            self.plugins[i.name] = i()

    def final_load(self):
        for plugin in self.plugins.values():
            plugin.plugins = self.plugins
            if plugin.default_config:
                self.config_manager.init_plugin_config(plugin.name, plugin.default_config)

    def activate_all(self):
        self.logger.info("Activating plugins.")
        for plugin in self.plugins.values():
            self.logger.info("Activated " + plugin.name)
            plugin.activate()
            self.active_plugins.add(plugin)

    def deactivate_all(self):
        self.logger.info("Deactivating plugins.")
        for plugin in self.plugins.values():
            self.logger.info("Deactivated " + plugin.name)
            plugin.deactivate()
            self.active_plugins.remove(plugin)

    def activate(self, plugin):
        try:
            plg = self.plugins[plugin]
            if plg not in self.active_plugins:
                plg.activate()
                self.active_plugins.add(plg)
            else:
                self.logger.warning("Attempted to activate already active plugin {}.".format(plugin))
        except KeyError:
            self.logger.error("Attempted to activate non-existent plugin {}.".format(plugin))

    def deactivate(self, plugin):
        try:
            plg = self.plugins[plugin]
            if plg in self.active_plugins:
                plg.deactivate()
                self.active_plugins.remove(plg)
            else:
                self.logger.warning("Attempted to deactivate already inactive plugin {}.".format(plugin))
        except KeyError:
            self.logger.error("Attempted to deactivate non-existent plugin {}.".format(plugin))

    @asyncio.coroutine
    def hook_event(self, event, *args):
        """
        Dispatches an event, with its data, to all plugins.
        :param event: The name of the event. Should match the calling function.
        :param *args: Everything that gets passed to the calling function
        should be passed through to this function.
        """
        for plugin in self.active_plugins:
            hook = getattr(plugin, event, False)
            if hook:
                try:
                    yield from hook(*args)
                except Exception:
                    self.logger.exception("Exception encounter in plugin {} on"
                                          " event {}: ".format(plugin.name, event), exc_info=True)


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
    default_config = None
    plugins = DotDict({})

    def __init__(self):
        self.plugin_config = self.config.get_plugin_config(self.name)
