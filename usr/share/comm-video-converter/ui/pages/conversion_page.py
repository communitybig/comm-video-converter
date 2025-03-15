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

        # Output folder row
        output_folder_row = Adw.ActionRow(title=_("Output folder"))
        output_folder_row.set_subtitle(
            _("Leave empty to use the same folder as input files")
        )

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
        self.delete_original_check = Adw.SwitchRow(title=_("Delete original files"))
        self.delete_original_check.set_subtitle(
            _("Remove original files after successful conversion")
        )
        file_group.add(self.delete_original_check)

        main_content.append(file_group)

        # Queue section
        queue_group = Adw.PreferencesGroup(title=_("Conversion Queue"))

        # Create a queue listbox with a scrolled window
        queue_scroll = Gtk.ScrolledWindow()
        queue_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        queue_scroll.set_min_content_height(200)  # Increased height
        queue_scroll.set_max_content_height(300)  # Increased height

        # Create a listbox for the queue items
        self.queue_listbox = Gtk.ListBox()
        self.queue_listbox.add_css_class("boxed-list")
        self.queue_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.queue_listbox.connect("row-activated", self.on_queue_item_activated)
        queue_scroll.set_child(self.queue_listbox)

        # Add the listbox to an ActionRow to provide padding
        queue_list_row = Adw.ActionRow()
        queue_list_row.set_activatable(False)
        queue_list_row.add_suffix(queue_scroll)
        queue_list_row.set_title("")  # Empty title for proper layout
        queue_group.add(queue_list_row)

        # Create button box for queue management
        queue_buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        queue_buttons_box.set_halign(Gtk.Align.CENTER)
        queue_buttons_box.set_spacing(12)
        queue_buttons_box.set_margin_top(12)
        queue_buttons_box.set_margin_bottom(12)

        # Queue management buttons
        clear_queue_button = Gtk.Button(label=_("Clear Queue"))
        clear_queue_button.connect("clicked", self.on_clear_queue_clicked)
        clear_queue_button.add_css_class("pill")
        queue_buttons_box.append(clear_queue_button)

        # Add files button (always adds to queue)
        add_files_button = Gtk.Button(label=_("Add Files"))
        add_files_button.connect("clicked", self.on_add_files_clicked)
        add_files_button.add_css_class("pill")
        add_files_button.add_css_class("suggested-action")
        queue_buttons_box.append(add_files_button)

        # Single convert button that processes the queue
        convert_button = Gtk.Button(label=_("Convert All"))
        convert_button.add_css_class("pill")
        convert_button.add_css_class("suggested-action")
        convert_button.connect("clicked", self.on_convert_clicked)
        self.convert_button = convert_button  # Store reference for enabling/disabling
        queue_buttons_box.append(convert_button)

        # Add the button box to an action row for proper layout
        queue_buttons_row = Adw.ActionRow()
        queue_buttons_row.set_activatable(False)
        queue_buttons_row.add_suffix(queue_buttons_box)
        queue_buttons_row.set_title("")  # Empty title for proper layout
        queue_group.add(queue_buttons_row)

        main_content.append(queue_group)

        # Update the queue display initially
        self.update_queue_display()

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

    def on_add_files_clicked(self, button):
        """Open file chooser to add files to the queue"""
        self.app.select_files_for_queue()

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

    def on_convert_clicked(self, button):
        """Start processing the queue"""
        # If queue is empty, show error
        if not self.app.conversion_queue:
            self.app.show_error_dialog(_("Please add files to the queue first."))
            return

        # Set the global delete original setting based on checkbox
        self.app.delete_original_after_conversion = (
            self.delete_original_check.get_active()
        )

        # Set the global output folder setting
        output_folder = self.output_folder_entry.get_text().strip()
        if output_folder:
            self.app.settings_manager.save_setting("output-folder", output_folder)

        # Start queue processing
        self.app.start_queue_processing()

    def on_clear_queue_clicked(self, button):
        """Clear all files from the queue"""
        self.app.clear_queue()

    def on_queue_item_activated(self, listbox, row):
        """Handle selection of a queue item - preview or view details"""
        if row and hasattr(row, "file_path") and row.file_path:
            # Show file details dialog or preview
            file_path = row.file_path
            if os.path.exists(file_path):
                self.app.show_file_details(file_path)

    def update_queue_display(self):
        """Update the queue display with current items"""
        # Clear existing items
        while True:
            row = self.queue_listbox.get_first_child()
            if row:
                self.queue_listbox.remove(row)
            else:
                break

        # Add current queue items
        for file_path in self.app.conversion_queue:
            if not os.path.exists(file_path):
                continue

            # Create a row for the file using ActionRow for better styling
            row = Adw.ActionRow()

            # Set title with filename and make it more prominent
            filename = os.path.basename(file_path)
            row.set_title(filename)
            row.set_title_lines(1)  # Ensure title gets one full line

            # Set directory as subtitle, but limit its display
            directory = os.path.dirname(file_path)
            row.set_subtitle(directory)
            row.set_subtitle_lines(1)  # Limit subtitle to one line

            # Ensure the row expands to fill available space
            row.set_hexpand(True)

            # Add remove button with proper spacing
            remove_button = Gtk.Button()
            remove_button.set_icon_name("list-remove-symbolic")
            remove_button.add_css_class("flat")
            remove_button.add_css_class("circular")
            remove_button.set_tooltip_text(_("Remove from queue"))
            remove_button.set_valign(Gtk.Align.CENTER)
            remove_button.connect("clicked", self.on_remove_from_queue, file_path)

            # Use a box to add some margin to the button
            button_box = Gtk.Box()
            button_box.set_margin_start(12)  # Add space before the button
            button_box.append(remove_button)

            row.add_suffix(button_box)

            # Make row activatable (clickable)
            row.set_activatable(True)

            # Store the file path using a standard Python attribute
            row.file_path = file_path

            # Add to listbox
            self.queue_listbox.append(row)

            # Ensure the listbox allocates sufficient height per row
            row.set_margin_top(4)
            row.set_margin_bottom(4)

        # Show a message if the queue is empty
        if len(self.app.conversion_queue) == 0:
            empty_label = Gtk.Label(label=_("Queue is empty. Add files to convert."))
            empty_label.set_margin_top(12)
            empty_label.set_margin_bottom(12)
            empty_label.add_css_class("dim-label")
            self.queue_listbox.append(empty_label)

        # Enable or disable convert button based on queue state
        self.convert_button.set_sensitive(len(self.app.conversion_queue) > 0)

    def on_remove_from_queue(self, button, file_path):
        """Remove a specific file from the queue"""
        self.app.remove_from_queue(file_path)
        self.update_queue_display()

    def get_selected_file_path(self):
        """Get currently selected file in queue or None"""
        for i in range(len(self.app.conversion_queue)):
            file_path = self.app.conversion_queue[i]
            if os.path.exists(file_path):
                return file_path
        return None

    def set_file(self, file_path):
        """Set the current file path for conversion (required for queue processing)"""
        if file_path and os.path.exists(file_path):
            # Store the current file to be processed
            self.current_file_path = file_path

            # Update output folder to match input folder
            input_dir = os.path.dirname(file_path)
            self.output_folder_entry.set_text(input_dir)

            # Keep last accessed directory updated
            self.app.last_accessed_directory = input_dir
            self.app.settings_manager.save_setting("last-accessed-directory", input_dir)
            return True
        return False

    def force_start_conversion(self):
        """Start conversion process with the currently selected file"""
        # Check if we have a file to convert
        if not hasattr(self, "current_file_path") or not os.path.exists(
            self.current_file_path
        ):
            print("Cannot start conversion: No valid file selected")
            return False

        # Get the file to convert
        input_file = self.current_file_path
        print(f"Starting conversion for: {input_file}")

        # Get absolute path to input directory
        input_dir = os.path.dirname(os.path.abspath(input_file))

        # Check if the conversion script exists
        if not os.path.exists(CONVERT_SCRIPT_PATH):
            self.app.show_error_dialog(
                _("Conversion script not found: {0}").format(CONVERT_SCRIPT_PATH)
            )
            return False

        # Build environment variables
        env_vars = os.environ.copy()  # Start with current environment

        # Load app settings for conversion
        try:
            if hasattr(self.app, "settings_manager") and hasattr(
                self.app.settings_manager, "json_config"
            ):
                settings = self.app.settings_manager.json_config

                # Map settings to environment variables
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

                # Apply settings
                for settings_key, env_key in settings_map.items():
                    value = settings.get(settings_key)
                    if isinstance(value, bool) and value:
                        env_vars[env_key] = "1"
                    elif value not in [None, "", False]:
                        env_vars[env_key] = str(value)
        except Exception as e:
            print(f"Error loading settings: {e}")

        # Set output folder
        output_folder = self.output_folder_entry.get_text()
        if output_folder:
            if not os.path.isabs(output_folder):
                output_folder = os.path.abspath(output_folder)
            env_vars["output_folder"] = output_folder
            print(f"Using specified output folder: {output_folder}")
        else:
            env_vars["output_folder"] = input_dir
            print(f"Using input file directory as output: {input_dir}")

        # Build the conversion command
        cmd = [CONVERT_SCRIPT_PATH, input_file]

        # Add trim options if applicable
        trim_options = self._get_trim_command_options()
        if trim_options:
            cmd.extend(trim_options)

        # Reset trim times after conversion
        self.app.set_trim_times(0, None, 0)

        # Delete original setting
        delete_original = self.delete_original_check.get_active()

        # Create and display progress dialog
        run_with_progress_dialog(
            self.app,
            cmd,
            f"{os.path.basename(input_file)}",
            input_file if delete_original else None,
            delete_original,
            env_vars,
        )

        return True

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
