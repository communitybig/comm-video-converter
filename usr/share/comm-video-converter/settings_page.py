import os
from gi.repository import Gtk, Adw
from constants import APP_DEVELOPERS, APP_WEBSITES

# Setup translation
import gettext
_ = gettext.gettext  # Will use the already initialized translation

class SettingsPage:
    def __init__(self, app):
        self.app = app
        self.settings_manager = app.settings_manager
        self.create_page()
    
    def get_page(self):
        return self.page
    
    def create_page(self):
        # Create settings page
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Add ScrolledWindow to enable scrolling when window is small
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_hexpand(True)
        scrolled_window.set_vexpand(True)
        self.page.append(scrolled_window)
        
        # Container for scrollable content - center vertically
        scrollable_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scrollable_content.set_valign(Gtk.Align.CENTER)  # Center content vertically
        scrollable_content.set_vexpand(True)
        scrolled_window.set_child(scrollable_content)
        
        # Use Adw.Clamp for consistent width
        clamp = Adw.Clamp()
        clamp.set_maximum_size(800)
        clamp.set_tightening_threshold(600)
        scrollable_content.append(clamp)
        
        # Main content box
        main_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_content.set_spacing(24)
        main_content.set_margin_start(12)
        main_content.set_margin_end(12)
        main_content.set_margin_top(24)
        main_content.set_margin_bottom(24)
        clamp.set_child(main_content)
        
        # Encoding settings section
        self.create_encoding_settings(main_content)
        
        # Audio settings section
        self.create_audio_settings(main_content)
        
        # Video settings section
        self.create_video_settings(main_content)
        
        # General options section
        self.create_general_options(main_content)
        
        # About section
        self.create_about_section(main_content)
        
        # Connect settings signals
        self.connect_setting_signals()
        
        # Load initial values
        self.load_settings()
    
    def create_encoding_settings(self, main_content):
        encoding_group = Adw.PreferencesGroup(title=_("Encoding Settings"))
        
        # GPU selection
        gpu_model = Gtk.StringList()
        for option in [_("Auto-detect"), _("nvidia"), _("amd"), _("intel"), _("software")]:
            gpu_model.append(option)
        self.gpu_combo = Adw.ComboRow(title=_("GPU"))
        self.gpu_combo.set_subtitle(_("Select hardware acceleration"))
        self.gpu_combo.set_model(gpu_model)
        self.gpu_combo.set_selected(0)
        encoding_group.add(self.gpu_combo)
        
        # Conversion mode switches
        self.gpu_partial_check = Adw.SwitchRow(title=_("GPU partial mode"))
        self.gpu_partial_check.set_subtitle(_("Decode using CPU, encode using GPU"))
        encoding_group.add(self.gpu_partial_check)
        
        # Video quality
        quality_model = Gtk.StringList()
        for option in [_("Default"), _("veryhigh"), _("high"), _("medium"), _("low"), _("verylow")]:
            quality_model.append(option)
        self.video_quality_combo = Adw.ComboRow(title=_("Video quality"))
        self.video_quality_combo.set_subtitle(_("Higher quality needs more processing power"))
        self.video_quality_combo.set_model(quality_model)
        self.video_quality_combo.set_selected(0)
        encoding_group.add(self.video_quality_combo)
        
        # Video codec
        codec_model = Gtk.StringList()
        for option in [_("Default (h264)"), _("h264 (MP4)"), _("h265 (HEVC)"), _("av1 (AV1)"), _("vp9 (VP9)")]:
            codec_model.append(option)
        self.video_encoder_combo = Adw.ComboRow(title=_("Video codec"))
        self.video_encoder_combo.set_subtitle(_("Select encoding format"))
        self.video_encoder_combo.set_model(codec_model)
        self.video_encoder_combo.set_selected(0)
        encoding_group.add(self.video_encoder_combo)
        
        # Video resolution combo with common values
        resolution_model = Gtk.StringList()
        self.resolution_values = [
            _("Default"),
            "3840x2160",  # 4K UHD
            "2560x1440",  # 2K QHD
            "1920x1080",  # 1080p Full HD
            "1280x720",   # 720p HD
            "854x480",    # 480p SD
            _("Custom")
        ]
        for option in self.resolution_values:
            resolution_model.append(option)
        
        self.video_resolution_combo = Adw.ComboRow(title=_("Video resolution"))
        self.video_resolution_combo.set_subtitle(_("Select output resolution"))
        self.video_resolution_combo.set_model(resolution_model)
        self.video_resolution_combo.set_selected(0)  # Default
        
        # Add custom entry for resolution that shows when "Custom" is selected
        self.custom_resolution_row = Adw.EntryRow(title=_("Custom resolution"))
        self.custom_resolution_row.set_tooltip_text(_("Ex: 1280x720, 1920x1080"))
        self.custom_resolution_row.set_visible(False)  # Initially hidden
        
        # Connect combo box to show/hide custom entry
        self.video_resolution_combo.connect("notify::selected", self.on_resolution_combo_changed)
        
        encoding_group.add(self.video_resolution_combo)
        encoding_group.add(self.custom_resolution_row)
        
        # Preset
        preset_model = Gtk.StringList()
        for option in [_("Default"), _("ultrafast"), _("veryfast"), _("faster"), _("medium"), _("slow"), _("veryslow")]:
            preset_model.append(option)
        self.preset_combo = Adw.ComboRow(title=_("Compression preset"))
        self.preset_combo.set_subtitle(_("Slower presets provide better compression"))
        self.preset_combo.set_model(preset_model)
        self.preset_combo.set_selected(0)
        encoding_group.add(self.preset_combo)
        
        # Subtitles
        subtitle_model = Gtk.StringList()
        for option in [_("Default (extract)"), _("extract (SRT)"), _("embedded"), _("none")]:
            subtitle_model.append(option)
        self.subtitle_extract_combo = Adw.ComboRow(title=_("Subtitle handling"))
        self.subtitle_extract_combo.set_model(subtitle_model)
        self.subtitle_extract_combo.set_selected(0)
        encoding_group.add(self.subtitle_extract_combo)
        
        main_content.append(encoding_group)
    
    def create_audio_settings(self, main_content):
        audio_group = Adw.PreferencesGroup(title=_("Audio Settings"))
        
        # Audio bitrate combo with common values
        bitrate_model = Gtk.StringList()
        self.bitrate_values = [
            _("Default"),
            "96k",
            "128k",
            "192k", 
            "256k",
            "320k",
            _("Custom")
        ]
        for option in self.bitrate_values:
            bitrate_model.append(option)
        
        # Create a box to hold both the combo and entry
        bitrate_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        self.audio_bitrate_combo = Adw.ComboRow(title=_("Audio bitrate"))
        self.audio_bitrate_combo.set_subtitle(_("Select common bitrate or enter custom value"))
        self.audio_bitrate_combo.set_model(bitrate_model)
        self.audio_bitrate_combo.set_selected(0)  # Default
        
        # Add custom entry for bitrate that shows when "Custom" is selected
        self.custom_bitrate_row = Adw.EntryRow(title=_("Custom bitrate"))
        self.custom_bitrate_row.set_tooltip_text(_("Ex: 128k, 192k, 256k"))
        self.custom_bitrate_row.set_visible(False)  # Initially hidden
        
        # Connect combo box to show/hide custom entry
        self.audio_bitrate_combo.connect("notify::selected", self.on_bitrate_combo_changed)
        
        audio_group.add(self.audio_bitrate_combo)
        audio_group.add(self.custom_bitrate_row)
        
        # Audio channels combo with common values
        channels_model = Gtk.StringList()
        self.channels_values = [
            _("Default"),
            "1",  # Mono
            "2",  # Stereo
            "6",  # 5.1
            _("Custom")
        ]
        for option in self.channels_values:
            channels_model.append(option)
        
        self.audio_channels_combo = Adw.ComboRow(title=_("Audio channels"))
        self.audio_channels_combo.set_subtitle(_("Select common channel configuration"))
        self.audio_channels_combo.set_model(channels_model)
        self.audio_channels_combo.set_selected(0)  # Default
        
        # Add custom entry for channels that shows when "Custom" is selected
        self.custom_channels_row = Adw.EntryRow(title=_("Custom channels"))
        self.custom_channels_row.set_tooltip_text(_("Ex: 2 (stereo), 6 (5.1)"))
        self.custom_channels_row.set_visible(False)  # Initially hidden
        
        # Connect combo box to show/hide custom entry
        self.audio_channels_combo.connect("notify::selected", self.on_channels_combo_changed)
        
        audio_group.add(self.audio_channels_combo)
        audio_group.add(self.custom_channels_row)
        
        # Audio handling
        audio_model = Gtk.StringList()
        for option in [_("Default (copy)"), _("copy"), _("reencode"), _("none")]:
            audio_model.append(option)
        self.audio_handling_combo = Adw.ComboRow(title=_("Audio handling"))
        self.audio_handling_combo.set_model(audio_model)
        self.audio_handling_combo.set_selected(0)
        audio_group.add(self.audio_handling_combo)
        
        main_content.append(audio_group)
    
    def on_bitrate_combo_changed(self, combo, param):
        selected = combo.get_selected()
        is_custom = selected == len(self.bitrate_values) - 1  # Check if "Custom" is selected
        self.custom_bitrate_row.set_visible(is_custom)
        
        # Update the setting unless it's custom
        if not is_custom and selected > 0:  # Not default and not custom
            self.settings_manager.save_setting("audio-bitrate", self.bitrate_values[selected])
        elif not is_custom and selected == 0:  # Default selected
            self.settings_manager.save_setting("audio-bitrate", "")
    
    def on_channels_combo_changed(self, combo, param):
        selected = combo.get_selected()
        is_custom = selected == len(self.channels_values) - 1  # Check if "Custom" is selected
        self.custom_channels_row.set_visible(is_custom)
        
        # Update the setting unless it's custom
        if not is_custom and selected > 0:  # Not default and not custom
            self.settings_manager.save_setting("audio-channels", self.channels_values[selected])
        elif not is_custom and selected == 0:  # Default selected
            self.settings_manager.save_setting("audio-channels", "")
    
    def on_resolution_combo_changed(self, combo, param):
        selected = combo.get_selected()
        is_custom = selected == len(self.resolution_values) - 1  # Check if "Custom" is selected
        self.custom_resolution_row.set_visible(is_custom)
        
        # Update the setting unless it's custom
        if not is_custom and selected > 0:  # Not default and not custom
            self.settings_manager.save_setting("video-resolution", self.resolution_values[selected])
        elif not is_custom and selected == 0:  # Default selected
            self.settings_manager.save_setting("video-resolution", "")
    
    def create_video_settings(self, main_content):
        # This section is now empty since we moved the video resolution to encoding settings
        # We can either leave it empty or remove it completely
        pass
    
    def create_general_options(self, main_content):
        options_group = Adw.PreferencesGroup(title=_("General Options"))
        
        # Additional options - moved from Video settings to General
        self.options_entry = Adw.EntryRow(title=_("Additional FFmpeg options"))
        self.options_entry.set_tooltip_text(_("Ex: -ss 60 -t 30"))
        options_group.add(self.options_entry)
        
        self.force_copy_video_check = Adw.SwitchRow(title=_("Copy video without reencoding"))
        self.force_copy_video_check.set_subtitle(_("Faster but less compatible"))
        options_group.add(self.force_copy_video_check)
        
        self.only_extract_subtitles_check = Adw.SwitchRow(title=_("Only extract subtitles"))
        self.only_extract_subtitles_check.set_subtitle(_("Extract subtitles to .srt files"))
        options_group.add(self.only_extract_subtitles_check)
        
        main_content.append(options_group)
    
    def create_about_section(self, main_content):
        from constants import APP_VERSION, APP_DEVELOPERS, APP_WEBSITES
        
        about_group = Adw.PreferencesGroup(title=_("About"))
        
        # App info in a compact format
        app_info_row = Adw.ActionRow(title=_("Comm Video Converter"))
        app_info_row.set_subtitle(_("A graphical frontend for converting MKV videos to MP4"))
        
        # App icon
        app_icon = Gtk.Image.new_from_icon_name("video-x-generic")
        app_icon.set_pixel_size(32)
        app_info_row.add_prefix(app_icon)
        
        # Version label
        version_label = Gtk.Label(label=f"v{APP_VERSION}")
        app_info_row.add_suffix(version_label)
        
        about_group.add(app_info_row)
        
        # Developers header
        devs_header = Adw.ActionRow(title=_("Developers"))
        about_group.add(devs_header)
        
        # Create a row for each developer
        for name in APP_DEVELOPERS:
            dev_row = Adw.ActionRow()
            dev_row.set_subtitle(name)
            dev_row.set_margin_start(24)  # Indent for better hierarchy
            about_group.add(dev_row)
        
        # Websites header
        sites_header = Adw.ActionRow(title=_("Websites"))
        about_group.add(sites_header)
        
        # Create a row for each website
        for site in APP_WEBSITES:
            site_row = Adw.ActionRow()
            site_row.set_subtitle(site)
            site_row.set_margin_start(24)  # Indent for better hierarchy
            about_group.add(site_row)
        
        main_content.append(about_group)
    
    def connect_setting_signals(self):
        """Connect signals for saving settings"""
        # Encoding settings
        self.gpu_combo.connect("notify::selected", lambda w, p: self.settings_manager.save_setting("gpu-selection", w.get_selected()))
        self.video_quality_combo.connect("notify::selected", lambda w, p: self.settings_manager.save_setting("video-quality", w.get_selected()))
        self.video_encoder_combo.connect("notify::selected", lambda w, p: self.settings_manager.save_setting("video-codec", w.get_selected()))
        self.preset_combo.connect("notify::selected", lambda w, p: self.settings_manager.save_setting("preset", w.get_selected()))
        self.subtitle_extract_combo.connect("notify::selected", lambda w, p: self.settings_manager.save_setting("subtitle-extract", w.get_selected()))
        self.audio_handling_combo.connect("notify::selected", lambda w, p: self.settings_manager.save_setting("audio-handling", w.get_selected()))
        
        # Audio settings - only connect custom entries, combos are handled by their own callbacks
        self.custom_bitrate_row.connect("changed", lambda w: self.settings_manager.save_setting("audio-bitrate", w.get_text()))
        self.custom_channels_row.connect("changed", lambda w: self.settings_manager.save_setting("audio-channels", w.get_text()))
        
        # Video resolution custom entry - combo is handled by its own callback
        self.custom_resolution_row.connect("changed", lambda w: self.settings_manager.save_setting("video-resolution", w.get_text()))
        
        # General options
        self.options_entry.connect("changed", lambda w: self.settings_manager.save_setting("additional-options", w.get_text()))
        self.gpu_partial_check.connect("notify::active", lambda w, p: self.settings_manager.save_setting("gpu-partial", w.get_active()))
        self.force_copy_video_check.connect("notify::active", lambda w, p: self.settings_manager.save_setting("force-copy-video", w.get_active()))
        self.only_extract_subtitles_check.connect("notify::active", lambda w, p: self.settings_manager.save_setting("only-extract-subtitles", w.get_active()))
    
    def load_settings(self):
        """Load all settings and update UI"""
        # Encoding settings
        self.gpu_combo.set_selected(self.settings_manager.load_setting("gpu-selection", 0))
        self.video_quality_combo.set_selected(self.settings_manager.load_setting("video-quality", 0))
        self.video_encoder_combo.set_selected(self.settings_manager.load_setting("video-codec", 0))
        self.preset_combo.set_selected(self.settings_manager.load_setting("preset", 0))
        self.subtitle_extract_combo.set_selected(self.settings_manager.load_setting("subtitle-extract", 0))
        self.audio_handling_combo.set_selected(self.settings_manager.load_setting("audio-handling", 0))
        
        # Audio settings with dropdown handling
        audio_bitrate = self.settings_manager.load_setting("audio-bitrate", "")
        audio_channels = self.settings_manager.load_setting("audio-channels", "")
        
        # Handle bitrate setting
        if not audio_bitrate:
            self.audio_bitrate_combo.set_selected(0)  # Default
        elif audio_bitrate in self.bitrate_values:
            self.audio_bitrate_combo.set_selected(self.bitrate_values.index(audio_bitrate))
        else:
            # Custom value
            self.audio_bitrate_combo.set_selected(len(self.bitrate_values) - 1)  # Custom option
            self.custom_bitrate_row.set_text(audio_bitrate)
            self.custom_bitrate_row.set_visible(True)
        
        # Handle channels setting
        if not audio_channels:
            self.audio_channels_combo.set_selected(0)  # Default
        elif audio_channels in self.channels_values:
            self.audio_channels_combo.set_selected(self.channels_values.index(audio_channels))
        else:
            # Custom value
            self.audio_channels_combo.set_selected(len(self.channels_values) - 1)  # Custom option
            self.custom_channels_row.set_text(audio_channels)
            self.custom_channels_row.set_visible(True)
        
        # Video resolution with dropdown handling
        video_resolution = self.settings_manager.load_setting("video-resolution", "")
        
        # Handle video resolution setting
        if not video_resolution:
            self.video_resolution_combo.set_selected(0)  # Default
        elif video_resolution in self.resolution_values:
            self.video_resolution_combo.set_selected(self.resolution_values.index(video_resolution))
        else:
            # Custom value
            self.video_resolution_combo.set_selected(len(self.resolution_values) - 1)  # Custom option
            self.custom_resolution_row.set_text(video_resolution)
            self.custom_resolution_row.set_visible(True)
        
        # General options
        self.options_entry.set_text(self.settings_manager.load_setting("additional-options", ""))
        self.gpu_partial_check.set_active(self.settings_manager.load_setting("gpu-partial", False))
        self.force_copy_video_check.set_active(self.settings_manager.load_setting("force-copy-video", False))
        self.only_extract_subtitles_check.set_active(self.settings_manager.load_setting("only-extract-subtitles", False))
        
    def apply_settings_to_env(self, env_vars):
        """Apply current settings to environment variables for conversion process"""
        # GPU Selection
        gpu_index = self.gpu_combo.get_selected()
        if gpu_index > 0:  # If not "Auto-detect"
            from constants import GPU_OPTIONS
            env_vars["gpu"] = GPU_OPTIONS[gpu_index].lower()
        
        # Video quality
        quality_index = self.video_quality_combo.get_selected()
        if quality_index > 0:  # If not "Default"
            from constants import VIDEO_QUALITY_OPTIONS
            env_vars["video_quality"] = VIDEO_QUALITY_OPTIONS[quality_index].lower()
        
        # Video codec
        codec_index = self.video_encoder_combo.get_selected()
        if codec_index > 0:  # If not "Default"
            # Extract just the codec name without the description
            codec = self.video_encoder_combo.get_selected_item().get_string().split()[0].lower()
            env_vars["video_encoder"] = codec
        
        # Video resolution
        resolution_index = self.video_resolution_combo.get_selected()
        if resolution_index > 0:  # If not "Default"
            if resolution_index == len(self.resolution_values) - 1:  # Custom
                # Use the custom value if it's set
                if self.custom_resolution_row.get_text():
                    env_vars["video_resolution"] = self.custom_resolution_row.get_text()
            else:
                env_vars["video_resolution"] = self.resolution_values[resolution_index]
        
        # Preset
        preset_index = self.preset_combo.get_selected()
        if preset_index > 0:  # If not "Default"
            from constants import PRESET_OPTIONS
            env_vars["preset"] = PRESET_OPTIONS[preset_index].lower()
        
        # Subtitle handling
        subtitle_index = self.subtitle_extract_combo.get_selected()
        if subtitle_index > 0:  # If not "Default"
            from constants import SUBTITLE_OPTIONS
            # Extract just the first word
            subtitle_option = SUBTITLE_OPTIONS[subtitle_index].split()[0].lower()
            env_vars["subtitle_extract"] = subtitle_option
        
        # Audio handling
        audio_index = self.audio_handling_combo.get_selected()
        if audio_index > 0:  # If not "Default"
            from constants import AUDIO_OPTIONS
            # Extract just the first word
            audio_option = AUDIO_OPTIONS[audio_index].split()[0].lower()
            env_vars["audio_handling"] = audio_option
        
        # Audio bitrate
        bitrate_index = self.audio_bitrate_combo.get_selected()
        if bitrate_index > 0:  # If not "Default"
            if bitrate_index == len(self.bitrate_values) - 1:  # Custom
                if self.custom_bitrate_row.get_text():
                    env_vars["audio_bitrate"] = self.custom_bitrate_row.get_text()
            else:
                env_vars["audio_bitrate"] = self.bitrate_values[bitrate_index]
        
        # Audio channels
        channels_index = self.audio_channels_combo.get_selected()
        if channels_index > 0:  # If not "Default"
            if channels_index == len(self.channels_values) - 1:  # Custom
                if self.custom_channels_row.get_text():
                    env_vars["audio_channels"] = self.custom_channels_row.get_text()
            else:
                env_vars["audio_channels"] = self.channels_values[channels_index]
        
        # Additional options
        if self.options_entry.get_text():
            env_vars["options"] = self.options_entry.get_text()
        
        # Boolean options
        if self.gpu_partial_check.get_active():
            env_vars["gpu_partial"] = "1"
        
        if self.force_copy_video_check.get_active():
            env_vars["force_copy_video"] = "1"
        
        if self.only_extract_subtitles_check.get_active():
            env_vars["only_extract_subtitles"] = "1"
        
        return env_vars
