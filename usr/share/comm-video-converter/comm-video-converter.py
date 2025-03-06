#!/usr/bin/env python3
import os
import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, Gdk

# Import local modules
from progress_dialog import ProgressDialog
from settings_manager import SettingsManager
from single_file_page import SingleFilePage
from batch_page import BatchPage
from settings_page import SettingsPage
from conversion import run_with_progress_dialog

# Setup translation
import gettext
lang_translations = gettext.translation(
    "comm-video-converter", localedir="/usr/share/locale", fallback=True
)
lang_translations.install()
# define _ shortcut for translations
_ = lang_translations.gettext

# Define GSettings schema ID
SCHEMA_ID = "org.communitybig.converter"

class VideoConverterApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.communitybig.converter", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect("activate", self.on_activate)
        
        # Initialize settings manager
        self.settings_manager = SettingsManager(SCHEMA_ID)
        
        # Set the last accessed directory
        self.last_accessed_directory = self.settings_manager.load_setting("last-accessed-directory", os.path.expanduser("~"))
        
        # State variables
        self.conversions_running = 0
    
    def on_activate(self, app):
        # Create main window
        self.window = Adw.ApplicationWindow(application=self)
        self.window.set_default_size(900, 620)
        self.window.set_title(_("Comm Video Converter"))
        
        # Configure application icon
        self.set_application_icon()
        
        # Create main content
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Create stack
        self.stack = Adw.ViewStack()
        self.stack.set_vexpand(True)
        
        # Add HeaderBar
        header_bar = Adw.HeaderBar()
        
        # Create a container for the toggle buttons in the header
        toggle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        toggle_box.add_css_class("linked")
        toggle_box.set_halign(Gtk.Align.CENTER)
        
        # Create the toggle buttons
        self.single_button = Gtk.Button(label=_("Single File"))
        self.single_button.connect("clicked", lambda b: self.activate_tab("single"))
        self.single_button.add_css_class("suggested-action")  # Start with this tab active
        toggle_box.append(self.single_button)
        
        self.batch_button = Gtk.Button(label=_("Multiple Files"))
        self.batch_button.connect("clicked", lambda b: self.activate_tab("batch"))
        toggle_box.append(self.batch_button)
        
        self.settings_button = Gtk.Button(label=_("Settings"))
        self.settings_button.connect("clicked", lambda b: self.activate_tab("settings"))
        toggle_box.append(self.settings_button)
        
        # Store buttons in a dictionary for easy access
        self.tab_buttons = {
            "single": self.single_button,
            "batch": self.batch_button,
            "settings": self.settings_button
        }
        
        # Set title widget for header bar
        header_bar.set_title_widget(toggle_box)
        
        main_box.append(header_bar)
        main_box.append(self.stack)
        
        self.window.set_content(main_box)
        
        # Create pages and assign their parent app reference
        self.single_page = SingleFilePage(self)
        self.batch_page = BatchPage(self)
        self.settings_page = SettingsPage(self)
        
        # Add pages to stack
        self.stack.add_titled(self.single_page.get_page(), "single", _("Single File"))
        self.stack.add_titled(self.batch_page.get_page(), "batch", _("Multiple Files"))
        self.stack.add_titled(self.settings_page.get_page(), "settings", _("Settings"))
        
        # Connect to stack's notify::visible-child signal to update button states
        self.stack.connect("notify::visible-child", self.on_visible_child_changed)
        
        # Show window
        self.window.present()
    
    def activate_tab(self, tab_name):
        """Switch to the specified tab and update button styling"""
        # Update stack
        self.stack.set_visible_child_name(tab_name)
        
        # Update button styling
        for name, button in self.tab_buttons.items():
            if name == tab_name:
                button.add_css_class("suggested-action")
            else:
                button.remove_css_class("suggested-action")
    
    def on_visible_child_changed(self, stack, param):
        """Update button styling when the visible stack child changes"""
        visible_name = stack.get_visible_child_name()
        self.activate_tab(visible_name)
    
    def set_application_icon(self):
        """Sets the application icon, checking multiple possible paths"""
        icon_paths = [
            # Paths to look for the icon
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "comm-video-converter.svg"),
            os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps/comm-video-converter.svg"),
            "/usr/share/icons/hicolor/scalable/apps/comm-video-converter.svg"
        ]
        
        # In GTK4, icons are typically handled by the window, not the application
        for icon_path in icon_paths:
            if (os.path.exists(icon_path)):
                self.window.set_icon_name("comm-video-converter")
                return
        
        # If SVG file not found, use system icon
        self.window.set_icon_name("video-x-generic")
    
    def show_error_dialog(self, message):
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
    
    def show_question_dialog(self, title, message):
        """Shows a question dialog with title and message, returns True if user confirms"""
        dialog = Gtk.AlertDialog()
        dialog.set_message(title)
        dialog.set_detail(message)
        dialog.set_buttons(["Cancel", "Continue"])
        dialog.set_default_button(0)  # Cancel is default
        dialog.set_cancel_button(0)   # Cancel button is cancel action
        
        result = [False]  # Use list to be modified from callback
        
        def on_response(dialog, response):
            result[0] = (response == 1)  # True if "Continue" was clicked
        
        dialog.connect("response", on_response)
        dialog.show(self.window)
        
        # Wait for user response
        while Gtk.events_pending():
            Gtk.main_iteration()
        
        return result[0]

def main():
    app = VideoConverterApp()
    return app.run(sys.argv)

if __name__ == "__main__":
    main()