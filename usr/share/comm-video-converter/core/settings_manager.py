# core/settings_manager.py
import os
import json

class SettingsManager:
    """
    Manages application settings using JSON file.
    Handles both production and development settings.
    """
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
                with open(self.settings_file, 'r') as f:
                    self.settings = json.load(f)
                print(f"Loaded settings from: {self.settings_file}")
            else:
                print(f"Settings file not found, will be created at: {self.settings_file}")
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
            
            # Save the settings
            with open(self.settings_file, 'w') as f:
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
                    with open(self.prod_settings_file, 'w') as f:
                        json.dump(self.settings, f, indent=2)
                    print(f"Successfully saved settings to backup location: {self.prod_settings_file}")
                    return True
                except Exception as backup_e:
                    print(f"Backup save also failed: {str(backup_e)}")
            
            return False
    
    def load_setting(self, key, default=None):
        """Load a setting from the settings dictionary"""
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