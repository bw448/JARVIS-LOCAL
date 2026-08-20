"""
Plugin system for JARVIS Assistant.
Allows extending functionality through plugins.
"""

from __future__ import annotations

import importlib
import inspect
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

class PluginBase(ABC):
    """Base class for all JARVIS plugins."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name."""
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version."""
        pass
    
    @property
    def description(self) -> str:
        """Plugin description."""
        return ""
    
    @property
    def author(self) -> str:
        """Plugin author."""
        return ""
    
    @abstractmethod
    def initialize(self, context: Dict[str, Any]) -> bool:
        """
        Initialize the plugin.
        
        Args:
            context: Application context containing config, services, etc.
        
        Returns:
            True if initialization was successful.
        """
        pass
    
    def cleanup(self):
        """Cleanup resources when plugin is unloaded."""
        pass
    
    def get_commands(self) -> Dict[str, callable]:
        """
        Get commands provided by this plugin.
        
        Returns:
            Dictionary mapping command names to handler functions.
        """
        return {}
    
    def get_event_handlers(self) -> Dict[str, List[callable]]:
        """
        Get event handlers provided by this plugin.
        
        Returns:
            Dictionary mapping event names to lists of handler functions.
        """
        return {}

class PluginManager:
    """Manages plugin loading and lifecycle."""
    
    def __init__(self, plugins_dir: Optional[Path] = None):
        self.plugins_dir = plugins_dir
        self.plugins: Dict[str, PluginBase] = {}
        self.commands: Dict[str, callable] = {}
        self.event_handlers: Dict[str, List[callable]] = {}
    
    def discover_plugins(self) -> List[str]:
        """
        Discover available plugins in the plugins directory.
        
        Returns:
            List of plugin module names.
        """
        if not self.plugins_dir or not self.plugins_dir.exists():
            return []
        
        plugin_modules = []
        for item in self.plugins_dir.iterdir():
            if item.is_dir() and (item / "__init__.py").exists():
                plugin_modules.append(item.name)
            elif item.suffix == ".py" and item.name != "__init__.py":
                plugin_modules.append(item.stem)
        
        return plugin_modules
    
    def load_plugin(self, module_name: str, context: Dict[str, Any]) -> bool:
        """
        Load and initialize a plugin.
        
        Args:
            module_name: Name of the plugin module.
            context: Application context.
        
        Returns:
            True if plugin was loaded successfully.
        """
        try:
            # Import the plugin module
            if self.plugins_dir:
                import sys
                sys.path.insert(0, str(self.plugins_dir.parent))
                module = importlib.import_module(f"plugins.{module_name}")
            else:
                module = importlib.import_module(module_name)
            
            # Find the plugin class
            plugin_class = None
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, PluginBase) and obj != PluginBase:
                    plugin_class = obj
                    break
            
            if not plugin_class:
                return False
            
            # Instantiate and initialize the plugin
            plugin = plugin_class()
            if not plugin.initialize(context):
                return False
            
            # Register the plugin
            self.plugins[plugin.name] = plugin
            
            # Register commands
            for cmd_name, cmd_handler in plugin.get_commands().items():
                self.commands[cmd_name] = cmd_handler
            
            # Register event handlers
            for event_name, handlers in plugin.get_event_handlers().items():
                if event_name not in self.event_handlers:
                    self.event_handlers[event_name] = []
                self.event_handlers[event_name].extend(handlers)
            
            return True
        
        except Exception as e:
            print(f"Failed to load plugin {module_name}: {e}")
            return False
    
    def load_all_plugins(self, context: Dict[str, Any]):
        """
        Load all available plugins.
        
        Args:
            context: Application context.
        """
        plugin_modules = self.discover_plugins()
        for module_name in plugin_modules:
            self.load_plugin(module_name, context)
    
    def unload_plugin(self, plugin_name: str):
        """
        Unload a plugin.
        
        Args:
            plugin_name: Name of the plugin to unload.
        """
        if plugin_name not in self.plugins:
            return
        
        plugin = self.plugins[plugin_name]
        plugin.cleanup()
        
        # Remove commands
        for cmd_name in plugin.get_commands():
            self.commands.pop(cmd_name, None)
        
        # Remove event handlers
        for event_name, handlers in plugin.get_event_handlers().items():
            if event_name in self.event_handlers:
                for handler in handlers:
                    if handler in self.event_handlers[event_name]:
                        self.event_handlers[event_name].remove(handler)
        
        del self.plugins[plugin_name]
    
    def unload_all_plugins(self):
        """Unload all plugins."""
        for plugin_name in list(self.plugins.keys()):
            self.unload_plugin(plugin_name)
    
    def get_plugin(self, plugin_name: str) -> Optional[PluginBase]:
        """Get a plugin by name."""
        return self.plugins.get(plugin_name)
    
    def execute_command(self, command_name: str, *args, **kwargs) -> Any:
        """
        Execute a plugin command.
        
        Args:
            command_name: Name of the command to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.
        
        Returns:
            Command result.
        """
        if command_name not in self.commands:
            raise ValueError(f"Unknown command: {command_name}")
        
        return self.commands[command_name](*args, **kwargs)
    
    def emit_event(self, event_name: str, *args, **kwargs):
        """
        Emit an event to all registered handlers.
        
        Args:
            event_name: Name of the event.
            *args: Positional arguments.
            **kwargs: Keyword arguments.
        """
        if event_name in self.event_handlers:
            for handler in self.event_handlers[event_name]:
                try:
                    handler(*args, **kwargs)
                except Exception as e:
                    print(f"Error in event handler for {event_name}: {e}")
