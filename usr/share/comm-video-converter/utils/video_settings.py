"""
Unified video settings management module.
Provides constants, utilities, and management for video adjustments.
"""

# Default values for all video adjustments
DEFAULT_VALUES = {
    "brightness": 0.0,  # Range: -1.0 to 1.0
    "contrast": 1.0,  # Range: 0.0 to 2.0 (1.0 is neutral)
    "saturation": 1.0,  # Range: 0.0 to 2.0 (1.0 is neutral)
    "gamma": 1.0,  # Range: 0.0 to 3.0 (1.0 is neutral)
    "gamma_r": 1.0,  # Range: 0.0 to 3.0 (1.0 is neutral)
    "gamma_g": 1.0,  # Range: 0.0 to 3.0 (1.0 is neutral)
    "gamma_b": 1.0,  # Range: 0.0 to 3.0 (1.0 is neutral)
    "gamma_weight": 1.0,  # Range: 0.0 to 1.0 (1.0 is neutral)
    "hue": 0.0,  # Range: -3.14 to 3.14 radians (0.0 is neutral)
    "crop_left": 0,  # Pixels to crop from left
    "crop_right": 0,  # Pixels to crop from right
    "crop_top": 0,  # Pixels to crop from top
    "crop_bottom": 0,  # Pixels to crop from bottom
    "trim_start": 0.0,  # Start time for trimming (seconds)
    "trim_end": -1.0,  # End time for trimming (seconds, -1 means no trim)
}

# Settings key mapping
SETTING_KEYS = {
    "brightness": "preview-brightness",
    "contrast": "preview-contrast",
    "saturation": "preview-saturation",
    "gamma": "preview-gamma",
    "gamma_r": "preview-gamma-r",
    "gamma_g": "preview-gamma-g",
    "gamma_b": "preview-gamma-b",
    "gamma_weight": "preview-gamma-weight",
    "hue": "preview-hue",
    "crop_left": "preview-crop-left",
    "crop_right": "preview-crop-right",
    "crop_top": "preview-crop-top",
    "crop_bottom": "preview-crop-bottom",
    "trim_start": "video-trim-start",
    "trim_end": "video-trim-end",
}

# Threshold for determining if a value needs to be included
FLOAT_THRESHOLD = 0.01


#
# Value Access Functions
#
def get_adjustment_value(settings, name):
    """Get adjustment value from settings"""
    setting_key = SETTING_KEYS.get(name)
    if not setting_key:
        return DEFAULT_VALUES.get(name, 0)

    if name in ["crop_left", "crop_right", "crop_top", "crop_bottom"]:
        return settings.get_value(setting_key, DEFAULT_VALUES.get(name, 0))
    else:
        return settings.get_value(setting_key, DEFAULT_VALUES.get(name, 0.0))


def save_adjustment_value(settings, name, value):
    """Save an adjustment value to settings"""
    setting_key = SETTING_KEYS.get(name)
    if not setting_key:
        return False

    if name in ["crop_left", "crop_right", "crop_top", "crop_bottom"]:
        return settings.set_int(setting_key, value)
    else:
        return settings.set_double(setting_key, value)


def reset_adjustment(settings, name):
    """Reset an adjustment to its default value"""
    setting_key = SETTING_KEYS.get(name)
    if not setting_key:
        return False

    default_value = DEFAULT_VALUES.get(name)
    if default_value is None:
        return False

    if name in ["crop_left", "crop_right", "crop_top", "crop_bottom"]:
        return settings.set_int(setting_key, default_value)
    else:
        return settings.set_double(setting_key, default_value)


#
# Value Conversion Functions
#
def ui_to_ffmpeg_contrast(ui_contrast):
    """Convert UI contrast (0-2) to FFmpeg contrast (-1 to 1)"""
    return (ui_contrast - 1.0) * 2


def ui_to_ffmpeg_hue(ui_hue):
    """Convert UI hue (radians) to FFmpeg hue (degrees)"""
    return ui_hue * 180 / 3.14159


#
# FFmpeg Filter Generation
#
def generate_video_filters(settings, video_width=None, video_height=None):
    """
    Generate all needed FFmpeg filters in one go.

    Args:
        settings: Settings manager
        video_width: Width of the video (needed for crop)
        video_height: Height of the video (needed for crop)

    Returns:
        List of filter strings ready to join with commas
    """
    filters = []

    # DEBUG: Print settings values to verify they're being read
    debug_values = {
        "brightness": get_adjustment_value(settings, "brightness"),
        "contrast": get_adjustment_value(settings, "contrast"),
        "saturation": get_adjustment_value(settings, "saturation"),
        "gamma": get_adjustment_value(settings, "gamma"),
        "hue": get_adjustment_value(settings, "hue"),
    }
    print(f"Video adjustment values: {debug_values}")

    # 1. Add crop filter if needed
    crop_left = get_adjustment_value(settings, "crop_left")
    crop_right = get_adjustment_value(settings, "crop_right")
    crop_top = get_adjustment_value(settings, "crop_top")
    crop_bottom = get_adjustment_value(settings, "crop_bottom")

    if (
        (crop_left > 0 or crop_right > 0 or crop_top > 0 or crop_bottom > 0)
        and video_width is not None
        and video_height is not None
    ):
        crop_width = video_width - crop_left - crop_right
        crop_height = video_height - crop_top - crop_bottom

        if crop_width > 0 and crop_height > 0:
            filters.append(f"crop={crop_width}:{crop_height}:{crop_left}:{crop_top}")

    # 2. Add hue adjustment
    hue = get_adjustment_value(settings, "hue")
    if abs(hue) > FLOAT_THRESHOLD:
        hue_degrees = ui_to_ffmpeg_hue(hue)
        filters.append(f"hue=h={hue_degrees}")

    # 3. Add eq filter for brightness, contrast, saturation, gamma
    eq_parts = []

    brightness = get_adjustment_value(settings, "brightness")
    if abs(brightness) > FLOAT_THRESHOLD:
        eq_parts.append(f"brightness={brightness}")

    contrast = get_adjustment_value(settings, "contrast")
    if abs(contrast - 1.0) > FLOAT_THRESHOLD:
        # Convert to FFmpeg contrast range
        ff_contrast = ui_to_ffmpeg_contrast(contrast)
        eq_parts.append(f"contrast={ff_contrast}")

    saturation = get_adjustment_value(settings, "saturation")
    if abs(saturation - 1.0) > FLOAT_THRESHOLD:
        eq_parts.append(f"saturation={saturation}")

    gamma = get_adjustment_value(settings, "gamma")
    if abs(gamma - 1.0) > FLOAT_THRESHOLD:
        eq_parts.append(f"gamma={gamma}")

    gamma_r = get_adjustment_value(settings, "gamma_r")
    if abs(gamma_r - 1.0) > FLOAT_THRESHOLD:
        eq_parts.append(f"gamma_r={gamma_r}")

    gamma_g = get_adjustment_value(settings, "gamma_g")
    if abs(gamma_g - 1.0) > FLOAT_THRESHOLD:
        eq_parts.append(f"gamma_g={gamma_g}")

    gamma_b = get_adjustment_value(settings, "gamma_b")
    if abs(gamma_b - 1.0) > FLOAT_THRESHOLD:
        eq_parts.append(f"gamma_b={gamma_b}")

    gamma_weight = get_adjustment_value(settings, "gamma_weight")
    if abs(gamma_weight - 1.0) > FLOAT_THRESHOLD:
        eq_parts.append(f"gamma_weight={gamma_weight}")

    # Add eq filter if we have parts
    if eq_parts:
        filters.append("eq=" + ":".join(eq_parts))

    # 4. Add resolution scaling if needed
    video_resolution = settings.get_value("video-resolution", "")
    if video_resolution:
        # Ensure we use the right format (width:height)
        if "x" in video_resolution:
            video_resolution = video_resolution.replace("x", ":")
        filters.append(f"scale={video_resolution}")

    # Debug what filters were generated
    print(f"Generated filters: {filters}")

    return filters


def get_ffmpeg_filter_string(settings, video_width=None, video_height=None):
    """Get the complete FFmpeg filter string for command-line use"""
    filters = generate_video_filters(settings, video_width, video_height)

    if not filters:
        return ""

    filter_string = ",".join(filters)
    return f"-vf {filter_string}"


# Legacy functions kept for compatibility
generate_all_filters = generate_video_filters
get_video_filter_string = get_ffmpeg_filter_string


#
# Video Adjustment Manager
#
class VideoAdjustmentManager:
    """
    Manages video adjustment settings with UI updates.
    """

    def __init__(self, settings_manager, page=None):
        self.settings = settings_manager
        self.page = page

        # Cache adjustment values
        self.values = {}
        for name in DEFAULT_VALUES:
            self.values[name] = self.get_value(name)

    def get_value(self, name):
        """Get adjustment value from settings"""
        return get_adjustment_value(self.settings, name)

    def set_value(self, name, value, update_ui=True):
        """Set adjustment value and update UI if requested"""
        setting_key = SETTING_KEYS.get(name)
        if not setting_key:
            return False

        # Store value in cache
        self.values[name] = value

        # Save to settings
        success = save_adjustment_value(self.settings, name, value)

        # Update UI if requested
        if update_ui and success and self.page:
            self._update_ui_for_setting(name, value)

        return success

    def reset_value(self, name, update_ui=True):
        """Reset adjustment to default value"""
        default = DEFAULT_VALUES.get(name)
        if default is None:
            return False

        return self.set_value(name, default, update_ui)

    def reset_all_values(self, update_ui=True):
        """Reset all adjustments to defaults"""
        for name, default in DEFAULT_VALUES.items():
            self.set_value(name, default, False)

        if update_ui and self.page:
            self._update_all_ui()

        return True

    def _update_ui_for_setting(self, name, value):
        """Update UI control for a specific setting"""
        if not self.page or not hasattr(self.page, "ui"):
            return

        ui = self.page.ui

        # Map setting name to UI control
        ui_controls = {
            "brightness": getattr(ui, "brightness_scale", None),
            "contrast": getattr(ui, "contrast_scale", None),
            "saturation": getattr(ui, "saturation_scale", None),
            "gamma": getattr(ui, "gamma_scale", None),
            "gamma_r": getattr(ui, "red_gamma_scale", None),
            "gamma_g": getattr(ui, "green_gamma_scale", None),
            "gamma_b": getattr(ui, "blue_gamma_scale", None),
            "gamma_weight": getattr(ui, "gamma_weight_scale", None),
            "hue": getattr(ui, "hue_scale", None),
            "crop_left": getattr(ui, "crop_left_spin", None),
            "crop_right": getattr(ui, "crop_right_spin", None),
            "crop_top": getattr(ui, "crop_top_spin", None),
            "crop_bottom": getattr(ui, "crop_bottom_spin", None),
        }

        control = ui_controls.get(name)
        if control:
            control.set_value(value)

    def _update_all_ui(self):
        """Update all UI controls with current values"""
        # Update all controls
        for name, value in self.values.items():
            self._update_ui_for_setting(name, value)

        # Refresh preview if possible
        if hasattr(self.page, "processor") and hasattr(self.page, "current_position"):
            if hasattr(self.page, "invalidate_current_frame_cache"):
                self.page.invalidate_current_frame_cache()
            self.page.processor.extract_frame(self.page.current_position)
