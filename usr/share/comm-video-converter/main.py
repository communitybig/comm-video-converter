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
from constants import APP_ID
from ui.widgets.header_bar import HeaderBar
from ui.pages.conversion_page import ConversionPage
from ui.pages.video_edit_page import VideoEditPage
from ui.pages.settings_page import SettingsPage
from ui.pages.progress_page import ProgressPage  # Add import for ProgressPage
from core.json_settings_manager import JsonSettingsManager as SettingsManager

# Setup translation
import gettext

lang_translations = gettext.translation(
    "comm-video-converter", localedir="/usr/share/locale", fallback=True
)
lang_translations.install()
# define _ shortcut for translations
_ = lang_translations.gettext


class VideoConverterApp(Adw.Application):
    def __init__(self):
        # Use the application_id from constants
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)

        # Set resource base path
        self.set_resource_base_path("/org/communitybig/converter")

        # Set program name to match StartupWMClass in desktop file
        GLib.set_prgname("comm-video-converter")

        # Connect the activation signal
        self.connect("activate", self.on_activate)

        # Setup command line handling
        self.connect("handle-local-options", self.on_handle_local_options)

        # Initialize settings manager
        self.settings_manager = SettingsManager(APP_ID)

        # Set the last accessed directory
        self.last_accessed_directory = self.settings_manager.load_setting(
            "last-accessed-directory", os.path.expanduser("~")
        )

        # State variables
        self.conversions_running = 0
        self.progress_widgets = []  # Add this to track active conversion widgets
        # Track the previous page to return after conversion completes
        self.previous_page = "conversion"

        # Conversion queue
        self.conversion_queue = deque()
        self.currently_converting = False
        self.auto_convert = False  # Disable auto-conversion by default - only convert when button is clicked
        self.queue_display_widgets = []  # Track widgets for queue display

        # Video trimming state
        self.trim_start_time = 0
        self.trim_end_time = None
        self.video_duration = 0

        # Video cropping state
        self.crop_x = 0
        self.crop_y = 0
        self.crop_width = 0
        self.crop_height = 0
        self.crop_enabled = False

        # Setup application actions
        self._setup_actions()

    def _setup_actions(self):
        """Setup application actions for the menu"""
        # About action
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self.on_about_action)
        self.add_action(about_action)

        # Help action
        help_action = Gio.SimpleAction.new("help", None)
        help_action.connect("activate", self.on_help_action)
        self.add_action(help_action)

        # Quit action
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda action, param: self.quit())
        self.add_action(quit_action)

    def on_activate(self, app):
        # Create main window
        self.window = Adw.ApplicationWindow(application=self)
        self.window.set_default_size(900, 620)
        self.window.set_title(_("Comm Video Converter"))

        # Configure application icon
        self.set_application_icon()

        # Set up drag and drop support
        self._setup_drag_and_drop()

        # Create main content
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Create custom header bar
        self.header_bar = HeaderBar(self)
        main_box.append(self.header_bar)

        # Create stack for pages
        self.stack = Adw.ViewStack()
        self.stack.set_vexpand(True)
        main_box.append(self.stack)

        self.window.set_content(main_box)

        # Create pages
        self.conversion_page = ConversionPage(self)
        self.video_edit_page = VideoEditPage(self)
        self.settings_page = SettingsPage(self)
        self.progress_page = ProgressPage(self)

        # Add pages to stack
        self.stack.add_titled(
            self.conversion_page.get_page(), "conversion", _("Conversion")
        )
        self.stack.add_titled(self.video_edit_page.get_page(), "edit", _("Video Edit"))
        self.stack.add_titled(self.settings_page.get_page(), "settings", _("Settings"))
        self.stack.add_titled(
            self.progress_page.get_page(), "progress", _("Progress")
        )  # Add progress page to stack

        # Connect to stack's notify::visible-child signal
        self.stack.connect("notify::visible-child", self.on_visible_child_changed)

        # Show window
        self.window.present()

        # Process any files passed on command line
        if self.queued_files:
            for file_path in self.queued_files:
                self.add_to_conversion_queue(file_path)
            self.queued_files = []

    def _setup_drag_and_drop(self):
        """Set up drag and drop support for the window"""
        # Create a unified drop target that handles both single files and file lists
        drop_target = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop_target.connect("drop", self.on_drop_file)
        self.window.add_controller(drop_target)

        # Add support for file lists (multiple files)
        filelist_drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        filelist_drop_target.connect("drop", self.on_drop_filelist)
        self.window.add_controller(filelist_drop_target)

    def is_valid_video_file(self, file_path):
        """Check if the file has a valid video extension"""
        if not file_path:
            return False

        # List of supported video extensions
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

        # Check if the file has a valid extension (case insensitive)
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
            # Process all files in the list
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

        # Use sys.argv to get command-line arguments instead of options.get_arguments()
        args = sys.argv

        # Skip first argument (program name)
        if len(args) > 1:
            for arg in args[1:]:
                if os.path.isfile(arg):
                    self.queued_files.append(arg)

        return -1  # Continue processing

    def add_file_to_queue(self, file_path):
        """Add a file to the conversion queue"""
        if file_path and os.path.exists(file_path):
            # Update last accessed directory
            input_dir = os.path.dirname(file_path)
            self.last_accessed_directory = input_dir
            self.settings_manager.save_setting("last-accessed-directory", input_dir)

            # Add file to queue
            if file_path not in self.conversion_queue:
                self.conversion_queue.append(file_path)
                queue_len = len(self.conversion_queue)
                print(
                    f"Added file to queue: {os.path.basename(file_path)}, Queue size: {queue_len}"
                )

                # If conversion page is available, update UI
                if hasattr(self, "conversion_page"):
                    # Update the queue display
                    self.conversion_page.update_queue_display()

                return True
            else:
                print(f"File already in queue: {file_path}")
                return False
        return False

    def add_to_conversion_queue(self, file_path):
        """Add a file to the conversion queue without starting conversion"""
        return self.add_file_to_queue(file_path)

    def select_files_for_queue(self):
        """Open a file chooser to select multiple files to add to the queue"""
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Select Video Files"))

        # Set current folder to last accessed directory
        if self.last_accessed_directory and os.path.exists(
            self.last_accessed_directory
        ):
            dialog.set_initial_folder(
                Gio.File.new_for_path(self.last_accessed_directory)
            )

        # Simplify file filters for more reliable behavior
        filter_list = Gio.ListStore.new(Gtk.FileFilter)

        # Create a filter for common video file extensions only - no MIME types
        video_filter = Gtk.FileFilter()
        video_filter.set_name(_("Video Files"))

        # Just add the most common video extensions
        for ext in [
            "mp4",
            "mkv",
            "webm",
            "mov",
            "avi",
            "wmv",
            "mpeg",
            "m4v",
            "ts",
            "flv",
        ]:
            # Add both lowercase and uppercase versions
            video_filter.add_pattern(f"*.{ext}")
            video_filter.add_pattern(f"*.{ext.upper()}")

        filter_list.append(video_filter)

        # Add an "All Files" filter
        filter_all = Gtk.FileFilter()
        filter_all.set_name(_("All Files"))
        filter_all.add_pattern("*")
        filter_list.append(filter_all)

        dialog.set_filters(filter_list)
        dialog.set_default_filter(video_filter)

        # Configure for multiple selection
        dialog.open_multiple(self.window, None, self._on_files_selected_for_queue)

    def _on_files_selected_for_queue(self, dialog, result):
        """Handle selected files from the file chooser dialog"""
        try:
            files_list = dialog.open_multiple_finish(result)
            if files_list:
                # Get files list from Gio.ListModel
                files = []
                # Convert to a standard Python list to avoid GTK4 iterator issues
                for i in range(files_list.get_n_items()):
                    file_obj = files_list.get_item(i)
                    if file_obj:
                        files.append(file_obj)

                # Now process the files from our Python list
                for file in files:
                    file_path = file.get_path()
                    if file_path and os.path.exists(file_path):
                        # Add all files to queue
                        self.add_file_to_queue(file_path)

        except Exception as e:
            print(f"Error selecting files: {e}")
            import traceback

            traceback.print_exc()  # Print full traceback for better debugging
            self.show_error_dialog(_("Error selecting files: {0}").format(str(e)))

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

    def start_queue_processing(self):
        """Start processing the conversion queue"""
        if self.conversion_queue:
            print("Starting queue processing")
            # Set flag to indicate we're processing a queue (for proper dialog handling)
            self._was_queue_processing = True

            # Ensure the header bar buttons remain disabled during queue processing
            self.header_bar.set_tabs_sensitive(False)

            # Set currently_converting to False first to allow processing to start
            was_converting = self.currently_converting
            self.currently_converting = False

            # Switch to progress tab before starting queue processing
            self.show_progress_page()

            # Start queue processing with a slight delay to ensure UI is ready
            GLib.timeout_add(300, self.process_next_in_queue)

            if was_converting:
                print(
                    "Note: Conversion was already in progress but we forced a restart"
                )

    def process_next_in_queue(self):
        """Process the next file in the conversion queue"""
        # Bail out early if queue is empty to avoid errors
        if not self.conversion_queue:
            print("Queue is empty, nothing to process")
            self.currently_converting = False
            return False  # Stop any timeout callbacks

        # If already converting, don't start another one
        if self.currently_converting:
            print("Already converting, not starting another conversion")
            return False  # Stop any timeout callbacks

        print("Processing next item in queue...")
        self.currently_converting = True

        # Get the next file to process
        file_path = self.conversion_queue[0]
        # Save reference to the file being processed
        self.current_processing_file = file_path

        print(f"Processing file: {os.path.basename(file_path)}")

        # Update conversion page if available and start conversion
        if hasattr(self, "conversion_page"):
            # First set the file to update the UI
            self.conversion_page.set_file(file_path)

            # Start conversion with a small delay
            GLib.timeout_add(300, self._force_start_conversion)

        return False  # Don't repeat

    def _force_start_conversion(self):
        """Helper to force start conversion with proper error handling"""
        try:
            print("Forcing conversion to start automatically...")
            if hasattr(self, "conversion_page"):
                self.conversion_page.force_start_conversion()
            return False  # Don't repeat
        except Exception as e:
            print(f"Error starting automatic conversion: {e}")
            self.currently_converting = False  # Reset flag to allow retry
            return False  # Don't repeat

    def conversion_completed(self, success):
        """Called when a conversion is completed"""
        print(f"Conversion completed with success={success}")
        self.currently_converting = False

        # Re-enable convert button on the conversion page
        if hasattr(self, "conversion_page"):
            GLib.idle_add(
                lambda: self.conversion_page.convert_button.set_sensitive(True)
            )

        # If there are files in queue and conversion was successful, remove the first item (current)
        if (
            self.conversion_queue
            and success
            and hasattr(self, "current_processing_file")
        ):
            # Remove the specific file that was processed
            try:
                self.conversion_queue.remove(self.current_processing_file)
                print(
                    f"Removed completed file from queue: {os.path.basename(self.current_processing_file)}"
                )
            except ValueError:
                # The file might have been removed already or wasn't in the queue
                print("File not found in queue, may have been removed already")

            # Clear the current processing file reference
            self.current_processing_file = None

            # Update the queue display
            if hasattr(self, "conversion_page"):
                GLib.idle_add(self.conversion_page.update_queue_display)

        # Process next file in queue if any
        if self.conversion_queue:
            remaining = len(self.conversion_queue)
            print(f"Queue has {remaining} file(s) remaining, processing next file")
            GLib.timeout_add(500, self.process_next_in_queue)
        else:
            print("Queue is now empty")

            # Queue is complete, re-enable tab navigation
            GLib.idle_add(self.header_bar.set_tabs_sensitive, True)

            # Only show notification that all conversions are complete if we were processing a queue
            if hasattr(self, "_was_queue_processing") and self._was_queue_processing:
                GLib.idle_add(
                    lambda: self.show_info_dialog(
                        _("Queue Processing Complete"),
                        _("All files in the queue have been processed."),
                    )
                )
                # Reset the flag
                self._was_queue_processing = False

                # Return to the conversion page after all conversions are done
                GLib.idle_add(self.return_to_previous_page)

    def activate_tab(self, tab_name):
        """Switch to the specified tab and update button styling"""
        # For edit tab, check if we need to load a video first
        if tab_name == "edit" and self.conversion_page:
            # Get the selected file path from conversion page
            file_path = self.conversion_page.get_selected_file_path()
            if not file_path:
                self.show_error_dialog(_("Please select a video file first"))
                return

            # Set the video in the edit page
            if not self.video_edit_page.set_video(file_path):
                self.show_error_dialog(_("Could not load the selected video file"))
                return

        # Special handling for progress tab - remember previous page unless already on progress
        if tab_name != "progress" and self.stack.get_visible_child_name() != "progress":
            self.previous_page = tab_name

        # Update stack
        self.stack.set_visible_child_name(tab_name)

        # Update button styling in header bar
        self.header_bar.activate_tab(tab_name)

    def show_progress_page(self):
        """Show progress page and disable tab navigation"""
        # Disable tab buttons while conversion runs
        self.header_bar.set_tabs_sensitive(False)
        # Show the progress page
        self.stack.set_visible_child_name("progress")

    def return_to_previous_page(self):
        """Return to the previous page after conversion completes"""
        # Re-enable tab buttons
        self.header_bar.set_tabs_sensitive(True)
        # Return to previous page
        self.stack.set_visible_child_name(self.previous_page)
        self.header_bar.activate_tab(self.previous_page)

    def on_visible_child_changed(self, stack, param):
        """Update button styling when the visible stack child changes"""
        visible_name = stack.get_visible_child_name()
        self.header_bar.activate_tab(visible_name)

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

    # Other methods from the original application...
    def set_application_icon(self):
        """Sets the application icon, ensuring proper integration with GNOME Shell"""
        try:
            self.window.set_icon_name("comm-video-converter")
            GLib.set_prgname("comm-video-converter")
            print("Application icon configured successfully.")
        except Exception as e:
            print(f"Error setting application icon: {e}")
            try:
                self.window.set_icon_name("video-x-generic")
            except:
                print("Could not set fallback icon.")

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
        self.crop_x = x
        self.crop_y = y
        self.crop_width = width
        self.crop_height = height
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
        self.crop_x = 0
        self.crop_y = 0
        self.crop_width = 0
        self.crop_height = 0
        self.crop_enabled = False

    def show_error_dialog(self, message):
        """Shows an error dialog with the given message"""
        dialog = Gtk.AlertDialog()
        dialog.set_message(_("Error"))
        dialog.set_detail(message)
        dialog.show(self.window)

    def show_info_dialog(self, title, message):
        """Shows an information dialog with title and message"""
        dialog = Gtk.AlertDialog()
        dialog.set_message(title)
        dialog.set_detail(message)
        dialog.show(self.window)

    def show_question_dialog(self, title, message, callback):
        """Shows a question dialog with title and message"""
        dialog = Gtk.AlertDialog()
        dialog.set_message(title)
        dialog.set_detail(message)
        dialog.set_buttons(["Cancel", "Continue"])
        dialog.set_default_button(0)  # Cancel is default
        dialog.set_cancel_button(0)  # Cancel button is cancel action

        def on_response(dialog, response):
            callback(response == 1)  # True if "Continue" was clicked

        dialog.connect("response", on_response)
        dialog.show(self.window)

    def show_file_details(self, file_path):
        """Show details or preview of a file from queue"""
        # Switch to video edit tab with this file
        if self.video_edit_page:
            try:
                # Attempt to load the file in the video edit page
                if self.video_edit_page.set_video(file_path):
                    # Switch to the edit tab
                    self.activate_tab("edit")
                else:
                    self.show_error_dialog(_("Could not preview this video file"))
            except Exception as e:
                print(f"Error previewing file: {e}")
                self.show_error_dialog(_("Error previewing file: {0}").format(str(e)))


def main():
    app = VideoConverterApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    main()
