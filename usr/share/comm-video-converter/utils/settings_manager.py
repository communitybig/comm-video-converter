# core/settings_manager.py
import os
import json
from pathlib import Path

# Setup translation
import gettext

_ = gettext.gettext


class SettingsManager:
    """
    Manages application settings using JSON file.
    Handles both production and development settings.
    """

    # Default values with direct string values instead of indexes
    DEFAULT_VALUES = {
        # General settings
        "last-accessed-directory": "",
        "output-folder": "",
        "delete-original": False,
        "show-single-help-on-startup": True,
        "show-conversion-help-on-startup": True,
        # Batch conversion settings
        "search-directory": "",
        "max-processes": 2,
        "min-mp4-size": 1024,
        "log-file": "mkv-mp4-convert.log",
        "delete-batch-originals": False,
        # Encoding settings - use direct string values
        "gpu": "auto",  # Directly use string value
        "video-quality": "medium",  # Directly use string value
        "video-codec": "h264",  # Directly use string value
        "preset": "medium",  # Directly use string value
        "subtitle-extract": "extract",  # Directly use string value
        "audio-handling": "copy",  # Already using string value
        # Advanced audio settings
        "audio-bitrate": "",
        "audio-channels": "",
        # Advanced video settings
        "video-resolution": "",
        "additional-options": "",
        # Conversion mode switches
        "gpu-partial": False,
        "force-copy-video": False,
        "only-extract-subtitles": False,
        # Video preview settings
        "preview-crop-left": 0,
        "preview-crop-right": 0,
        "preview-crop-top": 0,
        "preview-crop-bottom": 0,
        "preview-brightness": 0.0,
        "preview-contrast": 1.0,
        "preview-saturation": 1.0,
        "preview-gamma": 1.0,
        "preview-gamma-r": 1.0,
        "preview-gamma-g": 1.0,
        "preview-gamma-b": 1.0,
        "preview-gamma-weight": 1.0,
        "preview-hue": 0.0,
    }

    def __init__(self, app_id, dev_mode=False, dev_settings_file=None):
        self.app_id = app_id
        self.settings = {}
        self.dev_mode = dev_mode

        # Set up production paths
        self.prod_settings_dir = os.path.expanduser("~/.config/comm-video-converter")
        self.prod_settings_file = os.path.join(self.prod_settings_dir, "settings.json")

        # Set up development paths
        if dev_mode and dev_settings_file:
            self.dev_settings_file = dev_settings_file
            # Make sure we have an absolute path
            if not os.path.isabs(self.dev_settings_file):
                # Convert to absolute path relative to current directory
                self.dev_settings_file = os.path.abspath(self.dev_settings_file)
            self.settings_file = self.dev_settings_file
            print(f"Using development settings: {self.settings_file}")
        else:
            self.dev_settings_file = None
            self.settings_file = self.prod_settings_file
            print(f"Using production settings: {self.settings_file}")

        # Get the actual settings directory from the file path
        self.settings_dir = os.path.dirname(self.settings_file)

        # Ensure settings directory exists
        if self.settings_dir:
            os.makedirs(self.settings_dir, exist_ok=True)

        # Load settings from file if it exists
        self.load_from_disk()

    def load_from_disk(self):
        """Load settings from JSON file"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r") as f:
                    self.settings = json.load(f)
                print(f"Loaded settings from: {self.settings_file}")
            else:
                print(
                    f"Settings file not found, will be created at: {self.settings_file}"
                )
        except Exception as e:
            print(f"Error loading settings: {e}")
            self.settings = {}

    def save_to_disk(self):
        """Save settings to JSON file"""
        try:
            # Log the path we're trying to save to
            print(f"Attempting to save settings to: {self.settings_file}")

            # Make sure the directory exists
            if not self.settings_dir:
                raise ValueError("Settings directory path is empty")
            os.makedirs(self.settings_dir, exist_ok=True)

            # Clean up empty string settings to avoid confusion
            for key, value in list(self.settings.items()):
                if (
                    value == ""
                    and key in self.DEFAULT_VALUES
                    and self.DEFAULT_VALUES[key] == ""
                ):
                    # For empty string settings with empty string defaults, keep them
                    pass
                elif value == "":
                    # For other empty strings, replace with default
                    if key in self.DEFAULT_VALUES:
                        self.settings[key] = self.DEFAULT_VALUES[key]

            # Save the settings
            with open(self.settings_file, "w") as f:
                json.dump(self.settings, f, indent=2)
            print(f"Successfully saved settings to: {self.settings_file}")
            return True
        except Exception as e:
            print(f"Error saving settings: {str(e)}")
            # If we're in dev mode, try to save to production as backup
            if self.dev_mode:
                try:
                    print("Trying to save to production settings as backup...")
                    os.makedirs(self.prod_settings_dir, exist_ok=True)
                    with open(self.prod_settings_file, "w") as f:
                        json.dump(self.settings, f, indent=2)
                    print(
                        f"Successfully saved settings to backup location: {self.prod_settings_file}"
                    )
                    return True
                except Exception as backup_e:
                    print(f"Backup save also failed: {str(backup_e)}")
            return False

    # Type-specific getters and setters from JsonSettingsManager
    def get_string(self, key, default=None):
        if default is None:
            default = self.DEFAULT_VALUES.get(key, "")
        value = self.settings.get(key, default)
        return str(value) if value is not None else default

    def get_boolean(self, key, default=None):
        if default is None:
            default = self.DEFAULT_VALUES.get(key, False)
        return bool(self.settings.get(key, default))

    def get_int(self, key, default=None):
        if default is None:
            default = self.DEFAULT_VALUES.get(key, 0)
        try:
            return int(self.settings.get(key, default))
        except (ValueError, TypeError):
            return default

    def get_double(self, key, default=None):
        if default is None:
            default = self.DEFAULT_VALUES.get(key, 0.0)
        try:
            return float(self.settings.get(key, default))
        except (ValueError, TypeError):
            return default

    def set_string(self, key, value):
        self.settings[key] = str(value) if value is not None else ""
        return self.save_to_disk()

    def set_boolean(self, key, value):
        self.settings[key] = bool(value)
        return self.save_to_disk()

    def set_int(self, key, value):
        try:
            self.settings[key] = int(value)
            return self.save_to_disk()
        except (ValueError, TypeError):
            print(f"Error: Could not convert {value} to integer")
            return False

    def set_double(self, key, value):
        try:
            self.settings[key] = float(value)
            return self.save_to_disk()
        except (ValueError, TypeError):
            print(f"Error: Could not convert {value} to float")
            return False

    # Original generic API for backwards compatibility
    def load_setting(self, key, default=None):
        """Load a setting from the settings dictionary"""
        if default is None:
            default = self.DEFAULT_VALUES.get(key)
        return self.settings.get(key, default)

    def save_setting(self, key, value):
        """Save a setting to the settings dictionary and persist to disk"""
        try:
            # Update in-memory settings
            self.settings[key] = value
            print(f"Setting updated in memory: {key} = {value}")
            # Persist to disk
            success = self.save_to_disk()
            return success
        except Exception as e:
            print(f"Error saving setting {key}: {str(e)}")
            return False
