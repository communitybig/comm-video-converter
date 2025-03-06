#!/usr/bin/env python3
import os
import sys
import gi
import subprocess
import shlex
import re
import threading
import time

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

# Paths to executables
CONVERT_BIG_PATH = "/usr/bin/convert-big"
MKV_MP4_ALL_PATH = "/usr/bin/mkv-mp4-all"

# # During development, use local path if scripts are not installed
# if not os.path.exists(CONVERT_BIG_PATH):
#     CONVERT_BIG_PATH = "./convert-big.sh"
# if not os.path.exists(MKV_MP4_ALL_PATH):
#     MKV_MP4_ALL_PATH = "./mkv-mp4-all.sh"

class ProgressDialog(Gtk.Dialog):
    def __init__(self, parent, title, command, input_file=None):
        Gtk.Dialog.__init__(self, title=title, transient_for=parent, flags=0)
        self.set_default_size(450, 180)
        self.set_modal(True)
        
        # Store input file for possible later removal
        self.input_file = input_file
        self.delete_original = False  # Will be set by the caller
        
        # Add content area
        box = self.get_content_area()
        box.set_margin_top(15)
        box.set_margin_bottom(15)
        box.set_margin_start(15)
        box.set_margin_end(15)
        box.set_spacing(10)
        
        # Label for file
        command_label = Gtk.Label()
        command_label.set_line_wrap(True)
        file_name = os.path.basename(input_file) if input_file else "Multiple files"
        command_label.set_markup(f"<b>File:</b> {file_name}")
        command_label.set_xalign(0)
        box.add(command_label)
        
        # Label for status
        self.status_label = Gtk.Label(label="Starting conversion...")
        self.status_label.set_xalign(0)
        box.add(self.status_label)
        
        # Progress bar
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_text("0%")
        box.add(self.progress_bar)
        
        # Cancel button
        self.cancel_button = Gtk.Button(label="Cancel")
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        box.add(self.cancel_button)
        
        self.process = None
        self.cancelled = False
        self.success = False
        self.show_all()
    
    def on_cancel_clicked(self, button):
        if self.process:
            try:
                self.process.terminate()
                self.cancelled = True
                self.status_label.set_text("Conversion canceled.")
                self.progress_bar.set_fraction(0)
                self.progress_bar.set_text("Canceled")
            except:
                pass
        self.response(Gtk.ResponseType.CANCEL)
    
    def set_process(self, process):
        self.process = process
    
    def update_progress(self, fraction, text=None):
        self.progress_bar.set_fraction(fraction)
        if text:
            self.progress_bar.set_text(text)
        else:
            self.progress_bar.set_text(f"{int(fraction * 100)}%")
    
    def update_status(self, status):
        self.status_label.set_text(status)
    
    def set_delete_original(self, delete_original):
        self.delete_original = delete_original
    
    def mark_success(self):
        self.success = True


class VideoConverterApp:
    def __init__(self):
        # Create main window
        self.window = Gtk.Window(title="Comm Big Converter")
        self.window.set_default_size(800, 600)
        self.window.connect("destroy", Gtk.main_quit)
        
        # Configure application icon
        self.set_application_icon()
        
        # Create notebook (tabs)
        self.notebook = Gtk.Notebook()
        self.window.add(self.notebook)
        
        # Set the last accessed directory
        self.last_accessed_directory = os.path.expanduser("~")
        
        # Create pages
        self.create_convert_big_page()
        self.create_mkv_mp4_all_page()
        self.create_about_page()
        
        # State variables
        self.conversions_running = 0
        
        # Show window
        self.window.show_all()
    
    def set_application_icon(self):
        """Sets the application icon, checking multiple possible paths"""
        icon_paths = [
            # Paths to look for the icon
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "comm-big-converter.svg"),  # Local in current directory
            os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps/comm-big-converter.svg"),  # Local user installation
            "/usr/share/icons/hicolor/scalable/apps/comm-big-converter.svg"  # Global installation
        ]
        
        # Try each path until finding a valid icon
        for icon_path in icon_paths:
            if os.path.exists(icon_path):
                self.window.set_icon_from_file(icon_path)
                return
        
        # If SVG file not found, use system icon
        self.window.set_icon_name("video-x-generic")
    
    def create_convert_big_page(self):
        # Create page for convert-big.sh
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_margin_start(10)
        page.set_margin_end(10)
        page.set_margin_top(10)
        page.set_margin_bottom(10)
        
        # File section
        file_frame = Gtk.Frame(label="File")
        file_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        file_box.set_margin_start(10)
        file_box.set_margin_end(10)
        file_box.set_margin_top(10)
        file_box.set_margin_bottom(10)
        
        # Choose file
        file_box_row = Gtk.Box(spacing=5)
        file_label = Gtk.Label(label="Input file:")
        self.file_chooser = Gtk.FileChooserButton(title="Select File")
        self.file_chooser.set_current_folder(self.last_accessed_directory)
        self.file_chooser.connect("file-set", self.on_file_selected)
        file_box_row.pack_start(file_label, False, False, 0)
        file_box_row.pack_start(self.file_chooser, True, True, 0)
        file_box.pack_start(file_box_row, False, False, 0)
        
        # Output file
        output_box_row = Gtk.Box(spacing=5)
        output_label = Gtk.Label(label="Output file:")
        self.output_file_entry = Gtk.Entry()
        self.output_file_entry.set_placeholder_text("Leave empty to use the same name")
        output_box_row.pack_start(output_label, False, False, 0)
        output_box_row.pack_start(self.output_file_entry, True, True, 0)
        file_box.pack_start(output_box_row, False, False, 0)
        
        # Output folder
        folder_box_row = Gtk.Box(spacing=5)
        folder_label = Gtk.Label(label="Output folder:")
        self.output_folder_entry = Gtk.Entry()
        self.output_folder_entry.set_placeholder_text("Leave empty to use the same folder")
        folder_button = Gtk.Button()
        folder_button.set_image(Gtk.Image.new_from_icon_name("folder-symbolic", Gtk.IconSize.BUTTON))
        folder_button.connect("clicked", self.on_folder_button_clicked)
        folder_box_row.pack_start(folder_label, False, False, 0)
        folder_box_row.pack_start(self.output_folder_entry, True, True, 0)
        folder_box_row.pack_start(folder_button, False, False, 0)
        file_box.pack_start(folder_box_row, False, False, 0)
        
        # Option to delete original file
        delete_box_row = Gtk.Box(spacing=5)
        self.delete_original_check = Gtk.CheckButton(label="Delete original MKV file after successful conversion")
        delete_box_row.pack_start(self.delete_original_check, True, True, 0)
        file_box.pack_start(delete_box_row, False, False, 0)
        
        file_frame.add(file_box)
        page.pack_start(file_frame, False, False, 0)
        
        # Encoding section
        encoding_frame = Gtk.Frame(label="Encoding Settings")
        encoding_grid = Gtk.Grid()
        encoding_grid.set_row_spacing(10)
        encoding_grid.set_column_spacing(10)
        encoding_grid.set_margin_start(10)
        encoding_grid.set_margin_end(10)
        encoding_grid.set_margin_top(10)
        encoding_grid.set_margin_bottom(10)
        
        # GPU
        gpu_label = Gtk.Label(label="GPU:", halign=Gtk.Align.START)
        self.gpu_combo = Gtk.ComboBoxText()
        for option in ["Auto-detect", "nvidia", "amd", "intel", "software"]:
            self.gpu_combo.append_text(option)
        self.gpu_combo.set_active(0)
        encoding_grid.attach(gpu_label, 0, 0, 1, 1)
        encoding_grid.attach(self.gpu_combo, 1, 0, 1, 1)
        
        # Video quality
        quality_label = Gtk.Label(label="Video quality:", halign=Gtk.Align.START)
        self.video_quality_combo = Gtk.ComboBoxText()
        for option in ["Default", "veryhigh", "high", "medium", "low", "verylow"]:
            self.video_quality_combo.append_text(option)
        self.video_quality_combo.set_active(0)
        encoding_grid.attach(quality_label, 0, 1, 1, 1)
        encoding_grid.attach(self.video_quality_combo, 1, 1, 1, 1)
        
        # Video codec
        codec_label = Gtk.Label(label="Video codec:", halign=Gtk.Align.START)
        self.video_encoder_combo = Gtk.ComboBoxText()
        for option in ["Default (h264)", "h264 (MP4)", "h265 (HEVC)", "av1 (AV1)", "vp9 (VP9)"]:
            self.video_encoder_combo.append_text(option)
        self.video_encoder_combo.set_active(0)
        encoding_grid.attach(codec_label, 0, 2, 1, 1)
        encoding_grid.attach(self.video_encoder_combo, 1, 2, 1, 1)
        
        # Preset
        preset_label = Gtk.Label(label="Compression preset:", halign=Gtk.Align.START)
        self.preset_combo = Gtk.ComboBoxText()
        for option in ["Default", "ultrafast", "veryfast", "faster", "medium", "slow", "veryslow"]:
            self.preset_combo.append_text(option)
        self.preset_combo.set_active(0)
        encoding_grid.attach(preset_label, 0, 3, 1, 1)
        encoding_grid.attach(self.preset_combo, 1, 3, 1, 1)
        
        # Subtitles
        subtitle_label = Gtk.Label(label="Subtitle handling:", halign=Gtk.Align.START)
        self.subtitle_extract_combo = Gtk.ComboBoxText()
        for option in ["Default (extract)", "extract (SRT)", "embedded", "none"]:
            self.subtitle_extract_combo.append_text(option)
        self.subtitle_extract_combo.set_active(0)
        encoding_grid.attach(subtitle_label, 0, 4, 1, 1)
        encoding_grid.attach(self.subtitle_extract_combo, 1, 4, 1, 1)
        
        # Audio
        audio_label = Gtk.Label(label="Audio handling:", halign=Gtk.Align.START)
        self.audio_handling_combo = Gtk.ComboBoxText()
        for option in ["Default (copy)", "copy", "reencode", "none"]:
            self.audio_handling_combo.append_text(option)
        self.audio_handling_combo.set_active(0)
        encoding_grid.attach(audio_label, 0, 5, 1, 1)
        encoding_grid.attach(self.audio_handling_combo, 1, 5, 1, 1)
        
        # Audio bitrate
        bitrate_label = Gtk.Label(label="Audio bitrate:", halign=Gtk.Align.START)
        self.audio_bitrate_entry = Gtk.Entry()
        self.audio_bitrate_entry.set_placeholder_text("Ex: 128k, 192k, 256k")
        encoding_grid.attach(bitrate_label, 0, 6, 1, 1)
        encoding_grid.attach(self.audio_bitrate_entry, 1, 6, 1, 1)
        
        # Audio channels
        channels_label = Gtk.Label(label="Audio channels:", halign=Gtk.Align.START)
        self.audio_channels_entry = Gtk.Entry()
        self.audio_channels_entry.set_placeholder_text("Ex: 2 (stereo), 6 (5.1)")
        encoding_grid.attach(channels_label, 0, 7, 1, 1)
        encoding_grid.attach(self.audio_channels_entry, 1, 7, 1, 1)
        
        # Video resolution
        resolution_label = Gtk.Label(label="Video resolution:", halign=Gtk.Align.START)
        self.video_resolution_entry = Gtk.Entry()
        self.video_resolution_entry.set_placeholder_text("Ex: 1280x720, 1920x1080")
        encoding_grid.attach(resolution_label, 0, 8, 1, 1)
        encoding_grid.attach(self.video_resolution_entry, 1, 8, 1, 1)
        
        # Additional options
        options_label = Gtk.Label(label="Additional options:", halign=Gtk.Align.START)
        self.options_entry = Gtk.Entry()
        self.options_entry.set_placeholder_text("Ex: -ss 60 -t 30")
        encoding_grid.attach(options_label, 0, 9, 1, 1)
        encoding_grid.attach(self.options_entry, 1, 9, 1, 1)
        
        encoding_frame.add(encoding_grid)
        page.pack_start(encoding_frame, False, False, 0)
        
        # Advanced options
        advanced_frame = Gtk.Frame(label="Advanced Options")
        advanced_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        advanced_box.set_margin_start(10)
        advanced_box.set_margin_end(10)
        advanced_box.set_margin_top(10)
        advanced_box.set_margin_bottom(10)
        
        self.gpu_partial_check = Gtk.CheckButton(label="GPU partial mode (decode using CPU, encode using GPU)")
        self.force_software_check = Gtk.CheckButton(label="Force CPU decode and encode")
        self.force_copy_video_check = Gtk.CheckButton(label="Copy video without reencoding")
        self.only_extract_subtitles_check = Gtk.CheckButton(label="Only extract subtitles to .srt files")
        
        advanced_box.pack_start(self.gpu_partial_check, False, False, 0)
        advanced_box.pack_start(self.force_software_check, False, False, 0)
        advanced_box.pack_start(self.force_copy_video_check, False, False, 0)
        advanced_box.pack_start(self.only_extract_subtitles_check, False, False, 0)
        
        advanced_frame.add(advanced_box)
        page.pack_start(advanced_frame, False, False, 0)
        
        # Convert button
        convert_button = Gtk.Button(label="Convert File")
        convert_button.get_style_context().add_class("suggested-action")
        convert_button.connect("clicked", self.on_convert_big_button_clicked)
        button_box = Gtk.Box(spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.pack_start(convert_button, True, True, 0)
        page.pack_start(button_box, False, False, 10)
        
        # Add page to notebook
        label = Gtk.Label(label="Convert Single File")
        self.notebook.append_page(page, label)
    
    def create_mkv_mp4_all_page(self):
        # Create page for mkv-mp4-all.sh
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_margin_start(10)
        page.set_margin_end(10)
        page.set_margin_top(10)
        page.set_margin_bottom(10)
        
        # Settings
        settings_frame = Gtk.Frame(label="Batch Conversion Settings")
        settings_grid = Gtk.Grid()
        settings_grid.set_row_spacing(10)
        settings_grid.set_column_spacing(10)
        settings_grid.set_margin_start(10)
        settings_grid.set_margin_end(10)
        settings_grid.set_margin_top(10)
        settings_grid.set_margin_bottom(10)
        
        # Search directory
        dir_label = Gtk.Label(label="Search directory:", halign=Gtk.Align.START)
        self.search_dir_chooser = Gtk.FileChooserButton(title="Select Directory")
        self.search_dir_chooser.set_action(Gtk.FileChooserAction.SELECT_FOLDER)
        self.search_dir_chooser.set_current_folder(self.last_accessed_directory)
        self.search_dir_chooser.connect("file-set", self.on_directory_selected)
        settings_grid.attach(dir_label, 0, 0, 1, 1)
        settings_grid.attach(self.search_dir_chooser, 1, 0, 1, 1)
        
        # Simultaneous processes
        procs_label = Gtk.Label(label="Simultaneous processes:", halign=Gtk.Align.START)
        adjustment = Gtk.Adjustment(value=2, lower=1, upper=16, step_increment=1, page_increment=2)
        self.max_procs_spin = Gtk.SpinButton()
        self.max_procs_spin.set_adjustment(adjustment)
        self.max_procs_spin.set_numeric(True)
        settings_grid.attach(procs_label, 0, 1, 1, 1)
        settings_grid.attach(self.max_procs_spin, 1, 1, 1, 1)
        
        # Minimum size
        size_label = Gtk.Label(label="Minimum MP4 size (KB):", halign=Gtk.Align.START)
        adjustment = Gtk.Adjustment(value=1024, lower=1, upper=999999, step_increment=100, page_increment=1000)
        self.min_mp4_size_spin = Gtk.SpinButton()
        self.min_mp4_size_spin.set_adjustment(adjustment)
        self.min_mp4_size_spin.set_numeric(True)
        settings_grid.attach(size_label, 0, 2, 1, 1)
        settings_grid.attach(self.min_mp4_size_spin, 1, 2, 1, 1)
        
        # Log file
        log_label = Gtk.Label(label="Log file:", halign=Gtk.Align.START)
        self.log_file_entry = Gtk.Entry()
        self.log_file_entry.set_text("mkv-mp4-convert.log")
        settings_grid.attach(log_label, 0, 3, 1, 1)
        settings_grid.attach(self.log_file_entry, 1, 3, 1, 1)
        
        # Option to delete original files
        self.delete_batch_originals_check = Gtk.CheckButton(label="Delete original MKV files after successful conversion")
        settings_grid.attach(self.delete_batch_originals_check, 0, 4, 2, 1)
        
        settings_frame.add(settings_grid)
        page.pack_start(settings_frame, False, False, 0)
        
        # Information
        info_label = Gtk.Label()
        info_label.set_markup(
            "This mode will search for all MKV files in the selected directory and\n"
            "convert them to MP4. The original MKV file will only be removed if the MP4 is created\n"
            "successfully and has the defined minimum size."
        )
        info_label.set_justify(Gtk.Justification.CENTER)
        info_label.set_margin_top(20)
        info_label.set_margin_bottom(20)
        page.pack_start(info_label, False, False, 0)
        
        # Convert button
        convert_button = Gtk.Button(label="Convert All MKVs")
        convert_button.get_style_context().add_class("suggested-action")
        convert_button.connect("clicked", self.on_mkv_mp4_all_button_clicked)
        button_box = Gtk.Box(spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.pack_start(convert_button, True, True, 0)
        page.pack_start(button_box, False, False, 10)
        
        # Add page to notebook
        label = Gtk.Label(label="Convert Multiple Files")
        self.notebook.append_page(page, label)
    
    def create_about_page(self):
        # Create page for application information
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_margin_start(10)
        page.set_margin_end(10)
        page.set_margin_top(10)
        page.set_margin_bottom(10)
        
        # Title
        title_label = Gtk.Label()
        title_label.set_markup("<span size='x-large' weight='bold'>Comm Big Converter</span>")
        title_label.set_margin_top(20)
        title_label.set_margin_bottom(20)
        page.pack_start(title_label, False, False, 0)
        
        # Description
        desc_label = Gtk.Label()
        desc_label.set_markup(
            "<span size='large'>A graphical frontend for converting MKV videos to MP4</span>"
        )
        desc_label.set_margin_bottom(40)
        page.pack_start(desc_label, False, False, 0)
        
        # Developer information
        dev_frame = Gtk.Frame(label="Developer")
        dev_frame.set_margin_start(50)
        dev_frame.set_margin_end(50)
        
        dev_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        dev_box.set_margin_start(15)
        dev_box.set_margin_end(15)
        dev_box.set_margin_top(15)
        dev_box.set_margin_bottom(15)
        
        name_label = Gtk.Label()
        name_label.set_markup("<b>Tales A. Mendonça</b>")
        name_label.set_xalign(0)
        
        email_box = Gtk.Box(spacing=5)
        email_label = Gtk.Label()
        email_label.set_markup("<b>Email:</b> talesam@gmail.com")
        email_label.set_xalign(0)
        email_box.pack_start(email_label, True, True, 0)
        
        site_box = Gtk.Box(spacing=5)
        site_label = Gtk.Label()
        site_label.set_markup("<b>Site:</b> https://communitybig.org/")
        site_label.set_xalign(0)
        site_box.pack_start(site_label, True, True, 0)
        
        dev_box.pack_start(name_label, False, False, 0)
        dev_box.pack_start(email_box, False, False, 0)
        dev_box.pack_start(site_box, False, False, 0)
        
        dev_frame.add(dev_box)
        page.pack_start(dev_frame, False, False, 0)
        
        # White space
        spacer = Gtk.Box()
        page.pack_start(spacer, True, True, 0)
        
        # Application version
        version_label = Gtk.Label()
        version_label.set_markup("<span size='small'>Version 1.0.0</span>")
        version_label.set_margin_bottom(20)
        page.pack_end(version_label, False, False, 0)
        
        # Add page to notebook
        label = Gtk.Label(label="About")
        self.notebook.append_page(page, label)
    
    def on_folder_button_clicked(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Select the output folder",
            parent=self.window,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.output_folder_entry.set_text(dialog.get_filename())
        
        dialog.destroy()
    
    def on_convert_big_button_clicked(self, button):
        # Build command for convert-big.sh
        if not self.file_chooser.get_filename():
            self.show_error_dialog("Please select an input file.")
            return
            
        input_file = self.file_chooser.get_filename()
        
        # Check if the file is an MKV
        is_mkv = input_file.lower().endswith('.mkv')
        
        # Build environment variables
        env_vars = {}
        
        # Add selected options
        if self.gpu_combo.get_active_text() != "Auto-detect":
            env_vars["gpu"] = self.gpu_combo.get_active_text().lower()
        
        if self.output_file_entry.get_text():
            env_vars["output_file"] = self.output_file_entry.get_text()
            
        if self.output_folder_entry.get_text():
            env_vars["output_folder"] = self.output_folder_entry.get_text()
            
        if self.video_quality_combo.get_active_text() != "Default":
            env_vars["video_quality"] = self.video_quality_combo.get_active_text().lower()
            
        if self.video_encoder_combo.get_active_text() != "Default (h264)":
            env_vars["video_encoder"] = self.video_encoder_combo.get_active_text().split()[0].lower()
            
        if self.preset_combo.get_active_text() != "Default":
            env_vars["preset"] = self.preset_combo.get_active_text().lower()
            
        if self.subtitle_extract_combo.get_active_text() != "Default (extract)":
            env_vars["subtitle_extract"] = self.subtitle_extract_combo.get_active_text().lower().split()[0]
            
        if self.audio_handling_combo.get_active_text() != "Default (copy)":
            env_vars["audio_handling"] = self.audio_handling_combo.get_active_text().lower().split()[0]
            
        if self.audio_bitrate_entry.get_text():
            env_vars["audio_bitrate"] = self.audio_bitrate_entry.get_text()
            
        if self.audio_channels_entry.get_text():
            env_vars["audio_channels"] = self.audio_channels_entry.get_text()
            
        if self.video_resolution_entry.get_text():
            env_vars["video_resolution"] = self.video_resolution_entry.get_text()
            
        if self.options_entry.get_text():
            env_vars["options"] = self.options_entry.get_text()
            
        if self.gpu_partial_check.get_active():
            env_vars["gpu_partial"] = "1"
            
        if self.force_software_check.get_active():
            env_vars["force_software"] = "1"
            
        if self.force_copy_video_check.get_active():
            env_vars["force_copy_video"] = "1"
            
        if self.only_extract_subtitles_check.get_active():
            env_vars["only_extract_subtitles"] = "1"
        
        # Build command using absolute path to convert-big.sh
        cmd = []
        for key, value in env_vars.items():
            cmd.append(f"{key}={value}")
        
        cmd.extend([CONVERT_BIG_PATH, f"{input_file}"])
        
        # Construct command string for display
        cmd_str = " ".join([shlex.quote(arg) for arg in cmd])
        
        # Create and display progress dialog
        self.run_with_progress_dialog(cmd, f"{os.path.basename(input_file)}", input_file if is_mkv else None, self.delete_original_check.get_active())
    
    def on_mkv_mp4_all_button_clicked(self, button):
        # Build command for mkv-mp4-all.sh
        if not self.search_dir_chooser.get_filename():
            self.show_error_dialog("Please select a directory to search for MKV files.")
            return
            
        search_dir = self.search_dir_chooser.get_filename()
        max_procs = int(self.max_procs_spin.get_value())
        min_mp4_size = int(self.min_mp4_size_spin.get_value())
        log_file = self.log_file_entry.get_text()
        
        # Check if we want to delete the original files
        delete_originals = self.delete_batch_originals_check.get_active()
        
        # For mkv-mp4-all.sh, we don't pass delete_originals as a parameter
        # because the script already has this logic built in (it will delete the original MKVs after successful conversion)
        # However, if the user doesn't check the option, we add --nodelete
        
        # Build command using absolute path to mkv-mp4-all.sh
        cmd = [MKV_MP4_ALL_PATH, 
               "--dir", search_dir, 
               "--procs", str(max_procs), 
               "--size", str(min_mp4_size), 
               "--log", log_file]
        
        if not delete_originals:
            cmd.append("--nodelete")
        
        # Construct command string for display
        cmd_str = " ".join([shlex.quote(arg) for arg in cmd])
        
        # Create and display progress dialog
        self.run_with_progress_dialog(cmd, f"Batch conversion ({os.path.basename(search_dir)})")
    
    def run_with_progress_dialog(self, cmd, title_suffix, input_file=None, delete_original=False):
        cmd_str = " ".join([shlex.quote(arg) for arg in cmd])
        progress_dialog = ProgressDialog(self.window, "Converting...", title_suffix, input_file)
        
        # Configure option to delete original file
        if input_file:
            progress_dialog.set_delete_original(delete_original)
        
        # Increment counter of active conversions
        self.conversions_running += 1
        
        # Start process
        try:
            # Use PIPE for stdout and stderr to monitor progress
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            
            # Set the process in the progress dialog
            progress_dialog.set_process(process)
            
            # Start thread to monitor progress
            monitor_thread = threading.Thread(
                target=self.monitor_progress,
                args=(process, progress_dialog)
            )
            monitor_thread.daemon = True
            monitor_thread.start()
            
            # Show dialog and wait for response
            response = progress_dialog.run()
            
            # Close dialog
            progress_dialog.destroy()
            
        except Exception as e:
            self.show_error_dialog(f"Error starting conversion: {e}")
            progress_dialog.destroy()
            self.conversions_running -= 1
    
    def monitor_progress(self, process, progress_dialog):
        # Patterns to extract progress from ffmpeg
        time_pattern = re.compile(r'time=(\d+:\d+:\d+.\d+)')
        duration_pattern = re.compile(r'Duration: (\d+:\d+:\d+.\d+)')
        frame_pattern = re.compile(r'frame=\s*(\d+)')
        fps_pattern = re.compile(r'fps=\s*(\d+)')
        output_file_pattern = re.compile(r'Output #0.*?\'(.*?)\'')
        
        duration_secs = None
        current_time_secs = 0
        frame_count = 0
        estimated_frames = 0
        output_file = None
        
        # Read output line by line
        for line in iter(process.stderr.readline, ""):
            # Capture output file if available
            if "Output #0" in line and "'" in line:
                output_match = output_file_pattern.search(line)
                if output_match:
                    output_file = output_match.group(1)
            
            # Update user interface from main thread
            if "Duration" in line and not duration_secs:
                duration_match = duration_pattern.search(line)
                if duration_match:
                    duration_str = duration_match.group(1)
                    time_parts = duration_str.split(":")
                    h = float(time_parts[0])
                    m = float(time_parts[1])
                    s = float(time_parts[2])  # This already includes milliseconds as decimal part
                    duration_secs = h * 3600 + m * 60 + s
                    GLib.idle_add(progress_dialog.update_status, f"Total duration: {duration_str}")
            
            if "time=" in line:
                time_match = time_pattern.search(line)
                if time_match and duration_secs:
                    time_str = time_match.group(1)
                    time_parts = time_str.split(":")
                    h = float(time_parts[0])
                    m = float(time_parts[1])
                    s = float(time_parts[2])  # This already includes milliseconds
                    current_time_secs = h * 3600 + m * 60 + s
                    progress = min(current_time_secs / duration_secs, 1.0)
                    
                    # Update progress bar
                    GLib.idle_add(progress_dialog.update_progress, progress)
                    
                    # Update status
                    remaining_secs = max(0, duration_secs - current_time_secs)
                    remaining_mins = int(remaining_secs / 60)
                    remaining_secs = int(remaining_secs % 60)
                    GLib.idle_add(
                        progress_dialog.update_status, 
                        f"Estimated time remaining: {remaining_mins:02d}:{remaining_secs:02d}"
                    )
            
            # Extract frame and FPS information for conversions without time
            if not duration_secs and "frame=" in line:
                frame_match = frame_pattern.search(line)
                fps_match = fps_pattern.search(line)
                
                if frame_match:
                    new_frame_count = int(frame_match.group(1))
                    if new_frame_count > frame_count:
                        frame_count = new_frame_count
                        
                        # If we don't have an estimated total, let's assume a large value
                        if estimated_frames == 0:
                            estimated_frames = 10000  # Arbitrary value
                        
                        progress = min(frame_count / estimated_frames, 0.99)  # Never reach 100% until finished
                        GLib.idle_add(progress_dialog.update_progress, progress)
                        GLib.idle_add(progress_dialog.update_status, f"Frames processed: {frame_count}")
        
        # Process finished
        return_code = process.wait()
        
        # Update user interface from main thread
        if return_code == 0:
            # Mark as successful
            GLib.idle_add(progress_dialog.mark_success)
            
            # Update progress bar
            GLib.idle_add(progress_dialog.update_progress, 1.0, "Completed!")
            GLib.idle_add(progress_dialog.update_status, "Conversion completed successfully!")
            
            # Check if we should delete the original file
            if progress_dialog.delete_original and progress_dialog.input_file:
                input_file = progress_dialog.input_file
                
                # Check if the output file exists and has a reasonable size
                if output_file and os.path.exists(output_file):
                    input_size = os.path.getsize(input_file)
                    output_size = os.path.getsize(output_file)
                    
                    # Consider the conversion successful if the MP4 file exists with reasonable size (at least 1MB)
                    if output_size > 1024 * 1024:  # 1MB in bytes
                        try:
                            os.remove(input_file)
                            GLib.idle_add(
                                lambda: self.show_info_dialog_and_close_progress(
                                    f"✅ Conversion completed successfully!\n\nThe original file <b>{os.path.basename(input_file)}</b> was deleted.",
                                    progress_dialog
                                )
                            )
                        except Exception as e:
                            GLib.idle_add(
                                lambda: self.show_info_dialog_and_close_progress(
                                    f"✅ Conversion completed successfully!\n\nCould not delete the original file: {e}",
                                    progress_dialog
                                )
                            )
                    else:
                        GLib.idle_add(
                            lambda: self.show_info_dialog_and_close_progress(
                                f"✅ Conversion completed successfully!\n\nThe original file was not deleted because the converted file size looks suspicious.",
                                progress_dialog
                            )
                        )
                else:
                    GLib.idle_add(
                        lambda: self.show_info_dialog_and_close_progress(
                            f"✅ Conversion completed successfully!",
                            progress_dialog
                        )
                    )
            else:
                GLib.idle_add(
                    lambda: self.show_info_dialog_and_close_progress(
                        f"✅ Conversion completed successfully!",
                        progress_dialog
                    )
                )
        else:
            GLib.idle_add(progress_dialog.update_progress, 0.0, "Error!")
            GLib.idle_add(progress_dialog.update_status, f"Conversion failed with code {return_code}")
            GLib.idle_add(
                lambda: self.show_error_dialog_and_close_progress(
                    f"❌ The conversion failed with error code {return_code}.\n\nCheck the log for more details.",
                    progress_dialog
                )
            )
        
        # Disable cancel button
        GLib.idle_add(progress_dialog.cancel_button.set_sensitive, False)
        
        # Update active conversions counter
        self.conversions_running -= 1
    
    def on_file_selected(self, button):
        """Updates the last accessed directory when a file is selected"""
        selected_file = button.get_filename()
        if selected_file:
            self.last_accessed_directory = os.path.dirname(selected_file)
            
            # Also update the directory for the other file chooser
            if hasattr(self, 'search_dir_chooser'):
                self.search_dir_chooser.set_current_folder(self.last_accessed_directory)

    def on_directory_selected(self, button):
        """Updates the last accessed directory when a directory is selected"""
        selected_dir = button.get_filename()
        if selected_dir and os.path.isdir(selected_dir):
            self.last_accessed_directory = selected_dir
            
            # Also update the directory for the other file chooser
            if hasattr(self, 'file_chooser'):
                self.file_chooser.set_current_folder(self.last_accessed_directory)
    
    def show_error_dialog(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message
        )
        dialog.run()
        dialog.destroy()
    
    def show_info_dialog_and_close_progress(self, message, progress_dialog):
        """Shows an information dialog and closes the progress dialog"""
        # First close the progress dialog
        progress_dialog.destroy()
        
        # Then show the information message
        self.show_info_dialog(message)
    
    def show_error_dialog_and_close_progress(self, message, progress_dialog):
        """Shows an error dialog and closes the progress dialog"""
        # First close the progress dialog
        progress_dialog.destroy()
        
        # Then show the error message
        self.show_error_dialog(message)
    
    def show_info_dialog(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=""
        )
        # Configure markup as true
        dialog.set_markup(message)
        dialog.run()
        dialog.destroy()

def main():
    app = VideoConverterApp()
    Gtk.main()

if __name__ == "__main__":
    main()