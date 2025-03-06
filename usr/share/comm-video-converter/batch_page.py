import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, Pango

from constants import MKV_MP4_ALL_PATH
from conversion import run_with_progress_dialog

# Setup translation
import gettext
lang_translations = gettext.translation(
    "comm-video-converter", localedir="/usr/share/locale", fallback=True
)
lang_translations.install()
# define _ shortcut for translations
_ = lang_translations.gettext

class BatchPage:
    def __init__(self, app):
        self.app = app
        self.page = self._create_page()
    
    def get_page(self):
        return self.page
    
    def _create_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Add ScrolledWindow to enable scrolling when window is small
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_hexpand(True)
        scrolled_window.set_vexpand(True)
        page.append(scrolled_window)
        
        # Container for scrollable content - center vertically
        scrollable_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scrollable_content.set_valign(Gtk.Align.CENTER)  # Center content vertically
        scrollable_content.set_vexpand(True)
        scrolled_window.set_child(scrollable_content)
        
        # Use Adw.Clamp to constrain content width nicely
        clamp = Adw.Clamp()
        clamp.set_maximum_size(800)
        clamp.set_tightening_threshold(600)
        scrollable_content.append(clamp)
        
        # Main content box inside the clamp
        main_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_content.set_spacing(24)  # Larger spacing between groups
        main_content.set_margin_start(12)
        main_content.set_margin_end(12)
        main_content.set_margin_top(24)
        main_content.set_margin_bottom(24)
        clamp.set_child(main_content)
        
        # Batch settings using Adw.PreferencesGroup
        settings_group = Adw.PreferencesGroup()
        
        # Add help button to the header with a larger icon but same button size
        help_button = Gtk.Button()
        icon = Gtk.Image.new_from_icon_name("help-about-symbolic")
        icon.set_pixel_size(22)
        icon.add_css_class("accent")
        help_button.set_child(icon)
        help_button.add_css_class("flat")
        help_button.add_css_class("circular")
        help_button.connect("clicked", self.on_help_clicked)
        settings_group.set_header_suffix(help_button)
        
        # Search directory
        dir_row = Adw.ActionRow(title=_("Search directory"))
        dir_row.set_subtitle(_("Select the folder containing MKV files"))
        
        # Create a styled box for directory display
        dir_info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        self.search_dir_label = Gtk.Label(label=_("No directory selected"))
        self.search_dir_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.search_dir_label.set_hexpand(True)
        self.search_dir_label.set_halign(Gtk.Align.START)
        # Add a CSS class to improve styling
        self.search_dir_label.add_css_class("caption")
        
        dir_info_box.append(self.search_dir_label)
        
        # Using rounded and flat style classes for better Adwaita styling
        self.search_dir_button = Gtk.Button(label=_("Select Directory"))
        self.search_dir_button.connect("clicked", self.on_search_dir_button_clicked)
        self.search_dir_button.add_css_class("pill")
        self.search_dir_button.add_css_class("flat")
        
        dir_row.add_suffix(dir_info_box)
        dir_row.add_suffix(self.search_dir_button)
        dir_row.set_activatable_widget(self.search_dir_button)
        settings_group.add(dir_row)
        
        # Simultaneous processes
        proc_row = Adw.ActionRow(title=_("Simultaneous processes"))
        proc_row.set_subtitle(_("Number of conversions to run in parallel"))
        
        adjustment = Gtk.Adjustment(value=2, lower=1, upper=16, step_increment=1, page_increment=2)
        self.max_procs_spin = Gtk.SpinButton()
        self.max_procs_spin.set_adjustment(adjustment)
        self.max_procs_spin.set_numeric(True)
        # Add some visual styling to the spinbutton
        self.max_procs_spin.add_css_class("numeric")
        
        proc_row.add_suffix(self.max_procs_spin)
        settings_group.add(proc_row)
        
        # Minimum file size
        size_row = Adw.ActionRow(title=_("Minimum MP4 size"))
        size_row.set_subtitle(_("Threshold for considering conversion successful (KB)"))
        
        adjustment = Gtk.Adjustment(value=1024, lower=1, upper=999999, step_increment=100, page_increment=1000)
        self.min_mp4_size_spin = Gtk.SpinButton()
        self.min_mp4_size_spin.set_adjustment(adjustment)
        self.min_mp4_size_spin.set_numeric(True)
        
        size_row.add_suffix(self.min_mp4_size_spin)
        settings_group.add(size_row)
        
        # Log file
        self.log_file_entry = Adw.EntryRow(title=_("Log file"))
        self.log_file_entry.set_text("comm-mkv-mp4-converter.log")
        self.log_file_entry.set_tooltip_text(_("Path to save the conversion log"))
        settings_group.add(self.log_file_entry)
        
        # Delete originals
        self.delete_batch_originals_check = Adw.SwitchRow(title=_("Delete original MKV files"))
        self.delete_batch_originals_check.set_subtitle(_("Remove source files after successful conversion"))
        settings_group.add(self.delete_batch_originals_check)
        
        main_content.append(settings_group)
        
        # Connect settings
        self._connect_settings()
        
        # Convert button - ensure this is properly styled and visible
        convert_button = Gtk.Button(label=_("Convert All MKVs"))
        convert_button.add_css_class("suggested-action")
        convert_button.add_css_class("pill")  # Rounded button style
        convert_button.set_hexpand(False)     # Don't expand horizontally
        convert_button.set_halign(Gtk.Align.CENTER)  # Center align the button
        convert_button.connect("clicked", self.on_convert_button_clicked)
        
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        button_box.set_spacing(10)
        button_box.set_margin_top(24)
        button_box.set_margin_bottom(24)  # Add bottom margin
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.append(convert_button)
        
        main_content.append(button_box)
        
        return page
        
    def _connect_settings(self):
        """Connect UI elements to settings"""
        settings = self.app.settings_manager
        
        # Load settings
        search_dir = settings.load_setting("search-directory", "")
        if search_dir and os.path.exists(search_dir):
            self.search_dir_label.set_text(search_dir)
            
        self.max_procs_spin.set_value(settings.load_setting("max-processes", 2))
        self.min_mp4_size_spin.set_value(settings.load_setting("min-mp4-size", 1024))
        self.log_file_entry.set_text(settings.load_setting("log-file", "comm-mkv-mp4-converter.log"))
        self.delete_batch_originals_check.set_active(settings.load_setting("delete-batch-originals", False))
        
        # Connect signals
        self.max_procs_spin.connect("value-changed", 
                                   lambda w: settings.save_setting("max-processes", int(w.get_value())))
        self.min_mp4_size_spin.connect("value-changed", 
                                      lambda w: settings.save_setting("min-mp4-size", int(w.get_value())))
        self.log_file_entry.connect("changed", 
                                   lambda w: settings.save_setting("log-file", w.get_text()))
        self.delete_batch_originals_check.connect("notify::active", 
                                                lambda w, p: settings.save_setting("delete-batch-originals", w.get_active()))
    
    def on_help_clicked(self, button):
        """Show help information for batch mode"""
        self.app.show_info_dialog(
            _("Batch Conversion Help"),
            _("This mode will search for all MKV files in the selected directory and "
              "convert them to MP4.\n\n"
              "The original MKV file will only be removed if the MP4 is created "
              "successfully and has the defined minimum size.")
        )
    
    def on_search_dir_button_clicked(self, button):
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Select Directory"))
        dialog.set_initial_folder(Gio.File.new_for_path(self.app.last_accessed_directory))
        dialog.select_folder(self.app.window, None, self._on_search_dir_chosen)
    
    def _on_search_dir_chosen(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                folder_path = folder.get_path()
                self.search_dir_label.set_text(folder_path)
                self.app.last_accessed_directory = folder_path
                # Save search directory and last accessed directory to settings
                self.app.settings_manager.save_setting("search-directory", folder_path)
                self.app.settings_manager.save_setting("last-accessed-directory", folder_path)
        except Exception as e:
            print(f"Error selecting directory: {e}")
    
    def on_convert_button_clicked(self, button):
        # Build command for comm-mkv-mp4-all
        if not self.search_dir_label.get_text() or self.search_dir_label.get_text() == _("No directory selected"):
            self.app.show_error_dialog(_("Please select a directory to search for MKV files."))
            return
            
        search_dir = self.search_dir_label.get_text()
        max_procs = int(self.max_procs_spin.get_value())
        min_mp4_size = int(self.min_mp4_size_spin.get_value())
        log_file = self.log_file_entry.get_text()
        
        # Check if we want to delete the original files
        delete_originals = self.delete_batch_originals_check.get_active()
        
        # Save current settings
        self.app.settings_manager.save_setting("search-directory", search_dir)
        self.app.settings_manager.save_setting("max-processes", max_procs)
        self.app.settings_manager.save_setting("min-mp4-size", min_mp4_size)
        self.app.settings_manager.save_setting("log-file", log_file)
        self.app.settings_manager.save_setting("delete-batch-originals", delete_originals)
        
        # Build command using absolute path to comm-mkv-mp4-all
        cmd = [MKV_MP4_ALL_PATH, 
               "--dir", search_dir, 
               "--procs", str(max_procs), 
               "--size", str(min_mp4_size), 
               "--log", log_file]
        
        if not delete_originals:
            cmd.append("--nodelete")
        
        # Create environment variables dictionary
        env_vars = os.environ.copy()
        
        # Try to apply encoding settings from settings page
        try:
            self.app.settings_page.apply_settings_to_env(env_vars)
        except Exception as e:
            print(f"Error applying settings: {e}")
        
        # Create and display progress dialog
        run_with_progress_dialog(
            self.app,
            cmd,
            f"Batch conversion ({os.path.basename(search_dir)})",
            None, 
            False, 
            env_vars
        )
