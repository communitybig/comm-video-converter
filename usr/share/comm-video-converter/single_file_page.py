import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, Pango, GLib

from constants import CONVERT_BIG_PATH
from conversion import run_with_progress_dialog

# Setup translation
import gettext
lang_translations = gettext.translation(
    "comm-video-converter", localedir="/usr/share/locale", fallback=True
)
lang_translations.install()
# define _ shortcut for translations
_ = lang_translations.gettext

class SingleFilePage:
    def __init__(self, app):
        self.app = app
        self.page = self._create_page()
        
        # Connect settings after UI is created
        self._connect_settings()
        
        # Show help on startup if enabled (default: True)
        show_help_on_startup = self.app.settings_manager.load_setting("show-single-help-on-startup", True)
        if show_help_on_startup:
            # Use GLib.idle_add to show the dialog after the UI is fully loaded
            GLib.idle_add(self.on_help_clicked, None)
    
    def get_page(self):
        return self.page
    
    def _create_page(self):
        # Create page for convert-big.sh
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
        
        # File section using Adw.PreferencesGroup
        file_group = Adw.PreferencesGroup()
        
        # Add help button to the header with a larger icon but same button size
        help_button = Gtk.Button()
        icon = Gtk.Image.new_from_icon_name("help-about-symbolic")
        icon.set_pixel_size(22)
        icon.add_css_class("accent")
        help_button.set_child(icon)
        help_button.add_css_class("flat")
        help_button.add_css_class("circular")
        help_button.connect("clicked", self.on_help_clicked)
        file_group.set_header_suffix(help_button)
        
        # Input file row
        file_row = Adw.ActionRow(title=_("Input file"))
        file_row.set_subtitle(_("Select the video file to convert"))
        self.file_path_label = Gtk.Label(label=_("No file selected"))
        self.file_path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.file_path_label.set_hexpand(True)
        self.file_path_label.set_halign(Gtk.Align.START)
        
        self.file_chooser_button = Gtk.Button(label=_("Select File"))
        self.file_chooser_button.connect("clicked", self.on_file_chooser_clicked)
        self.file_chooser_button.add_css_class("pill")
        self.file_chooser_button.add_css_class("flat")
        
        file_row.add_suffix(self.file_path_label)
        file_row.add_suffix(self.file_chooser_button)
        file_row.set_activatable_widget(self.file_chooser_button)
        file_group.add(file_row)
        
        # Output file row
        self.output_file_entry = Adw.EntryRow(title=_("Output file"))
        self.output_file_entry.set_tooltip_text(_("Leave empty to use the same name"))
        file_group.add(self.output_file_entry)
        
        # Output folder row
        output_folder_row = Adw.ActionRow(title=_("Output folder"))
        output_folder_row.set_subtitle(_("Leave empty to use the same folder"))
        
        self.output_folder_entry = Gtk.Entry()
        self.output_folder_entry.set_hexpand(True)
        
        folder_button = Gtk.Button()
        folder_button.set_icon_name("folder-symbolic")
        folder_button.connect("clicked", self.on_folder_button_clicked)
        folder_button.add_css_class("flat")
        folder_button.add_css_class("round")
        
        output_folder_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        output_folder_box.append(self.output_folder_entry)
        output_folder_box.append(folder_button)
        
        output_folder_row.add_suffix(output_folder_box)
        file_group.add(output_folder_row)
        
        # Option to delete original file
        self.delete_original_check = Adw.SwitchRow(title=_("Delete original MKV file"))
        self.delete_original_check.set_subtitle(_("Remove original file after successful conversion"))
        file_group.add(self.delete_original_check)
        
        main_content.append(file_group)


        
        # Convert button - ensure this is properly styled and visible
        convert_button = Gtk.Button(label=_("Convert Video"))
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
        
        # Load settings and update UI
        output_folder = settings.load_setting("output-folder", "")
        delete_original = settings.load_setting("delete-original", False)
        show_help_on_startup = settings.load_setting("show-single-help-on-startup", True)
        
        self.output_folder_entry.set_text(output_folder)
        self.delete_original_check.set_active(delete_original)
        
        # Connect signals
        self.output_folder_entry.connect("changed", 
                                        lambda w: settings.save_setting("output-folder", w.get_text()))
    
    def on_help_clicked(self, button):
        """Show help information for single file mode with a switch to control startup behavior"""
        # Create a dialog window properly using Adw.Window
        dialog = Adw.Window()
        dialog.set_default_size(700, 550)
        dialog.set_modal(True)
        dialog.set_transient_for(self.app.window)
        dialog.set_hide_on_close(True)
        
        # Create content box
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Add header bar
        header_bar = Adw.HeaderBar()
        header_bar.set_title_widget(Gtk.Label(label=_("Comm Video Converter")))
        content_box.append(header_bar)
        
        # Create main box to hold everything with proper layout
        outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer_box.set_vexpand(True)
        
        # Create scrolled window for content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        
        # Main content
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        main_box.set_margin_top(12)
        main_box.set_spacing(12)
        
        # Help introduction
        intro_label = Gtk.Label()
        intro_label.set_wrap(True)
        intro_label.set_xalign(0)
        intro_label.set_margin_bottom(16)
        intro_label.set_markup(_(
            "A powerful tool for converting video files to MP4 format."
        ))
        main_box.append(intro_label)
        
        # Features list using bullet points
        features_list = [
            _("• GPU-accelerated conversion for NVIDIA, AMD, and Intel GPUs"),
            _("• High-quality video processing with customizable settings"),
            _("• Support for various video codecs (H.264, H.265/HEVC, AV1, VP9)"),
            _("• Subtitle extraction and embedding"),
            _("• Batch processing capabilities")
        ]
        
        for feature in features_list:
            feature_label = Gtk.Label()
            feature_label.set_wrap(True)
            feature_label.set_xalign(0)
            feature_label.set_markup(feature)
            feature_label.set_margin_start(12)
            feature_label.set_margin_bottom(4)
            main_box.append(feature_label)
        
        # Additional information
        info_label = Gtk.Label()
        info_label.set_wrap(True)
        info_label.set_xalign(0)
        info_label.set_margin_top(16)
        info_label.set_markup(_(
            "This application uses <b>FFmpeg</b> for reliable, high-performance video conversion. "
            "The GPU acceleration significantly reduces conversion time compared to software-only processing."
        ))
        main_box.append(info_label)
        
        # Add main box to scrolled window
        scrolled.set_child(main_box)
        outer_box.append(scrolled)
        
        # Create bottom area with fixed height
        bottom_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bottom_area.set_margin_start(24)
        bottom_area.set_margin_end(24)
        bottom_area.set_margin_top(12)
        bottom_area.set_margin_bottom(12)
        
        # Add separator above bottom area
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        bottom_area.append(separator)
        
        # Create a box for controls with spacing
        controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        controls_box.set_margin_top(12)
        controls_box.set_margin_bottom(12)
        
        # Get current setting value
        current_value = self.app.settings_manager.load_setting("show-single-help-on-startup", True)
        
        # Create switch with label
        switch_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        switch_box.set_hexpand(True)
        
        switch_label = Gtk.Label(label=_("Show dialog on startup"))
        switch_label.set_halign(Gtk.Align.START)
        
        show_on_startup_switch = Gtk.Switch()
        show_on_startup_switch.set_active(current_value)
        show_on_startup_switch.set_valign(Gtk.Align.CENTER)
        
        switch_box.append(switch_label)
        switch_box.append(show_on_startup_switch)
        controls_box.append(switch_box)
        
        # Add close button
        close_button = Gtk.Button(label=_("Close"))
        close_button.add_css_class("pill")
        close_button.add_css_class("suggested-action")
        close_button.connect("clicked", lambda btn: dialog.close())
        close_button.set_halign(Gtk.Align.END)
        controls_box.append(close_button)
        
        bottom_area.append(controls_box)
        outer_box.append(bottom_area)
        
        content_box.append(outer_box)
        
        # Set content and present dialog
        dialog.set_content(content_box)
        
        # Connect the switch signal
        show_on_startup_switch.connect("notify::active", self._on_dialog_switch_toggled)
        
        dialog.present()
    
    def _on_dialog_switch_toggled(self, switch, param):
        """Handle toggling the switch in the help dialog"""
        value = switch.get_active()
        # Update setting
        self.app.settings_manager.save_setting("show-single-help-on-startup", value)
    
    def on_file_chooser_clicked(self, button):
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Select File"))
        dialog.set_initial_folder(Gio.File.new_for_path(self.app.last_accessed_directory))
        
        # Create filter for video files
        filter_list = Gio.ListStore.new(Gtk.FileFilter)
        
        video_filter = Gtk.FileFilter()
        video_filter.set_name(_("Video files"))
        # Add common video MIME types
        video_filter.add_mime_type("video/mp4")
        video_filter.add_mime_type("video/x-matroska")
        video_filter.add_mime_type("video/x-msvideo")
        video_filter.add_mime_type("video/quicktime")
        video_filter.add_mime_type("video/webm")
        video_filter.add_mime_type("video/x-flv")
        video_filter.add_mime_type("video/mpeg")
        video_filter.add_mime_type("video/3gpp")
        video_filter.add_mime_type("video/x-ms-wmv")
        video_filter.add_mime_type("video/ogg")
        video_filter.add_mime_type("video/mp2t")
        filter_list.append(video_filter)
        
        all_filter = Gtk.FileFilter()
        all_filter.set_name(_("All files"))
        all_filter.add_pattern("*")
        filter_list.append(all_filter)
        
        dialog.set_filters(filter_list)
        dialog.set_default_filter(video_filter)
        
        dialog.open(self.app.window, None, self._on_file_chosen)
    
    def _on_file_chosen(self, dialog, result):
        try:
            file = dialog.open_finish(result)
            if file:
                file_path = file.get_path()
                self.file_path_label.set_text(file_path)
                self.app.last_accessed_directory = os.path.dirname(file_path)
                # Save last accessed directory to settings
                self.app.settings_manager.save_setting("last-accessed-directory", 
                                                     self.app.last_accessed_directory)
        except Exception as e:
            print(f"Error selecting file: {e}")
    
    def on_folder_button_clicked(self, button):
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Select the output folder"))
        dialog.set_initial_folder(Gio.File.new_for_path(self.app.last_accessed_directory))
        dialog.select_folder(self.app.window, None, self._on_folder_chosen)
    
    def _on_folder_chosen(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                folder_path = folder.get_path()
                self.output_folder_entry.set_text(folder_path)
                # Save output folder to settings
                self.app.settings_manager.save_setting("output-folder", folder_path)
        except Exception as e:
            print(f"Error selecting folder: {e}")
    
    def on_convert_button_clicked(self, button):
        # Build command for convert-big.sh
        if not self.file_path_label.get_text() or self.file_path_label.get_text() == _("No file selected"):
            self.app.show_error_dialog(_("Please select an input file."))
            return
            
        input_file = self.file_path_label.get_text()
        
        # Check if the file exists
        if not os.path.exists(input_file):
            self.app.show_error_dialog(_("The selected file does not exist: {0}").format(input_file))
            return
        
        # Check if the file is an MKV (for potential deletion)
        is_mkv = input_file.lower().endswith('.mkv')
        # Notify the user if they try to delete non-MKV files
        if self.delete_original_check.get_active() and not is_mkv:
            self.app.show_info_dialog(
                _("Information"),
                _("Note: The 'Delete original file' option only applies to MKV files.\n"
                "Your selected file will be converted but not deleted.")
            )
        
        # Check if the script exists
        if not os.path.exists(CONVERT_BIG_PATH):
            self.app.show_error_dialog(_("Conversion script not found: {0}").format(CONVERT_BIG_PATH))
            return
        
        # Build environment variables
        env_vars = os.environ.copy()  # Start with current environment
        
        # Get settings from settings page
        try:
            self.app.settings_page.apply_settings_to_env(env_vars)
        except Exception as e:
            print(f"Error applying settings: {e}")
        
        # Add output settings
        output_file_text = self.output_file_entry.get_text()
        if output_file_text:
            env_vars["output_file"] = output_file_text
            
        if self.output_folder_entry.get_text():
            env_vars["output_folder"] = self.output_folder_entry.get_text()
        
        cmd = [CONVERT_BIG_PATH, input_file]
        
        # Add trim options if applicable
        trim_options = self.get_trim_command_options()
        if trim_options:
            cmd.extend(trim_options)
        
        # Reset trim times after conversion
        self.app.set_trim_times(0, None, 0)
        
        # Debug output
        print(f"Command: {' '.join(cmd)}")
        print(f"Environment variables: {env_vars}")
        
        # Create and display progress dialog
        run_with_progress_dialog(
            self.app,
            cmd,
            f"{os.path.basename(input_file)}",
            input_file if is_mkv else None,
            self.delete_original_check.get_active(),
            env_vars
        )
    
    def get_selected_file_path(self):
        """Return the currently selected file path or None if no valid file is selected"""
        file_path = self.file_path_label.get_text()
        if file_path and file_path != _("No file selected") and os.path.exists(file_path):
            return file_path
        return None
    
    def get_trim_command_options(self):
        """Get ffmpeg command options for trimming based on set trim points"""
        start_time, end_time, duration = self.app.get_trim_times()
        
        # Only add trim options if either start_time > 0 or end_time is not None
        options = []
        
        if start_time > 0:
            # Format start time for ffmpeg (-ss option)
            start_str = self.format_time_ffmpeg(start_time)
            options.append("-ss")
            options.append(start_str)
        
        if end_time is not None and end_time < duration:
            if start_time > 0:
                # If we have a start time, use -t (duration) instead of -to (end time)
                trim_duration = end_time - start_time
                duration_str = self.format_time_ffmpeg(trim_duration)
                options.append("-t")
                options.append(duration_str)
            else:
                # If no start time, use -to (end time)
                end_str = self.format_time_ffmpeg(end_time)
                options.append("-to")
                options.append(end_str)
        
        return options

    def format_time_ffmpeg(self, seconds):
        """Format time in seconds to HH:MM:SS.mmm format for ffmpeg"""
        hours = int(seconds) // 3600
        minutes = (int(seconds) % 3600) // 60
        seconds_remainder = int(seconds) % 60
        milliseconds = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds_remainder:02d}.{milliseconds:03d}"
