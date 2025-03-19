import os
import gi
import subprocess
import json

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk, GdkPixbuf

# Setup translation
import gettext

_ = gettext.gettext

# Import the modules we've split off
from ui.pages.video_edit_ui import VideoEditUI
from ui.pages.video_processing import VideoProcessor
from ui.pages.video_edit_handlers import VideoEditHandlers


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
