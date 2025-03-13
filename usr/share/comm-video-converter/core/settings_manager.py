# core/settings_manager.py
import os
import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio

class SettingsManager:
    """
    Manages application settings using GSettings.
    Provides methods to save and load settings with fallback to default values.
    """
    def __init__(self, schema_id):
        self.schema_id = schema_id
        self.settings = None
        self.init_settings()
    
    def init_settings(self):
        """Initialize GSettings for the application"""
        try:
            # First try to get schema from default source
            schema_source = Gio.SettingsSchemaSource.get_default()
            schema = schema_source.lookup(self.schema_id, True)
            
            if schema:
                self.settings = Gio.Settings.new(self.schema_id)
                print(f"GSettings initialized with schema: {self.schema_id}")
                return
            
            # If not found, try to find in current directory during development
            schema_dir = os.path.dirname(os.path.abspath(__file__))
            schema_source = Gio.SettingsSchemaSource.new_from_directory(
                schema_dir, Gio.SettingsSchemaSource.get_default(), False)
                
            if schema_source:
                schema = schema_source.lookup(self.schema_id, True)
                if schema:
                    self.settings = Gio.Settings.new(self.schema_id)
                    print(f"GSettings initialized with local schema: {self.schema_id}")
                    return
                    
            print("Warning: GSettings schema not found. Settings will not be saved.")
        except Exception as e:
            print(f"Error initializing GSettings: {e}")
    
    def load_setting(self, key, default=None):
        """Load a setting from GSettings with fallback to default"""
        if not self.settings:
            return default
            
        try:
            schema = self.settings.get_property("settings-schema")
            if not schema.has_key(key):
                return default
                
            value_type = schema.get_key(key).get_value_type().dup_string()
            
            if value_type == 's':
                value = self.settings.get_string(key)
                return value if value else default
            elif value_type == 'b':
                return self.settings.get_boolean(key)
            elif value_type == 'i':
                return self.settings.get_int(key)
            elif value_type == 'd':
                return self.settings.get_double(key)
            else:
                return default
        except Exception as e:
            print(f"Error loading setting {key}: {e}")
            return default
    
    def save_setting(self, key, value):
        """Save a setting to GSettings"""
        if not self.settings:
            return False
            
        try:
            schema = self.settings.get_property("settings-schema")
            if not schema.has_key(key):
                print(f"Warning: Key {key} not found in schema")
                return False
                
            value_type = schema.get_key(key).get_value_type().dup_string()
            
            if value_type == 's':
                return self.settings.set_string(key, str(value) if value is not None else '')
            elif value_type == 'b':
                return self.settings.set_boolean(key, bool(value))
            elif value_type == 'i':
                return self.settings.set_int(key, int(value))
            elif value_type == 'd':
                return self.settings.set_double(key, float(value))
            else:
                print(f"Warning: Unsupported type {value_type} for {key}")
                return False
        except Exception as e:
            print(f"Error saving setting {key}: {e}")
            return False