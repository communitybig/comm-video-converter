#!/usr/bin/env python3
"""
Main entry point for Comm Video Converter application.
"""
import os
import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib

# Import local modules
from constants import APP_ID, SCHEMA_ID
from ui.widgets.header_bar import HeaderBar
from ui.pages.conversion_page import ConversionPage
from ui.pages.video_edit_page import VideoEditPage
from ui.dialogs.settings_dialog import SettingsDialog
from ui.dialogs.progress_dialog import ProgressDialog
from core.json_settings_manager import JsonSettingsManager as SettingsManager
from utils.conversion import run_with_progress_dialog

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
        super().__init__(application_id=APP_ID, 
                        flags=Gio.ApplicationFlags.FLAGS_NONE)
        
        # Set resource base path
        self.set_resource_base_path("/org/communitybig/converter")
        
        # Set program name to match StartupWMClass in desktop file
        GLib.set_prgname("comm-video-converter")
        
        # Connect the activation signal
        self.connect("activate", self.on_activate)
        
        # Initialize settings manager
        self.settings_manager = SettingsManager(APP_ID)
        
        # Set the last accessed directory
        self.last_accessed_directory = self.settings_manager.load_setting(
            "last-accessed-directory", os.path.expanduser("~")
        )
        
        # State variables
        self.conversions_running = 0
        
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
        
        # Add pages to stack
        self.stack.add_titled(self.conversion_page.get_page(), "conversion", _("Conversion"))
        self.stack.add_titled(self.video_edit_page.get_page(), "edit", _("Video Edit"))
        
        # Connect to stack's notify::visible-child signal
        self.stack.connect("notify::visible-child", self.on_visible_child_changed)
        
        # Show window
        self.window.present()
    
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
        
        # Update stack
        self.stack.set_visible_child_name(tab_name)
        
        # Update button styling in header bar
        self.header_bar.activate_tab(tab_name)
    
    def on_visible_child_changed(self, stack, param):
        """Update button styling when the visible stack child changes"""
        visible_name = stack.get_visible_child_name()
        self.header_bar.activate_tab(visible_name)
    
    def show_settings_dialog(self):
        """Show the settings dialog"""
        settings_dialog = SettingsDialog(self)
        settings_dialog.present()
    
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
            website="https://communitybig.org"
        )
        about.present()
    
    def on_help_action(self, action, param):
        """Show help information"""
        self.show_info_dialog(
            _("Help"),
            _("This application helps you convert video files between different formats.\n\n"
              "• Use the Conversion tab to select and convert video files\n"
              "• Use the Video Edit tab to trim, crop, and adjust video properties\n"
              "• Access settings through the gear icon\n\n"
              "For more help, visit the website: communitybig.org")
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
            'x': self.crop_x,
            'y': self.crop_y,
            'width': self.crop_width,
            'height': self.crop_height,
            'enabled': self.crop_enabled
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
        dialog.set_cancel_button(0)   # Cancel button is cancel action
        
        def on_response(dialog, response):
            callback(response == 1)  # True if "Continue" was clicked
        
        dialog.connect("response", on_response)
        dialog.show(self.window)

def main():
    app = VideoConverterApp()
    return app.run(sys.argv)

if __name__ == "__main__":
    main()