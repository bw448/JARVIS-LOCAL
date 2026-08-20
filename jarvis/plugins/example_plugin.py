"""
Example plugin for JARVIS Assistant.
Demonstrates how to create a plugin.
"""

from __future__ import annotations

from typing import Any, Dict

from . import PluginBase


class ExamplePlugin(PluginBase):
    """Example plugin that adds greeting functionality."""
    
    @property
    def name(self) -> str:
        return "example"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def description(self) -> str:
        return "Example plugin demonstrating the plugin system."
    
    @property
    def author(self) -> str:
        return "JARVIS Team"
    
    def initialize(self, context: Dict[str, Any]) -> bool:
        """Initialize the plugin."""
        self.context = context
        self.greeting_count = 0
        return True
    
    def cleanup(self):
        """Cleanup resources."""
        pass
    
    def get_commands(self) -> Dict[str, callable]:
        """Get commands provided by this plugin."""
        return {
            "greet": self.greet,
            "greet_count": self.get_greeting_count,
        }
    
    def get_event_handlers(self) -> Dict[str, list]:
        """Get event handlers provided by this plugin."""
        return {
            "user_connected": [self.on_user_connected],
        }
    
    def greet(self, name: str = "World") -> str:
        """
        Generate a greeting message.
        
        Args:
            name: Name to greet.
        
        Returns:
            Greeting message.
        """
        self.greeting_count += 1
        return f"Hello, {name}! This is greeting #{self.greeting_count}."
    
    def get_greeting_count(self) -> int:
        """Get the number of greetings generated."""
        return self.greeting_count
    
    def on_user_connected(self, username: str):
        """Handle user connected event."""
        print(f"Example plugin: User {username} connected.")
