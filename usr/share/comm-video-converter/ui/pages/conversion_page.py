import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, Pango, GLib

from constants import CONVERT_SCRIPT_PATH, VIDEO_FILE_MIME_TYPES
from utils.conversion import run_with_progress_dialog

# Setup translation
import gettext

_ = gettext.gettext


class ConversionPage:
    """
    Conversion page UI component.
    Provides interface for selecting and converting video files.
    """

    def __init__(self, app):
        self.app = app
        self.page = self._create_page()

        # Connect settings after UI is created
        self._connect_settings()

        # Show help on startup if enabled (default: True)
        try:
            # Try to load the setting
            show_help_on_startup = self.app.settings_manager.load_setting(
                "show-conversion-help-on-startup", True
            )
            print(
                f"Loaded setting show-conversion-help-on-startup: {show_help_on_startup}"
            )

            # Check if it's explicitly False (not just None or some other falsy value)
            if show_help_on_startup is False:
                print("Help dialog disabled by user setting")
            else:
                # Default behavior is to show dialog
                print("Help dialog will be shown (default or user setting)")
                # Use GLib.idle_add to show the dialog after the UI is fully loaded
                GLib.idle_add(self.on_help_clicked, None)
        except Exception as e:
            # If there's an error loading the setting, log it and default to showing help
            print(f"Error loading dialog setting: {e}")
            print("Defaulting to show help dialog")
            GLib.idle_add(self.on_help_clicked, None)

    def get_page(self):
        """Return the page widget"""
        return self.page

    def _create_page(self):
        # Create page for conversion
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
        folder_button.add_css_class("circular")

        output_folder_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        output_folder_box.append(self.output_folder_entry)
        output_folder_box.append(folder_button)

        output_folder_row.add_suffix(output_folder_box)
        file_group.add(output_folder_row)

        # Option to delete original file
        self.delete_original_check = Adw.SwitchRow(title=_("Delete original file"))
        self.delete_original_check.set_subtitle(
            _("Remove original file after successful conversion")
        )
        file_group.add(self.delete_original_check)

        main_content.append(file_group)

        # Convert button - ensure this is properly styled and visible
        convert_button = Gtk.Button(label=_("Convert"))
        convert_button.add_css_class("suggested-action")
        convert_button.add_css_class("pill")  # Rounded button style
        convert_button.set_hexpand(False)  # Don't expand horizontally
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

        self.output_folder_entry.set_text(output_folder)
        self.delete_original_check.set_active(delete_original)

        # Connect signals
        self.output_folder_entry.connect(
            "changed", lambda w: settings.save_setting("output-folder", w.get_text())
        )

        self.delete_original_check.connect(
            "notify::active",
            lambda w, p: settings.save_setting("delete-original", w.get_active()),
        )

    def on_help_clicked(self, button):
        """Show help information for conversion mode with a switch to control startup behavior"""
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
        intro_label.set_markup(
            _("A powerful tool for converting video files to MP4 format.")
        )
        main_box.append(intro_label)

        # Features list using bullet points
        features_list = [
            _("• GPU-accelerated conversion for NVIDIA, AMD, and Intel GPUs"),
            _("• High-quality video processing with customizable settings"),
            _("• Support for various video codecs (H.264, H.265/HEVC, AV1, VP9)"),
            _("• Subtitle extraction and embedding"),
            _("• Video preview with trimming and effects"),
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
        info_label.set_markup(
            _(
                "This application uses <b>FFmpeg</b> for reliable, high-performance video conversion. "
                "The GPU acceleration significantly reduces conversion time compared to software-only processing."
            )
        )
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
        current_value = self.app.settings_manager.load_setting(
            "show-conversion-help-on-startup", True
        )

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
        try:
            value = switch.get_active()

            # Print debug information
            print(
                f"Attempting to save setting: show-conversion-help-on-startup = {value}"
            )

            # Update setting
            success = self.app.settings_manager.save_setting(
                "show-conversion-help-on-startup", value
            )

            if success:
                print(
                    f"Successfully saved setting: show-conversion-help-on-startup = {value}"
                )
            else:
                print("Warning: Setting may not have been saved properly.")

        except Exception as e:
            # Log the error
            print(f"Error toggling dialog setting: {str(e)}")

            # Fallback approach - try direct save
            try:
                settings_file = os.path.expanduser(
                    "~/.config/comm-video-converter/settings.json"
                )
                os.makedirs(os.path.dirname(settings_file), exist_ok=True)

                # Load existing settings if available
                settings = {}
                if os.path.exists(settings_file):
                    with open(settings_file, "r") as f:
                        import json

                        try:
                            settings = json.load(f)
                        except:
                            settings = {}

                # Update the setting
                settings["show-conversion-help-on-startup"] = switch.get_active()

                # Write back to file
                with open(settings_file, "w") as f:
                    import json

                    json.dump(settings, f, indent=2)

                print(f"Saved setting using fallback method to: {settings_file}")
            except Exception as backup_error:
                print(f"Even fallback saving method failed: {str(backup_error)}")

    def on_file_chooser_clicked(self, button):
        """Open file chooser dialog to select a video file"""
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Select File"))
        dialog.set_initial_folder(
            Gio.File.new_for_path(self.app.last_accessed_directory)
        )

        # Create filter for video files
        filter_list = Gio.ListStore.new(Gtk.FileFilter)

        video_filter = Gtk.FileFilter()
        video_filter.set_name(_("Video files"))
        # Add common video MIME types
        for mime_type in VIDEO_FILE_MIME_TYPES:
            video_filter.add_mime_type(mime_type)
        filter_list.append(video_filter)

        all_filter = Gtk.FileFilter()
        all_filter.set_name(_("All files"))
        all_filter.add_pattern("*")
        filter_list.append(all_filter)

        dialog.set_filters(filter_list)
        dialog.set_default_filter(video_filter)

        dialog.open(self.app.window, None, self._on_file_chosen)

    def _on_file_chosen(self, dialog, result):
        """Handle selected file from file chooser"""
        try:
            file = dialog.open_finish(result)
            if file:
                file_path = file.get_path()
                self.file_path_label.set_text(file_path)
                input_dir = os.path.dirname(file_path)
                self.app.last_accessed_directory = input_dir
                # Save last accessed directory to settings
                self.app.settings_manager.save_setting(
                    "last-accessed-directory", self.app.last_accessed_directory
                )

                # Auto-set output file name if empty
                if not self.output_file_entry.get_text():
                    input_basename = os.path.basename(file_path)
                    name, ext = os.path.splitext(input_basename)
                    # Set MP4 as default output extension
                    self.output_file_entry.set_text(f"{name}.mp4")

                # CORREÇÃO: Auto-set output folder to match input folder
                # This ensures converted files go to the same directory as originals
                self.output_folder_entry.set_text(input_dir)
                # Save this as the default output folder
                self.app.settings_manager.save_setting("output-folder", input_dir)
        except Exception as e:
            print(f"Error selecting file: {e}")

    def on_folder_button_clicked(self, button):
        """Open folder chooser dialog to select output folder"""
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Select the output folder"))
        dialog.set_initial_folder(
            Gio.File.new_for_path(self.app.last_accessed_directory)
        )
        dialog.select_folder(self.app.window, None, self._on_folder_chosen)

    def _on_folder_chosen(self, dialog, result):
        """Handle selected folder from folder chooser"""
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
        """Handle convert button click, start conversion process"""
        # Check if input file is selected
        if not self.file_path_label.get_text() or self.file_path_label.get_text() == _(
            "No file selected"
        ):
            self.app.show_error_dialog(_("Please select an input file."))
            return

        input_file = self.file_path_label.get_text()

        # Obtenha o diretório do arquivo de entrada - caminho COMPLETO e ABSOLUTO
        input_dir = os.path.dirname(os.path.abspath(input_file))
        print(f"Input file directory (absolute): {input_dir}")

        # Check if the file exists
        if not os.path.exists(input_file):
            self.app.show_error_dialog(
                _("The selected file does not exist: {0}").format(input_file)
            )
            return

        # Check if the conversion script exists
        if not os.path.exists(CONVERT_SCRIPT_PATH):
            self.app.show_error_dialog(
                _("Conversion script not found: {0}").format(CONVERT_SCRIPT_PATH)
            )
            return

        # Build environment variables
        env_vars = os.environ.copy()  # Start with current environment

        # Em vez de mostrar o diálogo, apenas obtenha as configurações
        try:
            # Carregue as configurações diretamente
            if hasattr(self.app, "settings_manager") and hasattr(
                self.app.settings_manager, "json_config"
            ):
                settings = self.app.settings_manager.json_config

                # Mapeie as configurações para variáveis de ambiente
                settings_map = {
                    "gpu-selection": "gpu",
                    "video-quality": "video_quality",
                    "video-codec": "video_encoder",
                    "preset": "preset",
                    "subtitle-extract": "subtitle_extract",
                    "audio-handling": "audio_handling",
                    "audio-bitrate": "audio_bitrate",
                    "audio-channels": "audio_channels",
                    "video-resolution": "video_resolution",
                    "additional-options": "options",
                    "gpu-partial": "gpu_partial",
                    "force-copy-video": "force_copy_video",
                    "only-extract-subtitles": "only_extract_subtitles",
                }

                # Aplique as configurações
                for settings_key, env_key in settings_map.items():
                    value = settings.get(settings_key)
                    if isinstance(value, bool) and value:
                        env_vars[env_key] = "1"
                    elif value not in [None, "", False]:
                        env_vars[env_key] = str(value)
        except Exception as e:
            print(f"Error loading settings: {e}")

        # Add output settings
        output_file_text = self.output_file_entry.get_text()
        if output_file_text:
            env_vars["output_file"] = output_file_text

        # CRUCIAL: Defina o diretório de saída corretamente
        output_folder = self.output_folder_entry.get_text()
        if output_folder:
            # Garanta que é caminho absoluto
            if not os.path.isabs(output_folder):
                output_folder = os.path.abspath(output_folder)
                self.output_folder_entry.set_text(output_folder)
            env_vars["output_folder"] = output_folder
            print(f"Using specified output folder: {output_folder}")
        else:
            # Se nenhum diretório de saída foi especificado, use o mesmo do arquivo de entrada
            env_vars["output_folder"] = input_dir
            # Atualize também o campo na interface para feedback visual
            self.output_folder_entry.set_text(input_dir)
            print(f"Using input file directory as output: {input_dir}")

        # Build the conversion command
        cmd = [CONVERT_SCRIPT_PATH, input_file]

        # Add trim options if applicable
        trim_options = self._get_trim_command_options()
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
            input_file if self.delete_original_check.get_active() else None,
            self.delete_original_check.get_active(),
            env_vars,
        )

    def get_selected_file_path(self):
        """Return the currently selected file path or None if no valid file is selected"""
        file_path = self.file_path_label.get_text()
        if (
            file_path
            and file_path != _("No file selected")
            and os.path.exists(file_path)
        ):
            return file_path
        return None

    def _get_trim_command_options(self):
        """Get ffmpeg command options for trimming based on set trim points"""
        start_time, end_time, duration = self.app.get_trim_times()

        # Only add trim options if either start_time > 0 or end_time is not None
        options = []

        if start_time > 0:
            # Format start time for ffmpeg (-ss option)
            start_str = self._format_time_ffmpeg(start_time)
            options.append("-ss")
            options.append(start_str)

        if end_time is not None and end_time < duration:
            if start_time > 0:
                # If we have a start time, use -t (duration) instead of -to (end time)
                trim_duration = end_time - start_time
                duration_str = self._format_time_ffmpeg(trim_duration)
                options.append("-t")
                options.append(duration_str)
            else:
                # If no start time, use -to (end time)
                end_str = self._format_time_ffmpeg(end_time)
                options.append("-to")
                options.append(end_str)

        return options

    def _format_time_ffmpeg(self, seconds):
        """Format time in seconds to HH:MM:SS.mmm format for ffmpeg"""
        hours = int(seconds) // 3600
        minutes = (int(seconds) % 3600) // 60
        seconds_remainder = int(seconds) % 60
        milliseconds = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds_remainder:02d}.{milliseconds:03d}"
