"""
VideoAdjustmentManager - centralized manager for all video adjustment settings.
This module eliminates duplicated code for accessing settings by providing
a single interface for all video adjustment operations.
"""

import os
from utils.video_adjustments import DEFAULT_VALUES, SETTING_KEYS, FLOAT_THRESHOLD


class VideoAdjustmentManager:
    """
    Manages all video adjustment settings, providing a single interface
    for getting, setting, and resetting values.
    """

    def __init__(self, settings_manager, page=None):
        """
        Initialize with the application's settings manager

        Args:
            settings_manager: Application settings manager that provides get/set methods
            page: Optional reference to the video edit page for UI updates
        """
        self.settings = settings_manager
        self.page = page

        # Initialize adjustment values from settings
        self.values = {}
        self.load_all_values()

    def load_all_values(self):
        """Load all adjustment values from settings"""
        for name, default in DEFAULT_VALUES.items():
            self.values[name] = self.get_value(name)

    def get_value(self, name):
        """
        Get the value of a specific adjustment

        Args:
            name: Name of the adjustment (e.g., "brightness", "crop_left")

        Returns:
            Current value of the adjustment
        """
        setting_key = SETTING_KEYS.get(name)
        if not setting_key:
            return DEFAULT_VALUES.get(name)

        if name in ["crop_left", "crop_right", "crop_top", "crop_bottom"]:
            return self.settings.get_int(setting_key, DEFAULT_VALUES.get(name, 0))
        else:
            return self.settings.get_double(setting_key, DEFAULT_VALUES.get(name, 0.0))

    def set_value(self, name, value, update_ui=True):
        """
        Set the value of a specific adjustment

        Args:
            name: Name of the adjustment
            value: Value to set
            update_ui: Whether to update UI after setting the value

        Returns:
            Success status
        """
        setting_key = SETTING_KEYS.get(name)
        if not setting_key:
            return False

        # Store the value in our local cache
        self.values[name] = value

        # Save to settings storage
        success = False
        if name in ["crop_left", "crop_right", "crop_top", "crop_bottom"]:
            success = self.settings.set_int(setting_key, value)
        else:
            success = self.settings.set_double(setting_key, value)

        # Update UI if requested and if we have access to the page
        if update_ui and success and self.page:
            self._update_ui_for_setting(name, value)

        return success

    def reset_value(self, name, update_ui=True):
        """
        Reset a specific adjustment to its default value

        Args:
            name: Name of the adjustment to reset
            update_ui: Whether to update UI after resetting

        Returns:
            Success status
        """
        default_value = DEFAULT_VALUES.get(name)
        if default_value is None:
            return False

        success = self.set_value(name, default_value, update_ui=False)

        # Update UI if requested
        if update_ui and success and self.page:
            self._update_ui_for_setting(name, default_value)

        return success

    def reset_all_values(self, update_ui=True):
        """
        Reset all adjustments to their default values

        Args:
            update_ui: Whether to update UI after resetting

        Returns:
            Success status (True if all resets succeeded)
        """
        all_success = True

        for name, default_value in DEFAULT_VALUES.items():
            success = self.set_value(name, default_value, update_ui=False)
            if not success:
                all_success = False

        # Update all UI elements at once if requested
        if update_ui and self.page:
            self._update_all_ui()

        return all_success

    def _update_ui_for_setting(self, name, value):
        """
        Update UI element for a specific setting

        Args:
            name: Name of the adjustment
            value: New value
        """
        if not self.page or not hasattr(self.page, "ui"):
            return

        # Update UI based on setting type
        if name == "brightness" and hasattr(self.page.ui, "brightness_scale"):
            self.page.ui.brightness_scale.set_value(value)

        elif name == "contrast" and hasattr(self.page.ui, "contrast_scale"):
            self.page.ui.contrast_scale.set_value(value)

        elif name == "saturation" and hasattr(self.page.ui, "saturation_scale"):
            self.page.ui.saturation_scale.set_value(value)

        elif name == "gamma" and hasattr(self.page.ui, "gamma_scale"):
            self.page.ui.gamma_scale.set_value(value)

        elif name == "gamma_r" and hasattr(self.page.ui, "red_gamma_scale"):
            self.page.ui.red_gamma_scale.set_value(value)

        elif name == "gamma_g" and hasattr(self.page.ui, "green_gamma_scale"):
            self.page.ui.green_gamma_scale.set_value(value)

        elif name == "gamma_b" and hasattr(self.page.ui, "blue_gamma_scale"):
            self.page.ui.blue_gamma_scale.set_value(value)

        elif name == "gamma_weight" and hasattr(self.page.ui, "gamma_weight_scale"):
            self.page.ui.gamma_weight_scale.set_value(value)

        elif name == "hue" and hasattr(self.page.ui, "hue_scale"):
            self.page.ui.hue_scale.set_value(value)

        elif name == "crop_left" and hasattr(self.page.ui, "crop_left_spin"):
            self.page.ui.crop_left_spin.set_value(value)

        elif name == "crop_right" and hasattr(self.page.ui, "crop_right_spin"):
            self.page.ui.crop_right_spin.set_value(value)

        elif name == "crop_top" and hasattr(self.page.ui, "crop_top_spin"):
            self.page.ui.crop_top_spin.set_value(value)

        elif name == "crop_bottom" and hasattr(self.page.ui, "crop_bottom_spin"):
            self.page.ui.crop_bottom_spin.set_value(value)

    def _update_all_ui(self):
        """Update all UI elements with current values"""
        for name, value in self.values.items():
            self._update_ui_for_setting(name, value)

        # If there's a processor, refresh the preview
        if hasattr(self.page, "processor") and hasattr(self.page, "current_position"):
            # Invalidate the cache first
            if hasattr(self.page, "invalidate_current_frame_cache"):
                self.page.invalidate_current_frame_cache()
            # Then extract a new frame with updated settings
            self.page.processor.extract_frame(self.page.current_position)

    def get_all_values(self):
        """Get dictionary of all adjustment values"""
        return self.values.copy()

    def apply_settings_to_page(self, page):
        """
        Apply all settings directly to page attributes

        Args:
            page: The video_edit_page instance to update
        """
        for name, value in self.values.items():
            if hasattr(page, name):
                setattr(page, name, value)
