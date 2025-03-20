import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GLib

# Setup translation
import gettext

_ = gettext.gettext

# Import the modules we've split off
from ui.video_edit_ui import VideoEditUI
from ui.video_processing import VideoProcessor
from ui.video_edit_handlers import VideoEditHandlers
from utils.video_adjustments import generate_video_filters

# Import the centralized adjustment utilities
from utils.video_adjustments import (
    DEFAULT_VALUES,
    FLOAT_THRESHOLD,
    get_adjustment_value,
    save_adjustment_value,
    reset_adjustment,
    ui_to_ffmpeg_contrast,
    ui_to_ffmpeg_hue,
    generate_all_filters,
)


class VideoEditPage:
    def __init__(self, app):
        self.app = app

        # Usar o settings_manager do app em vez de criar uma nova instância de Gio.Settings
        self.settings = app.settings_manager

        self.current_video_path = None
        self.video_duration = 0  # Duration in seconds
        self.current_position = 0  # Current position in seconds
        self.start_time = 0
        self.end_time = None  # None means end of video
        self.position_update_id = None
        self.position_changed_handler_id = None  # Store handler ID for blocking
        self.crop_update_timeout_id = None  # Timer ID for delayed crop updates

        # Crop selection variables - load from settings
        self.video_width = 0
        self.video_height = 0
        self.crop_left = self.settings.get_int("preview-crop-left", 0)
        self.crop_right = self.settings.get_int("preview-crop-right", 0)
        self.crop_top = self.settings.get_int("preview-crop-top", 0)
        self.crop_bottom = self.settings.get_int("preview-crop-bottom", 0)

        # Add property adjustment variables - load from settings
        self.brightness = self.settings.get_double("preview-brightness", 0.0)
        self.contrast = self.settings.get_double("preview-contrast", 1.0)
        self.saturation = self.settings.get_double("preview-saturation", 1.0)

        # Additional adjustment variables - load from settings
        self.gamma = self.settings.get_double("preview-gamma", 1.0)
        self.gamma_r = self.settings.get_double("preview-gamma-r", 1.0)
        self.gamma_g = self.settings.get_double("preview-gamma-g", 1.0)
        self.gamma_b = self.settings.get_double("preview-gamma-b", 1.0)
        self.gamma_weight = self.settings.get_double("preview-gamma-weight", 1.0)
        self.fps = None  # Custom FPS value
        self.hue = self.settings.get_double("preview-hue", 0.0)

        # Create a dictionary to store tooltips for different sliders and buttons
        self.adjustment_tooltips = {}
        self.button_tooltips = {}

        # Initialize the event handlers BEFORE the UI
        self.handlers = VideoEditHandlers(self)

        # Initialize the video processor
        self.processor = VideoProcessor(self)

        # Initialize the UI component AFTER handlers and processor
        self.ui = VideoEditUI(self)
        self.page = self.ui.create_page()

        # Add loading lock to prevent multiple simultaneous video loads
        self.loading_video = False
        self.requested_video_path = None

    # Add a destructor to ensure cleanup is called
    def __del__(self):
        self.cleanup()

    def set_video(self, file_path):
        """Set the video file from the main application and load it"""
        print(f"VideoEditPage.set_video called with file_path: {file_path}")

        # Verify path exists before loading
        if not file_path or not os.path.exists(file_path):
            print(f"Invalid file path for video: {file_path}")
            return False

        # Don't reload if it's already the current video
        if self.current_video_path == file_path:
            print(f"Video already loaded: {file_path}")
            return True

        # Store the requested path - do this first to prevent race conditions
        self.requested_video_path = file_path

        # If we're currently loading a video, don't start another load
        if self.loading_video:
            print("Already loading a video, can't load another one now")
            print(f"Will try again in 500ms: {file_path}")
            # Schedule another attempt after a short delay
            GLib.timeout_add(500, lambda: self._retry_load_video(file_path))
            return True

        # Start the loading process
        self.loading_video = True

        # Clear any existing video data
        self.current_video_path = None

        # Reset frame cache and position
        self.current_position = 0

        # Load video with a slight delay to ensure UI updates properly
        GLib.idle_add(lambda: self._delayed_load_video(file_path))
        return True

    def _retry_load_video(self, file_path):
        """Retry loading video after a short delay"""
        print(f"Retrying video load: {file_path}")

        # If still loading, reschedule
        if self.loading_video:
            print("Still loading previous video, will try again in 500ms")
            return True  # Continue trying

        # Check if the file still exists
        if not file_path or not os.path.exists(file_path):
            print(f"File no longer exists: {file_path}")
            return False

        # Try loading the video again
        return self.set_video(file_path)

    def _delayed_load_video(self, file_path):
        """Load video with a slight delay to ensure UI updates properly"""
        try:
            # Double-check requested path is still valid
            if not file_path or not os.path.exists(file_path):
                print(f"File no longer exists: {file_path}")
                self.loading_video = False
                return False

            # Make sure this is still the file we want to load
            if hasattr(self.app, "preview_file_path") and self.app.preview_file_path:
                if file_path != self.app.preview_file_path:
                    print(
                        f"Ignoring conflicting video load: requested={self.app.preview_file_path}, attempted={file_path}"
                    )
                    self.loading_video = False
                    return False

            # Make sure this is the file we're supposed to load
            if file_path != self.requested_video_path:
                print(
                    f"Conflicting load requests. Requested: {self.requested_video_path}, Loading: {file_path}"
                )
                # Don't reset loading flag here - let the proper requested file load
                return False

            # Update UI to indicate loading
            self.ui.info_filename_label.set_text(_("Loading..."))

            # Perform the actual loading
            result = self.processor.load_video(file_path)
            print(f"Video load result for {os.path.basename(file_path)}: {result}")

            # Always reset the loading flag when done, regardless of success
            self.loading_video = False

            return False  # Don't repeat
        except Exception as e:
            print(f"Error in delayed video loading: {e}")
            import traceback

            traceback.print_exc()
            # Make sure to reset loading flag even on error
            self.loading_video = False
            return False

    def get_page(self):
        return self.page

    def format_resolution(self, width, height):
        """
        Format resolution string with the correct separator.
        FFmpeg requires width:height format (not width×height).

        Args:
            width (int): Video width
            height (int): Video height

        Returns:
            str: Formatted resolution string (e.g. "1920:1080")
        """
        return f"{width}:{height}"

    def cleanup(self):
        """Clean up resources when the page is destroyed"""
        # Cancel any pending crop update
        if hasattr(self, "crop_update_timeout_id") and self.crop_update_timeout_id:
            GLib.source_remove(self.crop_update_timeout_id)
            self.crop_update_timeout_id = None

        # Clear any update timers
        if hasattr(self, "position_update_id") and self.position_update_id:
            GLib.source_remove(self.position_update_id)
            self.position_update_id = None

    def invalidate_current_frame_cache(self):
        """Invalidate the cache for the current position - no longer needed"""
        # This is now a no-op since we're not caching frames
        pass

    def extract_frame(self, position):
        """Extract a frame at the specified position using FFmpeg"""
        if not self.current_video_path:
            print("Cannot extract frame - no video loaded")
            return None

        try:
            # Get the filters using our shared utility
            filters = generate_video_filters(
                self.settings,
                video_width=self.video_width,
                video_height=self.video_height,
            )

            filter_arg = ",".join(filters) if filters else "null"

            # Print the filter for debugging
            print(f"FFmpeg filter: {filter_arg}")

        except Exception as e:
            print(f"Error extracting frame: {e}")
            import traceback

            traceback.print_exc()
            return False

        # Generate a temp filename for the frame
        output_file = os.path.join(
            self.temp_preview_dir, f"frame_{int(position * 100)}.jpg"
        )

        # Use the centralized filter utilities
        filters = generate_all_filters(
            self.settings, video_width=self.video_width, video_height=self.video_height
        )

        # Add video resolution filter if needed
        video_resolution = self.settings.load_setting("video-resolution", "")
        if video_resolution:
            filters.insert(0, f"scale={video_resolution}")

        filter_arg = ",".join(filters) if filters else "null"

        # Print the filter for debugging
        print(f"FFmpeg filter for frame extraction: {filter_arg}")

    def on_brightness_changed(self, scale, value_label=None):
        """Handle brightness slider changes"""
        brightness = scale.get_value()

        # Save to settings using the centralized utility
        save_adjustment_value(self.settings, "brightness", brightness)

        if value_label:
            value_label.set_text(f"{brightness:.2f}")

        # Update current frame with new settings
        self.extract_frame(self.current_position)

    def on_contrast_changed(self, scale, value_label=None):
        """Handle contrast slider changes"""
        contrast = scale.get_value()

        # Save to settings using the centralized utility
        save_adjustment_value(self.settings, "contrast", contrast)

        if value_label:
            value_label.set_text(f"{contrast:.2f}")

        # For debugging, show the FFmpeg value
        ff_contrast = ui_to_ffmpeg_contrast(contrast)
        print(f"UI contrast: {contrast:.2f}, FFmpeg contrast: {ff_contrast:.2f}")

        # Update current frame with new settings
        self.extract_frame(self.current_position)

    def reset_brightness(self):
        """Reset brightness to default"""
        reset_adjustment(self.settings, "brightness")
        self.brightness = get_adjustment_value(self.settings, "brightness")
        self.brightness_scale.set_value(self.brightness)
        self.extract_frame(self.current_position)

    def on_crop_value_changed(self, widget):
        """Handle changes to crop spinbutton values with delayed update"""
        # Get and store all crop values
        self.crop_left = int(self.crop_left_spin.get_value())
        self.crop_right = int(self.crop_right_spin.get_value())
        self.crop_top = int(self.crop_top_spin.get_value())
        self.crop_bottom = int(self.crop_bottom_spin.get_value())

        # Save using the centralized utility
        save_adjustment_value(self.settings, "crop_left", self.crop_left)
        save_adjustment_value(self.settings, "crop_right", self.crop_right)
        save_adjustment_value(self.settings, "crop_top", self.crop_top)
        save_adjustment_value(self.settings, "crop_bottom", self.crop_bottom)
