#!/usr/bin/env python3
"""
Main entry point for Comm Video Converter application.
"""

import os
import sys
import gi
from collections import deque

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib, Gdk

# Import local modules
from constants import APP_ID, VIDEO_FILE_MIME_TYPES
from ui.widgets.header_bar import HeaderBar
from ui.pages.conversion_page import ConversionPage
from ui.pages.video_edit_page import VideoEditPage
from ui.pages.settings_page import SettingsPage
from ui.pages.progress_page import ProgressPage
from core.json_settings_manager import JsonSettingsManager as SettingsManager

# Setup translation
import gettext

# Setup translation
import gettext

_ = gettext.gettext


class VideoConverterApp(Adw.Application):
    def __init__(self):
        # Initialize with proper single-instance flags
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN
            | Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )

        # No need to call with parameter in constructor - will be called later
        self.set_resource_base_path("/org/communitybig/converter")
        GLib.set_prgname("comm-video-converter")

        # Connect signals
        self.connect("activate", self.on_activate)
        self.connect("handle-local-options", self.on_handle_local_options)

        # Initialize settings
        self.settings_manager = SettingsManager(APP_ID)
        self.last_accessed_directory = self.settings_manager.load_setting(
            "last-accessed-directory", os.path.expanduser("~")
        )

        # Initialize state variables
        self.conversions_running = 0
        self.progress_widgets = []
        self.previous_page = "conversion"
        self.conversion_queue = deque()
        self.currently_converting = False
        self.auto_convert = False
        self.queue_display_widgets = []

        # Video editing state
        self.trim_start_time = 0
        self.trim_end_time = None
        self.video_duration = 0
        self.crop_x = self.crop_y = self.crop_width = self.crop_height = 0
        self.crop_enabled = False

        # Setup application actions
        self._setup_actions()

    def _setup_actions(self):
        """Setup application actions for the menu"""
        actions = {
            "about": self.on_about_action,
            "help": self.on_help_action,
            "quit": lambda a, p: self.quit(),
        }

        for name, callback in actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def on_activate(self, app):
        # Create window if it doesn't exist
        if not hasattr(self, "window") or self.window is None:
            self._create_window()

        # Present window and process any queued files
        self.window.present()

        if hasattr(self, "queued_files") and self.queued_files:
            for file_path in self.queued_files:
                self.add_to_conversion_queue(file_path)
            self.queued_files = []

    def _create_window(self):
        """Create the main application window and UI components"""
        # Create main window
        self.window = Adw.ApplicationWindow(application=self)
        self.window.set_default_size(900, 620)
        self.window.set_title(_("Comm Video Converter"))

        # Set application icon
        self.set_application_icon()

        # Setup drag and drop
        self._setup_drag_and_drop()

        # Create main content structure
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.header_bar = HeaderBar(self)
        main_box.append(self.header_bar)

        # Create and add stack
        self.stack = Adw.ViewStack()
        self.stack.set_vexpand(True)
        main_box.append(self.stack)
        self.window.set_content(main_box)

        # Create pages
        self._create_pages()

        # Connect stack signals
        self.stack.connect("notify::visible-child", self.on_visible_child_changed)

    def _create_pages(self):
        """Create and add all application pages"""
        # Initialize pages
        self.conversion_page = ConversionPage(self)
        self.video_edit_page = VideoEditPage(self)
        self.settings_page = SettingsPage(self)
        self.progress_page = ProgressPage(self)

        # Add pages to stack
        pages = [
            ("conversion", _("Conversion"), self.conversion_page),
            ("edit", _("Video Edit"), self.video_edit_page),
            ("settings", _("Settings"), self.settings_page),
            ("progress", _("Progress"), self.progress_page),
        ]

        for id, title, page in pages:
            self.stack.add_titled(page.get_page(), id, title)

    def _setup_drag_and_drop(self):
        """Set up drag and drop support for the window"""
        # Handle single files
        drop_target = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop_target.connect("drop", self.on_drop_file)
        self.window.add_controller(drop_target)

        # Handle multiple files
        filelist_drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        filelist_drop_target.connect("drop", self.on_drop_filelist)
        self.window.add_controller(filelist_drop_target)

    # File handling methods
    def is_valid_video_file(self, file_path):
        """Check if file has a valid video extension"""
        if not file_path:
            return False

        valid_extensions = [
            ".mp4",
            ".mkv",
            ".webm",
            ".mov",
            ".avi",
            ".wmv",
            ".mpeg",
            ".m4v",
            ".ts",
            ".flv",
        ]

        ext = os.path.splitext(file_path)[1].lower()
        return ext in valid_extensions

    def on_drop_file(self, drop_target, value, x, y):
        """Handle single dropped file"""
        if isinstance(value, Gio.File):
            file_path = value.get_path()
            if file_path and os.path.exists(file_path):
                if self.is_valid_video_file(file_path):
                    return self.add_file_to_queue(file_path)
                else:
                    print(f"Rejected file with invalid extension: {file_path}")
        return False

    def on_drop_filelist(self, drop_target, value, x, y):
        """Handle multiple dropped files"""
        if isinstance(value, Gdk.FileList):
            files_added = 0
            for file in value.get_files():
                if (
                    file
                    and (file_path := file.get_path())
                    and os.path.exists(file_path)
                ):
                    if self.is_valid_video_file(file_path):
                        if self.add_file_to_queue(file_path):
                            files_added += 1
                    else:
                        print(f"Rejected file with invalid extension: {file_path}")
            return files_added > 0
        return False

    def on_handle_local_options(self, app, options):
        """Handle command line parameters"""
        self.queued_files = []
        return -1  # Continue processing

    # Queue management
    def add_file_to_queue(self, file_path):
        """Add a file to the conversion queue"""
        if file_path and os.path.exists(file_path):
            # Update last accessed directory
            input_dir = os.path.dirname(file_path)
            self.last_accessed_directory = input_dir
            self.settings_manager.save_setting("last-accessed-directory", input_dir)

            # Add to queue if not already present
            if file_path not in self.conversion_queue:
                self.conversion_queue.append(file_path)
                print(
                    f"Added file to queue: {os.path.basename(file_path)}, Queue size: {len(self.conversion_queue)}"
                )

                # Update UI
                if hasattr(self, "conversion_page"):
                    GLib.idle_add(self.conversion_page.update_queue_display)
                return True
            else:
                print(f"File already in queue: {file_path}")
        return False

    def add_to_conversion_queue(self, file_path):
        """Add a file to the conversion queue without starting conversion"""
        return self.add_file_to_queue(file_path)

    def clear_queue(self):
        """Clear the conversion queue"""
        self.conversion_queue.clear()
        if hasattr(self, "conversion_page"):
            self.conversion_page.update_queue_display()
        print("Conversion queue cleared")

    def remove_from_queue(self, file_path):
        """Remove a specific file from the queue"""
        if file_path in self.conversion_queue:
            self.conversion_queue.remove(file_path)
            if hasattr(self, "conversion_page"):
                self.conversion_page.update_queue_display()
            print(f"Removed {os.path.basename(file_path)} from queue")
            return True
        return False

    # Conversion processing
    def start_queue_processing(self):
        """Start processing the conversion queue"""
        if not self.conversion_queue:
            return

        print("Starting queue processing")
        self._was_queue_processing = True
        self.header_bar.set_tabs_sensitive(False)

        # Reset conversion state and start processing
        self.currently_converting = False
        self.show_progress_page()
        GLib.timeout_add(300, self.process_next_in_queue)

    def process_next_in_queue(self):
        """Process the next file in the conversion queue"""
        # Check if we can proceed
        if not self.conversion_queue:
            print("Queue is empty, nothing to process")
            self.currently_converting = False
            return False

        if self.currently_converting:
            print("Already converting, not starting another conversion")
            return False

        # Start processing
        print("Processing next item in queue...")
        self.currently_converting = True

        # Get next file
        file_path = self.conversion_queue[0]
        self.current_processing_file = file_path
        print(f"Processing file: {os.path.basename(file_path)}")

        # Set file and start conversion
        if hasattr(self, "conversion_page"):
            self.conversion_page.set_file(file_path)
            GLib.timeout_add(300, self._force_start_conversion)

        return False  # Don't repeat

    def _force_start_conversion(self):
        """Helper to force start conversion with proper error handling"""
        try:
            print("Forcing conversion to start automatically...")
            if hasattr(self, "conversion_page"):
                self.conversion_page.force_start_conversion()
        except Exception as e:
            print(f"Error starting automatic conversion: {e}")
            self.currently_converting = False
        return False  # Don't repeat

    def conversion_completed(self, success):
        """Called when a conversion is completed"""
        print(f"Conversion completed with success={success}")
        self.currently_converting = False

        # Re-enable convert button
        if hasattr(self, "conversion_page"):
            GLib.idle_add(
                lambda: self.conversion_page.convert_button.set_sensitive(True)
            )

        # Handle completed file
        if (
            self.conversion_queue
            and success
            and hasattr(self, "current_processing_file")
        ):
            try:
                self.conversion_queue.remove(self.current_processing_file)
                print(
                    f"Removed completed file from queue: {os.path.basename(self.current_processing_file)}"
                )
            except ValueError:
                print("File not found in queue, may have been removed already")

            self.current_processing_file = None

            # Update UI
            if hasattr(self, "conversion_page"):
                GLib.idle_add(self.conversion_page.update_queue_display)

        # Process next file or finish
        if self.conversion_queue:
            print(
                f"Queue has {len(self.conversion_queue)} file(s) remaining, processing next file"
            )
            GLib.timeout_add(500, self.process_next_in_queue)
        else:
            print("Queue is now empty")
            GLib.idle_add(self.header_bar.set_tabs_sensitive, True)

            # Show completion notification if we were processing a queue
            if hasattr(self, "_was_queue_processing") and self._was_queue_processing:
                GLib.idle_add(
                    lambda: self.show_info_dialog(
                        _("Queue Processing Complete"),
                        _("All files in the queue have been processed."),
                    )
                )
                self._was_queue_processing = False
                GLib.idle_add(self.return_to_previous_page)

    # UI Navigation
    def activate_tab(self, tab_name):
        """Switch to the specified tab and update button styling"""
        # Special handling for edit tab - need to load a video
        if tab_name == "edit" and self.conversion_page:
            file_path = self.conversion_page.get_selected_file_path()
            if not file_path:
                self.show_error_dialog(_("Please select a video file first"))
                return

            if not self.video_edit_page.set_video(file_path):
                self.show_error_dialog(_("Could not load the selected video file"))
                return

        # Remember previous page unless switching to progress
        if tab_name != "progress" and self.stack.get_visible_child_name() != "progress":
            self.previous_page = tab_name

        # Update UI
        self.stack.set_visible_child_name(tab_name)
        self.header_bar.activate_tab(tab_name)

    def show_progress_page(self):
        """Show progress page and disable tab navigation"""
        self.header_bar.set_tabs_sensitive(False)
        self.stack.set_visible_child_name("progress")

    def return_to_previous_page(self):
        """Return to the previous page after conversion completes"""
        self.header_bar.set_tabs_sensitive(True)
        self.stack.set_visible_child_name(self.previous_page)
        self.header_bar.activate_tab(self.previous_page)

    def on_visible_child_changed(self, stack, param):
        """Update button styling when the visible stack child changes"""
        visible_name = stack.get_visible_child_name()
        self.header_bar.activate_tab(visible_name)

    # Menu actions
    def on_about_action(self, action, param):
        """Show about dialog"""
        from constants import APP_NAME, APP_VERSION, APP_DEVELOPERS

        about = Adw.AboutWindow(
            transient_for=self.window,
            application_name=APP_NAME,
            application_icon="comm-video-converter",
            version=APP_VERSION,
            developers=APP_DEVELOPERS,
            license_type=Gtk.License.GPL_3_0,
            website="https://communitybig.org",
        )
        about.present()

    def on_help_action(self, action, param):
        """Show help information"""
        self.show_info_dialog(
            _("Help"),
            _(
                "This application helps you convert video files between different formats.\n\n"
                "• Use the Conversion tab to select and convert video files\n"
                "• Use the Video Edit tab to trim, crop, and adjust video properties\n"
                "• Access settings through the gear icon\n\n"
                "For more help, visit the website: communitybig.org"
            ),
        )

    # Application utilities
    def set_application_icon(self, icon_name=None):
        """Sets the application icon - improved for Wayland compatibility"""
        try:
            # If icon name is provided, use it
            if icon_name:
                # Set on the application itself using Gio.Application method
                Gio.Application.set_application_icon(self, icon_name)

            # Always set for window if it exists
            if hasattr(self, "window"):
                self.window.set_icon_name("comm-video-converter")

            # Ensure program name is correctly set
            GLib.set_prgname("comm-video-converter")

            print("Application icon set successfully")
        except Exception as e:
            print(f"Error setting application icon: {e}")
            try:
                # Fallback to generic video icon
                if hasattr(self, "window"):
                    self.window.set_icon_name("video-x-generic")
                print("Using fallback icon")
            except Exception as e2:
                print(f"Could not set fallback icon: {e2}")

    # Video editing parameters
    def set_trim_times(self, start_time, end_time, duration):
        """Set the trim start and end times for video cutting"""
        self.trim_start_time = start_time
        self.trim_end_time = end_time
        self.video_duration = duration

    def get_trim_times(self):
        """Get the current trim start and end times"""
        return self.trim_start_time, self.trim_end_time, self.video_duration

    def set_crop_params(self, x, y, width, height, enabled=True):
        """Set the crop parameters for video cropping"""
        self.crop_x, self.crop_y = x, y
        self.crop_width, self.crop_height = width, height
        self.crop_enabled = enabled

    def get_crop_params(self):
        """Get the current crop parameters"""
        return {
            "x": self.crop_x,
            "y": self.crop_y,
            "width": self.crop_width,
            "height": self.crop_height,
            "enabled": self.crop_enabled,
        }

    def reset_crop_params(self):
        """Reset crop parameters"""
        self.crop_x = self.crop_y = self.crop_width = self.crop_height = 0
        self.crop_enabled = False

    # Dialog helpers
    def show_error_dialog(self, message):
        """Shows an error dialog"""
        dialog = Gtk.AlertDialog()
        dialog.set_message(_("Error"))
        dialog.set_detail(message)
        dialog.show(self.window)

    def show_info_dialog(self, title, message):
        """Shows an information dialog"""
        dialog = Gtk.AlertDialog()
        dialog.set_message(title)
        dialog.set_detail(message)
        dialog.show(self.window)

    def show_question_dialog(self, title, message, callback):
        """Shows a question dialog"""
        dialog = Gtk.AlertDialog()
        dialog.set_message(title)
        dialog.set_detail(message)
        dialog.set_buttons(["Cancel", "Continue"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)

        dialog.connect("response", lambda d, r: callback(r == 1))
        dialog.show(self.window)

    def show_file_details(self, file_path):
        """Preview a file in the editor"""
        if self.video_edit_page:
            try:
                if self.video_edit_page.set_video(file_path):
                    self.activate_tab("edit")
                else:
                    self.show_error_dialog(_("Could not preview this video file"))
            except Exception as e:
                print(f"Error previewing file: {e}")
                self.show_error_dialog(_("Error previewing file: {0}").format(str(e)))

    # GIO Application overrides
    def do_open(self, files, n_files, hint):
        """Handle files opened via file association or from another instance"""
        # Ensure window exists
        if not hasattr(self, "window") or self.window is None:
            self.activate()

        # Add files to queue
        files_added = 0
        for file in files:
            file_path = file.get_path()
            if (
                file_path
                and os.path.exists(file_path)
                and self.is_valid_video_file(file_path)
            ):
                if self.add_file_to_queue(file_path):
                    files_added += 1

        # Switch to conversion tab if files were added
        if files_added > 0:
            GLib.idle_add(self._activate_conversion_tab)

    def _activate_conversion_tab(self):
        """Activate conversion tab safely from idle callback"""
        if hasattr(self, "stack") and hasattr(self, "header_bar"):
            self.activate_tab("conversion")
        return False

    def do_command_line(self, command_line):
        """Handle command line arguments"""
        args = command_line.get_arguments()

        # Process file arguments
        if len(args) > 1:
            files = [
                Gio.File.new_for_path(arg) for arg in args[1:] if os.path.isfile(arg)
            ]
            if files:
                self.do_open(files, len(files), "")

        # Show window
        self.activate()
        return 0

    # File selection methods
    def select_files_for_queue(self):
        """Open file chooser to select video files for the queue"""
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Select Video Files"))
        dialog.set_modal(True)

        # Set initial folder to last accessed directory
        if hasattr(self, "last_accessed_directory") and self.last_accessed_directory:
            try:
                initial_folder = Gio.File.new_for_path(self.last_accessed_directory)
                dialog.set_initial_folder(initial_folder)
            except Exception as e:
                print(f"Error setting initial folder: {e}")

        # Create filter for video files
        filter = Gtk.FileFilter()
        filter.set_name(_("Video Files"))
        for mime_type in VIDEO_FILE_MIME_TYPES:
            filter.add_mime_type(mime_type)

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter)
        dialog.set_filters(filters)

        # Allow multiple file selection - corrected method name
        dialog.open_multiple(self.window, None, self._on_files_selected)

    def _on_files_selected(self, dialog, result):
        """Handle selected files from file chooser dialog"""
        try:
            # Use open_multiple_finish instead of select_multiple_finish
            files = dialog.open_multiple_finish(result)
            if files:
                files_added = 0
                for file in files:
                    file_path = file.get_path()
                    if (
                        file_path
                        and os.path.exists(file_path)
                        and self.is_valid_video_file(file_path)
                    ):
                        if self.add_file_to_queue(file_path):
                            files_added += 1

                # Update last accessed directory if files were selected
                if files_added > 0:
                    first_file = files[0].get_path()
                    if first_file:
                        self.last_accessed_directory = os.path.dirname(first_file)
                        self.settings_manager.save_setting(
                            "last-accessed-directory", self.last_accessed_directory
                        )
        except Exception as e:
            print(f"Error selecting files: {e}")


def main():
    # Set up internationalization
    locale_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "locale")
    gettext.bindtextdomain("comm-video-converter", locale_dir)
    gettext.textdomain("comm-video-converter")

    # Create and run application
    app = VideoConverterApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    main()
