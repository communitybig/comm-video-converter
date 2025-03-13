import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib

# Setup translation
import gettext
_ = gettext.gettext

class HeaderBar(Gtk.Box):
    """
    Custom header bar with tabs and buttons for settings and menu.
    """
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.app = app
        
        # Create the header bar
        self.header_bar = Adw.HeaderBar()
        self.append(self.header_bar)
        
        # Create tab buttons container
        self.tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.tab_box.add_css_class("linked")
        self.tab_box.set_halign(Gtk.Align.CENTER)
        
        # Create tab buttons
        self.conversion_button = Gtk.Button(label=_("Conversion"))
        self.conversion_button.connect("clicked", self._on_tab_clicked, "conversion")
        self.conversion_button.add_css_class("suggested-action")
        self.tab_box.append(self.conversion_button)
        
        self.preview_button = Gtk.Button(label=_("Video Preview"))
        self.preview_button.connect("clicked", self._on_tab_clicked, "preview")
        self.tab_box.append(self.preview_button)
        
        # Store buttons for easy access
        self.tab_buttons = {
            "conversion": self.conversion_button,
            "preview": self.preview_button
        }
        
        # Set title widget for header bar
        self.header_bar.set_title_widget(self.tab_box)
        
        # Add settings button (gear icon)
        self.settings_button = Gtk.Button()
        self.settings_button.set_icon_name("emblem-system-symbolic")
        self.settings_button.set_tooltip_text(_("Settings"))
        self.settings_button.add_css_class("flat")
        self.settings_button.connect("clicked", self._on_settings_clicked)
        self.header_bar.pack_end(self.settings_button)
        
        # Add menu button (three dots)
        self.menu_button = Gtk.MenuButton()
        self.menu_button.set_icon_name("open-menu-symbolic")
        self.menu_button.set_tooltip_text(_("Menu"))
        
        # Create menu model
        menu = Gio.Menu.new()
        menu.append(_("About"), "app.about")
        menu.append(_("Help"), "app.help")
        menu.append(_("Quit"), "app.quit")
        
        self.menu_button.set_menu_model(menu)
        self.header_bar.pack_end(self.menu_button)
    
    def _on_tab_clicked(self, button, tab_name):
        """Handle tab button clicks"""
        if hasattr(self.app, "activate_tab"):
            self.app.activate_tab(tab_name)
    
    def _on_settings_clicked(self, button):
        """Show settings dialog"""
        if hasattr(self.app, "show_settings_dialog"):
            self.app.show_settings_dialog()
    
    def activate_tab(self, tab_name):
        """Update button styling to reflect current tab"""
        for name, button in self.tab_buttons.items():
            if name == tab_name:
                button.add_css_class("suggested-action")
            else:
                button.remove_css_class("suggested-action")
