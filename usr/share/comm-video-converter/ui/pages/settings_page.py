import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from constants import (
    GPU_OPTIONS,
    VIDEO_QUALITY_OPTIONS,
    VIDEO_CODEC_OPTIONS,
    PRESET_OPTIONS,
    SUBTITLE_OPTIONS,
    AUDIO_OPTIONS,
)

# Setup translation
import gettext

_ = gettext.gettext


class SettingsPage:
    """
    Settings page for application configuration.
    Adapted from the original settings dialog.
    """

    def __init__(self, app):
        self.app = app
        self.settings_manager = app.settings_manager

        # Create the settings page
        self.page = self._create_page()

        # Connect settings signals
        self._connect_setting_signals()

        # Load initial values
        self._load_settings()

    def get_page(self):
        """Return the settings page widget"""
        return self.page

    def _create_page(self):
        # Create page for settings
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Add ScrolledWindow to enable scrolling when window is small
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_hexpand(True)
        scrolled_window.set_vexpand(True)
        page.append(scrolled_window)

        # Container for scrollable content
        scrollable_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
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

        # Create settings groups
        self._create_encoding_settings(main_content)
        self._create_audio_settings(main_content)
        self._create_general_options(main_content)

        return page

    def _create_encoding_settings(self, main_content):
        encoding_group = Adw.PreferencesGroup(title=_("Encoding Settings"))

        # GPU selection
        gpu_model = Gtk.StringList()
        for option in GPU_OPTIONS:
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
        for option in VIDEO_QUALITY_OPTIONS:
            quality_model.append(option)
        self.video_quality_combo = Adw.ComboRow(title=_("Video quality"))
        self.video_quality_combo.set_subtitle(
            _("Higher quality needs more processing power")
        )
        self.video_quality_combo.set_model(quality_model)
        self.video_quality_combo.set_selected(0)
        encoding_group.add(self.video_quality_combo)

        # Video codec
        codec_model = Gtk.StringList()
        for option in VIDEO_CODEC_OPTIONS:
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
            "1280x720",  # 720p HD
            "854x480",  # 480p SD
            _("Custom"),
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
        self.video_resolution_combo.connect(
            "notify::selected", self._on_resolution_combo_changed
        )

        encoding_group.add(self.video_resolution_combo)
        encoding_group.add(self.custom_resolution_row)

        # Preset
        preset_model = Gtk.StringList()
        for option in PRESET_OPTIONS:
            preset_model.append(option)
        self.preset_combo = Adw.ComboRow(title=_("Compression preset"))
        self.preset_combo.set_subtitle(_("Slower presets provide better compression"))
        self.preset_combo.set_model(preset_model)
        self.preset_combo.set_selected(0)
        encoding_group.add(self.preset_combo)

        # Subtitles
        subtitle_model = Gtk.StringList()
        for option in SUBTITLE_OPTIONS:
            subtitle_model.append(option)
        self.subtitle_extract_combo = Adw.ComboRow(title=_("Subtitle handling"))
        self.subtitle_extract_combo.set_model(subtitle_model)
        self.subtitle_extract_combo.set_selected(0)
        encoding_group.add(self.subtitle_extract_combo)

        main_content.append(encoding_group)

    def _create_audio_settings(self, main_content):
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
            _("Custom"),
        ]
        for option in self.bitrate_values:
            bitrate_model.append(option)

        self.audio_bitrate_combo = Adw.ComboRow(title=_("Audio bitrate"))
        self.audio_bitrate_combo.set_subtitle(
            _("Select common bitrate or enter custom value")
        )
        self.audio_bitrate_combo.set_model(bitrate_model)
        self.audio_bitrate_combo.set_selected(0)  # Default

        # Add custom entry for bitrate that shows when "Custom" is selected
        self.custom_bitrate_row = Adw.EntryRow(title=_("Custom bitrate"))
        self.custom_bitrate_row.set_tooltip_text(_("Ex: 128k, 192k, 256k"))
        self.custom_bitrate_row.set_visible(False)  # Initially hidden

        # Connect combo box to show/hide custom entry
        self.audio_bitrate_combo.connect(
            "notify::selected", self._on_bitrate_combo_changed
        )

        audio_group.add(self.audio_bitrate_combo)
        audio_group.add(self.custom_bitrate_row)

        # Audio channels combo with common values
        channels_model = Gtk.StringList()
        self.channels_values = [
            _("Default"),
            "1",  # Mono
            "2",  # Stereo
            "6",  # 5.1
            _("Custom"),
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
        self.audio_channels_combo.connect(
            "notify::selected", self._on_channels_combo_changed
        )

        audio_group.add(self.audio_channels_combo)
        audio_group.add(self.custom_channels_row)

        # Audio handling
        audio_model = Gtk.StringList()
        for option in AUDIO_OPTIONS:
            audio_model.append(option)
        self.audio_handling_combo = Adw.ComboRow(title=_("Audio handling"))
        self.audio_handling_combo.set_model(audio_model)
        self.audio_handling_combo.set_selected(0)
        audio_group.add(self.audio_handling_combo)

        main_content.append(audio_group)

    def _create_general_options(self, main_content):
        options_group = Adw.PreferencesGroup(title=_("General Options"))

        # Additional options
        self.options_entry = Adw.EntryRow(title=_("Additional FFmpeg options"))
        self.options_entry.set_tooltip_text(_("Ex: -ss 60 -t 30"))
        options_group.add(self.options_entry)

        self.force_copy_video_check = Adw.SwitchRow(
            title=_("Copy video without reencoding")
        )
        self.force_copy_video_check.set_subtitle(_("Faster but less compatible"))
        options_group.add(self.force_copy_video_check)

        self.only_extract_subtitles_check = Adw.SwitchRow(
            title=_("Only extract subtitles")
        )
        self.only_extract_subtitles_check.set_subtitle(
            _("Extract subtitles to .srt files")
        )
        options_group.add(self.only_extract_subtitles_check)

        main_content.append(options_group)

    def _on_bitrate_combo_changed(self, combo, param):
        selected = combo.get_selected()
        is_custom = (
            selected == len(self.bitrate_values) - 1
        )  # Check if "Custom" is selected
        self.custom_bitrate_row.set_visible(is_custom)

        # Update the setting unless it's custom
        if not is_custom and selected > 0:  # Not default and not custom
            self.settings_manager.save_setting(
                "audio-bitrate", self.bitrate_values[selected]
            )
        elif not is_custom and selected == 0:  # Default selected
            self.settings_manager.save_setting("audio-bitrate", "")

    def _on_channels_combo_changed(self, combo, param):
        selected = combo.get_selected()
        is_custom = (
            selected == len(self.channels_values) - 1
        )  # Check if "Custom" is selected
        self.custom_channels_row.set_visible(is_custom)

        # Update the setting unless it's custom
        if not is_custom and selected > 0:  # Not default and not custom
            self.settings_manager.save_setting(
                "audio-channels", self.channels_values[selected]
            )
        elif not is_custom and selected == 0:  # Default selected
            self.settings_manager.save_setting("audio-channels", "")

    def _on_resolution_combo_changed(self, combo, param):
        selected = combo.get_selected()
        is_custom = (
            selected == len(self.resolution_values) - 1
        )  # Check if "Custom" is selected
        self.custom_resolution_row.set_visible(is_custom)

        # Update the setting unless it's custom
        if not is_custom and selected > 0:  # Not default and not custom
            self.settings_manager.save_setting(
                "video-resolution", self.resolution_values[selected]
            )
        elif not is_custom and selected == 0:  # Default selected
            self.settings_manager.save_setting("video-resolution", "")

    def _connect_setting_signals(self):
        """Connect signals for saving settings"""
        self.gpu_combo.connect(
            "notify::selected",
            lambda w, p: self.settings_manager.save_setting(
                "gpu-selection", w.get_selected()
            ),
        )
        self.video_quality_combo.connect(
            "notify::selected",
            lambda w, p: self.settings_manager.save_setting(
                "video-quality", w.get_selected()
            ),
        )
        self.video_encoder_combo.connect(
            "notify::selected",
            lambda w, p: self.settings_manager.save_setting(
                "video-codec", w.get_selected()
            ),
        )
        self.preset_combo.connect(
            "notify::selected",
            lambda w, p: self.settings_manager.save_setting("preset", w.get_selected()),
        )
        self.subtitle_extract_combo.connect(
            "notify::selected",
            lambda w, p: self.settings_manager.save_setting(
                "subtitle-extract", w.get_selected()
            ),
        )
        self.audio_handling_combo.connect(
            "notify::selected",
            lambda w, p: self.settings_manager.save_setting(
                "audio-handling", w.get_selected()
            ),
        )
        self.custom_resolution_row.connect(
            "changed",
            lambda w: self.settings_manager.save_setting(
                "video-resolution", w.get_text()
            ),
        )
        self.custom_bitrate_row.connect(
            "changed",
            lambda w: self.settings_manager.save_setting("audio-bitrate", w.get_text()),
        )
        self.custom_channels_row.connect(
            "changed",
            lambda w: self.settings_manager.save_setting(
                "audio-channels", w.get_text()
            ),
        )
        self.options_entry.connect(
            "changed",
            lambda w: self.settings_manager.save_setting(
                "additional-options", w.get_text()
            ),
        )
        self.gpu_partial_check.connect(
            "notify::active",
            lambda w, p: self.settings_manager.save_setting(
                "gpu-partial", w.get_active()
            ),
        )
        self.force_copy_video_check.connect(
            "notify::active",
            lambda w, p: self.settings_manager.save_setting(
                "force-copy-video", w.get_active()
            ),
        )
        self.only_extract_subtitles_check.connect(
            "notify::active",
            lambda w, p: self.settings_manager.save_setting(
                "only-extract-subtitles", w.get_active()
            ),
        )

    def _load_settings(self):
        """Load all settings and update UI"""
        # Encoding settings
        self.gpu_combo.set_selected(
            self.settings_manager.load_setting("gpu-selection", 0)
        )
        self.video_quality_combo.set_selected(
            self.settings_manager.load_setting("video-quality", 0)
        )
        self.video_encoder_combo.set_selected(
            self.settings_manager.load_setting("video-codec", 0)
        )
        self.preset_combo.set_selected(self.settings_manager.load_setting("preset", 0))
        self.subtitle_extract_combo.set_selected(
            self.settings_manager.load_setting("subtitle-extract", 0)
        )
        self.audio_handling_combo.set_selected(
            self.settings_manager.load_setting("audio-handling", 0)
        )

        # Audio settings with dropdown handling
        audio_bitrate = self.settings_manager.load_setting("audio-bitrate", "")
        audio_channels = self.settings_manager.load_setting("audio-channels", "")

        # Handle bitrate setting
        if not audio_bitrate:
            self.audio_bitrate_combo.set_selected(0)  # Default
        elif audio_bitrate in self.bitrate_values:
            self.audio_bitrate_combo.set_selected(
                self.bitrate_values.index(audio_bitrate)
            )
        else:
            # Custom value
            self.audio_bitrate_combo.set_selected(
                len(self.bitrate_values) - 1
            )  # Custom option
            self.custom_bitrate_row.set_text(audio_bitrate)
            self.custom_bitrate_row.set_visible(True)

        # Handle channels setting
        if not audio_channels:
            self.audio_channels_combo.set_selected(0)  # Default
        elif audio_channels in self.channels_values:
            self.audio_channels_combo.set_selected(
                self.channels_values.index(audio_channels)
            )
        else:
            # Custom value
            self.audio_channels_combo.set_selected(
                len(self.channels_values) - 1
            )  # Custom option
            self.custom_channels_row.set_text(audio_channels)
            self.custom_channels_row.set_visible(True)

        # Video resolution with dropdown handling
        video_resolution = self.settings_manager.load_setting("video-resolution", "")

        # Handle video resolution setting
        if not video_resolution:
            self.video_resolution_combo.set_selected(0)  # Default
        elif video_resolution in self.resolution_values:
            self.video_resolution_combo.set_selected(
                self.resolution_values.index(video_resolution)
            )
        else:
            # Custom value
            self.video_resolution_combo.set_selected(
                len(self.resolution_values) - 1
            )  # Custom option
            self.custom_resolution_row.set_text(video_resolution)
            self.custom_resolution_row.set_visible(True)

        # General options
        self.options_entry.set_text(
            self.settings_manager.load_setting("additional-options", "")
        )
        self.gpu_partial_check.set_active(
            self.settings_manager.load_setting("gpu-partial", False)
        )
        self.force_copy_video_check.set_active(
            self.settings_manager.load_setting("force-copy-video", False)
        )
        self.only_extract_subtitles_check.set_active(
            self.settings_manager.load_setting("only-extract-subtitles", False)
        )
