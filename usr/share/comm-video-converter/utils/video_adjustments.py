"""
Centralized handling of video adjustment parameters.
This file serves as the single source of truth for all video adjustment operations,
including default values, UI-to-FFmpeg conversions, and filter generation.
"""

import subprocess
import os

# Default values for all video adjustments
DEFAULT_VALUES = {
    "brightness": 0.0,  # Range: -1.0 to 1.0
    "contrast": 1.0,  # UI Range: 0.0 to 2.0 (1.0 is neutral)
    "saturation": 1.0,  # Range: 0.0 to 2.0 (1.0 is neutral)
    "gamma": 1.0,  # Range: 0.0 to 16.0 (1.0 is neutral)
    "gamma_r": 1.0,  # Range: 0.0 to 16.0 (1.0 is neutral)
    "gamma_g": 1.0,  # Range: 0.0 to 16.0 (1.0 is neutral)
    "gamma_b": 1.0,  # Range: 0.0 to 16.0 (1.0 is neutral)
    "gamma_weight": 1.0,  # Range: 0.0 to 1.0 (1.0 is neutral)
    "hue": 0.0,  # Range: -3.14 to 3.14 radians (0.0 is neutral)
    "crop_left": 0,  # Pixels to crop from left
    "crop_right": 0,  # Pixels to crop from right
    "crop_top": 0,  # Pixels to crop from top
    "crop_bottom": 0,  # Pixels to crop from bottom
}

# Setting keys in the settings storage - prefix with 'preview-' for consistency
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
}

# Threshold for determining if a value is different from default
FLOAT_THRESHOLD = 0.01


def ui_to_ffmpeg_contrast(ui_contrast):
    """
    Convert contrast from UI range to FFmpeg range.
    UI range: 0.0-2.0 with 1.0 as neutral
    FFmpeg range: -1.0 to 1.0 with 0.0 as neutral
    """
    return (ui_contrast - 1.0) * 2


def ui_to_ffmpeg_hue(ui_hue):
    """
    Convert hue from UI radians to FFmpeg degrees.
    UI range: -3.14 to 3.14 radians
    FFmpeg range: -180 to 180 degrees
    """
    return ui_hue * 180 / 3.14159


def get_adjustment_value(settings, adjustment_name):
    """
    Get the current value of a specific adjustment from settings.

    Args:
        settings: The settings manager object
        adjustment_name: Name of the adjustment (e.g., "brightness", "contrast")

    Returns:
        Current value of the adjustment, or default if not found
    """
    setting_key = SETTING_KEYS.get(adjustment_name)
    if not setting_key:
        return DEFAULT_VALUES.get(adjustment_name, 0.0)

    if adjustment_name in ["crop_left", "crop_right", "crop_top", "crop_bottom"]:
        return settings.get_int(setting_key, DEFAULT_VALUES.get(adjustment_name, 0))
    else:
        return settings.get_double(
            setting_key, DEFAULT_VALUES.get(adjustment_name, 0.0)
        )


def save_adjustment_value(settings, adjustment_name, value):
    """
    Save an adjustment value to settings.

    Args:
        settings: The settings manager object
        adjustment_name: Name of the adjustment (e.g., "brightness", "contrast")
        value: The value to save

    Returns:
        Success status from settings save operation
    """
    setting_key = SETTING_KEYS.get(adjustment_name)
    if not setting_key:
        return False

    if adjustment_name in ["crop_left", "crop_right", "crop_top", "crop_bottom"]:
        return settings.set_int(setting_key, value)
    else:
        return settings.set_double(setting_key, value)


def reset_adjustment(settings, adjustment_name):
    """
    Reset a specific adjustment to its default value.

    Args:
        settings: The settings manager object
        adjustment_name: Name of the adjustment to reset

    Returns:
        Success status
    """
    setting_key = SETTING_KEYS.get(adjustment_name)
    if not setting_key:
        return False

    # If settings manager has a reset method, use it
    if hasattr(settings, "reset") and callable(settings.reset):
        return settings.reset(setting_key)

    # Otherwise, save the default value
    default_value = DEFAULT_VALUES.get(adjustment_name, 0.0)

    if adjustment_name in ["crop_left", "crop_right", "crop_top", "crop_bottom"]:
        return settings.set_int(setting_key, default_value)
    else:
        return settings.set_double(setting_key, default_value)


def get_all_adjustments(settings):
    """
    Get a dictionary of all adjustment values from settings.

    Args:
        settings: The settings manager object

    Returns:
        Dictionary of all adjustment values
    """
    adjustments = {}
    for adjustment_name in DEFAULT_VALUES:
        adjustments[adjustment_name] = get_adjustment_value(settings, adjustment_name)
    return adjustments


def generate_eq_filter(settings):
    """
    Generate a FFmpeg 'eq' filter string based on the current settings.

    Args:
        settings: The settings manager object

    Returns:
        eq filter string or None if no adjustments needed
    """
    eq_parts = []

    # Brightness
    brightness = get_adjustment_value(settings, "brightness")
    if abs(brightness) > FLOAT_THRESHOLD:
        eq_parts.append(f"brightness={brightness}")

    # Contrast (needs conversion from UI to FFmpeg value)
    contrast = get_adjustment_value(settings, "contrast")
    if abs(contrast - 1.0) > FLOAT_THRESHOLD:
        ff_contrast = ui_to_ffmpeg_contrast(contrast)
        eq_parts.append(f"contrast={ff_contrast}")

    # Saturation
    saturation = get_adjustment_value(settings, "saturation")
    if abs(saturation - 1.0) > FLOAT_THRESHOLD:
        eq_parts.append(f"saturation={saturation}")

    # Gamma
    gamma = get_adjustment_value(settings, "gamma")
    if abs(gamma - 1.0) > FLOAT_THRESHOLD:
        eq_parts.append(f"gamma={gamma}")

    # Gamma R
    gamma_r = get_adjustment_value(settings, "gamma_r")
    if abs(gamma_r - 1.0) > FLOAT_THRESHOLD:
        eq_parts.append(f"gamma_r={gamma_r}")

    # Gamma G
    gamma_g = get_adjustment_value(settings, "gamma_g")
    if abs(gamma_g - 1.0) > FLOAT_THRESHOLD:
        eq_parts.append(f"gamma_g={gamma_g}")

    # Gamma B
    gamma_b = get_adjustment_value(settings, "gamma_b")
    if abs(gamma_b - 1.0) > FLOAT_THRESHOLD:
        eq_parts.append(f"gamma_b={gamma_b}")

    # Gamma Weight
    gamma_weight = get_adjustment_value(settings, "gamma_weight")
    if abs(gamma_weight - 1.0) > FLOAT_THRESHOLD:
        eq_parts.append(f"gamma_weight={gamma_weight}")

    # If we have eq parts, return the filter string
    if eq_parts:
        return "eq=" + ":".join(eq_parts)

    return None


def generate_hue_filter(settings):
    """
    Generate a FFmpeg 'hue' filter string based on the current settings.

    Args:
        settings: The settings manager object

    Returns:
        hue filter string or None if no hue adjustment needed
    """
    hue = get_adjustment_value(settings, "hue")

    if abs(hue) > FLOAT_THRESHOLD:
        hue_degrees = ui_to_ffmpeg_hue(hue)
        return f"hue=h={hue_degrees}"

    return None


def generate_crop_filter(settings, video_width=None, video_height=None):
    """
    Generate a FFmpeg 'crop' filter string based on the current settings.

    Args:
        settings: The settings manager object
        video_width: Width of the video (required for crop)
        video_height: Height of the video (required for crop)

    Returns:
        crop filter string or None if no cropping needed or dimensions unknown
    """
    crop_left = get_adjustment_value(settings, "crop_left")
    crop_right = get_adjustment_value(settings, "crop_right")
    crop_top = get_adjustment_value(settings, "crop_top")
    crop_bottom = get_adjustment_value(settings, "crop_bottom")

    # Only proceed if we have crop values and video dimensions
    if (
        (crop_left > 0 or crop_right > 0 or crop_top > 0 or crop_bottom > 0)
        and video_width is not None
        and video_height is not None
    ):
        crop_width = video_width - crop_left - crop_right
        crop_height = video_height - crop_top - crop_bottom

        if crop_width > 0 and crop_height > 0:
            return f"crop={crop_width}:{crop_height}:{crop_left}:{crop_top}"

    return None


def generate_all_filters(settings, video_width=None, video_height=None):
    """
    Generate a list of all necessary FFmpeg filters based on the current settings.

    Args:
        settings: The settings manager object
        video_width: Width of the video
        video_height: Height of the video

    Returns:
        List of filter strings
    """
    filters = []

    # Crop filter
    crop_filter = generate_crop_filter(settings, video_width, video_height)
    if crop_filter:
        filters.append(crop_filter)

    # Hue filter
    hue_filter = generate_hue_filter(settings)
    if hue_filter:
        filters.append(hue_filter)

    # Eq filter for color adjustments
    eq_filter = generate_eq_filter(settings)
    if eq_filter:
        filters.append(eq_filter)

    return filters


def generate_video_filters(
    settings, video_path=None, video_width=None, video_height=None
):
    """
    Generate FFmpeg video filters based on settings.

    Args:
        settings: The settings manager object with get_double, get_int methods
        video_path: Optional path to video file (for getting dimensions if needed)
        video_width: Optional width of the video (for crop calculations)
        video_height: Optional height of the video (for crop calculations)

    Returns:
        A list of filter strings that can be joined with commas for FFmpeg
    """
    # If we don't have dimensions but have a video path, try to get dimensions
    if (
        (video_width is None or video_height is None)
        and video_path
        and os.path.exists(video_path)
    ):
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height",
                    "-of",
                    "csv=p=0",
                    video_path,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            video_width, video_height = map(int, result.stdout.strip().split(","))
            print(f"Detected video dimensions: {video_width}x{video_height}")
        except Exception as e:
            print(f"Error getting video dimensions: {e}")

    # Use the centralized function to generate filters
    all_filters = generate_all_filters(settings, video_width, video_height)

    # Handle video resolution explicitly here if needed
    video_resolution = settings.load_setting("video-resolution", "")
    if video_resolution:
        all_filters.insert(0, f"scale={video_resolution}")

    # Print debug info
    print_debug_info(settings)

    return all_filters


def get_video_filter_string(
    settings, video_path=None, video_width=None, video_height=None
):
    """
    Get the complete FFmpeg video filter string ready to use in a command.

    Args:
        settings: The settings manager object
        video_path: Optional path to video file (for getting dimensions if needed)
        video_width: Optional width of the video
        video_height: Optional height of the video

    Returns:
        A string in the format "-vf filter1,filter2,..." or empty string if no filters
    """
    filters = generate_video_filters(settings, video_path, video_width, video_height)

    if filters:
        filter_string = ",".join(filters)
        return f"-vf {filter_string}"

    return ""


def get_filter_string(settings, video_width=None, video_height=None):
    """
    Get a complete FFmpeg filter string for video adjustments.

    Args:
        settings: The settings manager object
        video_width: Width of the video
        video_height: Height of the video

    Returns:
        FFmpeg filter string in the format "-vf filter1,filter2,..."
        or empty string if no filters are needed
    """
    filters = generate_all_filters(settings, video_width, video_height)

    if filters:
        filter_string = ",".join(filters)
        return f"-vf {filter_string}"

    return ""


def print_debug_info(settings):
    """
    Print debug information about the current adjustment values.

    Args:
        settings: The settings manager object
    """
    print("=== VIDEO ADJUSTMENT DEBUG INFO ===")

    # Print raw values
    print("Raw Settings Values:")
    for name in DEFAULT_VALUES:
        value = get_adjustment_value(settings, name)
        print(f"  {name}: {value}")

    # Print computed FFmpeg filters
    print("\nComputed FFmpeg Filters:")
    filters = generate_all_filters(settings)
    for filter_str in filters:
        print(f"  {filter_str}")

    # Print contrast transformation specifically since it's often misunderstood
    contrast = get_adjustment_value(settings, "contrast")
    ff_contrast = ui_to_ffmpeg_contrast(contrast)
    print(f"\nContrast Transformation:")
    print(f"  UI Value: {contrast}")
    print(f"  FFmpeg Value: {ff_contrast}")
    print(f"  Formula: (UI_value - 1.0) * 2")

    print("===================================")
