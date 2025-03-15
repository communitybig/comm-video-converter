# core/json_settings_manager.py
import os
import json
from pathlib import Path


class JsonSettingsManager:
    """
    Simple JSON-based settings manager to replace GSettings
    for easier development without schema compilation.
    """

    # Valores padrão com base no seu schema
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
        # Encoding settings
        "gpu-selection": 0,
        "video-quality": 0,
        "video-codec": 0,
        "preset": 0,
        "subtitle-extract": 0,
        "audio-handling": 0,
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
        "preview-exposure": 0.0,
    }

    def __init__(self, schema_id):
        self.schema_id = schema_id
        self.json_config = {}

        # Determine config file location
        dev_file = Path("./dev_settings.json")
        config_dir = Path(os.path.expanduser("~/.config/bigiborg/comm-video-converter"))

        # Use dev file if it exists or we're in a writable directory
        if dev_file.exists() or os.access(".", os.W_OK):
            self.json_file = dev_file
            print(f"Using development settings: {dev_file}")
        else:
            # Otherwise use the user config directory
            config_dir.mkdir(parents=True, exist_ok=True)
            self.json_file = config_dir / "settings.json"
            print(f"Using user settings: {self.json_file}")

        # Load existing settings or create new file
        if self.json_file.exists():
            try:
                with open(self.json_file, "r") as f:
                    self.json_config = json.load(f)
                print(f"Loaded settings from {self.json_file}")
            except json.JSONDecodeError:
                print(f"Error parsing {self.json_file}, creating new file")
                self.json_config = {}
                self._save_json()
        else:
            # Create new settings file
            self.json_config = {}
            self._save_json()
            print(f"Created new settings file: {self.json_file}")

    def _save_json(self):
        """Save settings to JSON file"""
        try:
            # Get the directory path - works with both Path objects and strings
            directory = (
                self.json_file.parent
                if isinstance(self.json_file, Path)
                else os.path.dirname(str(self.json_file))
            )

            # Print debug info
            print(f"Saving settings to: {self.json_file}")
            print(f"Directory: {directory}")

            # Create directory if needed
            if str(directory) and str(directory) != ".":
                os.makedirs(directory, exist_ok=True)

            # Convert to string for open() if needed
            filepath_str = str(self.json_file)

            with open(filepath_str, "w") as f:
                json.dump(self.json_config, f, indent=2)

            print("Settings successfully saved")
            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False

    # Direct API for settings
    def get_string(self, key, default=None):
        if default is None:
            default = self.DEFAULT_VALUES.get(key, "")
        value = self.json_config.get(key, default)
        return str(value) if value is not None else default

    def get_boolean(self, key, default=None):
        if default is None:
            default = self.DEFAULT_VALUES.get(key, False)
        return bool(self.json_config.get(key, default))

    def get_int(self, key, default=None):
        if default is None:
            default = self.DEFAULT_VALUES.get(key, 0)
        try:
            return int(self.json_config.get(key, default))
        except (ValueError, TypeError):
            return default

    def get_double(self, key, default=None):
        if default is None:
            default = self.DEFAULT_VALUES.get(key, 0.0)
        try:
            return float(self.json_config.get(key, default))
        except (ValueError, TypeError):
            return default

    def set_string(self, key, value):
        self.json_config[key] = str(value) if value is not None else ""
        return self._save_json()

    def set_boolean(self, key, value):
        self.json_config[key] = bool(value)
        return self._save_json()

    def set_int(self, key, value):
        try:
            self.json_config[key] = int(value)
            return self._save_json()
        except (ValueError, TypeError):
            print(f"Error: Could not convert {value} to integer")
            return False

    def set_double(self, key, value):
        try:
            self.json_config[key] = float(value)
            return self._save_json()
        except (ValueError, TypeError):
            print(f"Error: Could not convert {value} to float")
            return False

    # Generic API compatible with existing code
    def load_setting(self, key, default=None):
        if default is None:
            default = self.DEFAULT_VALUES.get(key)
        return self.json_config.get(key, default)

    def save_setting(self, key, value):
        self.json_config[key] = value
        return self._save_json()
