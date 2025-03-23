import os
import subprocess
import json
import re
import gi
import threading

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango, Gdk

# For translations
import gettext

_ = gettext.gettext


class VideoInfoDialog:
    """Dialog to display detailed video file information"""

    def __init__(self, parent_window, file_path):
        self.parent_window = parent_window
        self.file_path = file_path

        # Create the dialog window
        self.dialog = Adw.Window()
        self.dialog.set_default_size(780, 600)
        self.dialog.set_modal(True)
        self.dialog.set_transient_for(parent_window)
        self.dialog.set_hide_on_close(True)

        # Apply custom CSS for better readability
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            row label.title {
                font-size: 15px;
            }
            
            row label.subtitle {
                font-size: 14px;
            }
            
            preferencesgroup label.heading {
                font-weight: bold;
                font-size: 16px;
            }
            
            expanderrow > box > box > label {
                font-size: 15px;
            }
        """)

        display = Gdk.Display.get_default()
        Gtk.StyleContext.add_provider_for_display(
            display, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Main content box
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Add header bar with proper title
        header_bar = Adw.HeaderBar()
        file_name = os.path.basename(file_path)
        title_label = Gtk.Label(label=_("File Information"))
        title_label.add_css_class("title")
        header_bar.set_title_widget(title_label)

        content_box.append(header_bar)

        # Apply custom CSS for better readability
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            row {
                padding: 2px 0px;
            }
            
            label.value-text {
                font-size: 15px;
            }
            
            label.dim-label {
                font-size: 13px;
            }
            
            label.heading {
                font-weight: bold;
                font-size: 16px;
            }
            
            label.caption {
                font-size: 13px;
            }
            
            row expander-row {
                padding: 4px 0px;
            }
            
            expander-row label.heading {
                font-weight: bold;
            }
            
            row button.flat {
                min-height: 34px;
                min-width: 34px;
            }
        """)

        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Create main box for content with proper structure for scrolling
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.set_hexpand(True)  # Ensure box takes full width
        main_box.set_vexpand(True)  # Ensure box takes full height

        # Create a scrolled window that extends to the edges of the main window
        # No margins on scrolled window itself
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_margin_start(0)
        scrolled.set_margin_end(0)
        scrolled.set_margin_top(0)
        scrolled.set_margin_bottom(0)

        # Use a content container inside the scrolled window to apply proper margins
        content_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_container.set_margin_start(24)
        content_container.set_margin_end(24)  # Leave space for scrollbar
        content_container.set_margin_top(24)
        content_container.set_margin_bottom(24)
        content_container.set_spacing(24)
        content_container.set_hexpand(True)

        # Use Adw.Clamp inside the content container
        clamp = Adw.Clamp()
        clamp.set_maximum_size(800)
        clamp.set_tightening_threshold(600)
        clamp.set_hexpand(True)

        # Create info box for actual content
        self.info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.info_box.set_hexpand(True)

        # Set up the widget hierarchy
        clamp.set_child(self.info_box)
        content_container.append(clamp)
        scrolled.set_child(content_container)
        main_box.append(scrolled)

        # Add loading state with spinner
        self.loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.loading_box.set_margin_top(48)
        self.loading_box.set_margin_bottom(48)
        self.loading_box.set_valign(Gtk.Align.CENTER)
        self.loading_box.set_halign(Gtk.Align.CENTER)

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        self.spinner.start()
        self.loading_box.append(self.spinner)

        self.loading_label = Gtk.Label(label=_("Analyzing video file..."))
        self.loading_label.add_css_class("dim-label")
        self.loading_box.append(self.loading_label)

        self.info_box.append(self.loading_box)

        content_box.append(main_box)

        # Set dialog content
        self.dialog.set_content(content_box)

    def show(self):
        """Show the dialog and start loading file information"""
        self.dialog.present()

        # Start loading file information in background
        GLib.idle_add(self._load_file_info)

    def _load_file_info(self):
        """Load file information using ffprobe"""
        try:
            # Get file info in background thread to avoid blocking UI
            info_thread = threading.Thread(target=self._get_file_info_thread)
            info_thread.daemon = True
            info_thread.start()
            return False
        except Exception as e:
            self._show_error(str(e))
            return False

    def _get_file_info_thread(self):
        """Background thread to get file information"""
        try:
            info = get_video_file_info(self.file_path)
            GLib.idle_add(self._update_ui_with_info, info)
        except Exception as e:
            GLib.idle_add(self._show_error, str(e))

    def _update_ui_with_info(self, info):
        """Update the UI with the file information"""
        # Remove loading indicators
        self.info_box.remove(self.loading_box)

        if not info:
            self._show_error(_("Could not retrieve file information."))
            return

        # Add file information groups
        self._add_general_info(info)

        if "streams" in info:
            # Group streams by type
            video_streams = [
                s for s in info["streams"] if s.get("codec_type") == "video"
            ]
            audio_streams = [
                s for s in info["streams"] if s.get("codec_type") == "audio"
            ]
            subtitle_streams = [
                s for s in info["streams"] if s.get("codec_type") == "subtitle"
            ]

            if video_streams:
                self._add_stream_group(_("Video Streams"), video_streams)

            if audio_streams:
                self._add_stream_group(_("Audio Streams"), audio_streams)

            if subtitle_streams:
                self._add_stream_group(_("Subtitles"), subtitle_streams)

        # Add format information
        if "format" in info:
            self._add_format_info(info["format"])

    def _add_general_info(self, info):
        """Add general file information"""
        group = Adw.PreferencesGroup(title=_("General Information"))

        # File name
        file_name = os.path.basename(self.file_path)
        file_name_row = Adw.ActionRow(title=_("File Name"))
        file_name_row.set_subtitle(file_name)
        # Add a copy button to copy the file name
        copy_button = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
        copy_button.add_css_class("flat")
        copy_button.set_tooltip_text(_("Copy file name"))
        copy_button.connect("clicked", lambda btn: self._copy_to_clipboard(file_name))
        file_name_row.add_suffix(copy_button)
        group.add(file_name_row)

        # File path (location)
        file_dir = os.path.dirname(self.file_path)
        file_path_row = Adw.ActionRow(title=_("Location"))
        file_path_row.set_subtitle(file_dir)
        # Add open folder button
        open_button = Gtk.Button.new_from_icon_name("folder-open-symbolic")
        open_button.add_css_class("flat")
        open_button.set_tooltip_text(_("Open containing folder"))
        open_button.connect(
            "clicked", lambda btn: self._open_containing_folder(file_dir)
        )
        file_path_row.add_suffix(open_button)
        group.add(file_path_row)

        # File size
        if "format" in info and "size" in info["format"]:
            size_bytes = int(info["format"]["size"])
            size_mb = size_bytes / (1024 * 1024)
            size_row = Adw.ActionRow(title=_("File Size"))
            # Use the helper function for readable size
            size_str = format_file_size(size_bytes)
            size_row.set_subtitle(size_str)
            group.add(size_row)

        # Duration
        if "format" in info and "duration" in info["format"]:
            duration_secs = float(info["format"]["duration"])
            hours = int(duration_secs // 3600)
            minutes = int((duration_secs % 3600) // 60)
            seconds = duration_secs % 60
            duration_row = Adw.ActionRow(title=_("Duration"))
            duration_row.set_subtitle(f"{hours:02d}:{minutes:02d}:{seconds:06.3f}")

            # Add readable duration
            duration_label = Gtk.Label(label=format_time_display(duration_secs))
            duration_label.add_css_class("caption")
            duration_label.add_css_class("dim-label")
            duration_row.add_suffix(duration_label)

            group.add(duration_row)

        # Format
        if "format" in info and "format_name" in info["format"]:
            format_row = Adw.ActionRow(title=_("Format"))
            format_row.set_subtitle(info["format"]["format_name"])

            # If we have a format_long_name, show it as a suffix
            if "format_long_name" in info["format"]:
                format_label = Gtk.Label(label=info["format"]["format_long_name"])
                format_label.add_css_class("caption")
                format_label.add_css_class("dim-label")
                format_row.add_suffix(format_label)

            group.add(format_row)

        # Bitrate
        if "format" in info and "bit_rate" in info["format"]:
            bit_rate = int(info["format"]["bit_rate"]) / 1000
            bitrate_row = Adw.ActionRow(title=_("Bitrate"))
            bitrate_row.set_subtitle(f"{bit_rate:.2f} kbps")
            group.add(bitrate_row)

        self.info_box.append(group)

    def _copy_to_clipboard(self, text):
        """Copy text to clipboard"""
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(text)

    def _open_containing_folder(self, folder_path):
        """Open the containing folder in the file manager"""
        try:
            Gtk.show_uri(self.dialog, f"file://{folder_path}", Gdk.CURRENT_TIME)
        except Exception as e:
            print(f"Error opening folder: {e}")
            # Fallback method using subprocess
            try:
                subprocess.Popen(["xdg-open", folder_path])
            except Exception as e2:
                print(f"Fallback error opening folder: {e2}")

    def _add_stream_group(self, title, streams):
        """Add a group of streams (video, audio, subtitles)"""
        group = Adw.PreferencesGroup(title=title)

        for idx, stream in enumerate(streams):
            stream_title = f"{title.rstrip('s')} {idx + 1}"
            stream_icon = None

            # Add appropriate stream icon based on type
            if stream.get("codec_type") == "video":
                stream_icon = "video-x-generic-symbolic"
            elif stream.get("codec_type") == "audio":
                stream_icon = "audio-x-generic-symbolic"
            elif stream.get("codec_type") == "subtitle":
                stream_icon = "text-x-generic-symbolic"

            # Add language info to title
            if "tags" in stream:
                if "title" in stream["tags"]:
                    stream_title += f" - {stream['tags']['title']}"
                elif "language" in stream["tags"]:
                    lang = stream["tags"]["language"]
                    stream_title += f" - {lang.upper()}"

            expander = Adw.ExpanderRow(title=stream_title)

            # Add icon suffix if we have one
            if stream_icon:
                icon = Gtk.Image.new_from_icon_name(stream_icon)
                icon.add_css_class("dim-label")
                expander.add_prefix(icon)

            # Codec with icon
            if "codec_name" in stream:
                codec_row = Adw.ActionRow(title=_("Codec"))
                codec_name = stream["codec_name"]
                if "profile" in stream:
                    codec_name += f" ({stream['profile']})"
                codec_row.set_subtitle(codec_name)

                # Add codec icon suffix
                codec_icon = Gtk.Image.new_from_icon_name(
                    "application-x-executable-symbolic"
                )
                codec_icon.add_css_class("dim-label")
                codec_row.add_suffix(codec_icon)

                expander.add_row(codec_row)

            # Resolution for video streams
            if stream.get("codec_type") == "video":
                if "width" in stream and "height" in stream:
                    res_row = Adw.ActionRow(title=_("Resolution"))
                    res_value = f"{stream['width']}×{stream['height']}"
                    res_row.set_subtitle(res_value)

                    # Add standard resolution label if applicable
                    if stream["height"] in [480, 720, 1080, 2160, 4320]:
                        resolution_labels = {
                            480: "SD (480p)",
                            720: "HD (720p)",
                            1080: "Full HD (1080p)",
                            2160: "4K UHD",
                            4320: "8K UHD",
                        }
                        res_label = Gtk.Label(label=resolution_labels[stream["height"]])
                        res_label.add_css_class("caption")
                        res_label.add_css_class("accent")
                        res_row.add_suffix(res_label)

                    expander.add_row(res_row)

                if "r_frame_rate" in stream:
                    try:
                        num, den = map(int, stream["r_frame_rate"].split("/"))
                        fps = num / den if den != 0 else 0
                        fps_row = Adw.ActionRow(title=_("Frame Rate"))
                        fps_row.set_subtitle(f"{fps:.3f} fps")
                        expander.add_row(fps_row)
                    except (ValueError, ZeroDivisionError):
                        pass

                # Pixel format
                if "pix_fmt" in stream:
                    pix_row = Adw.ActionRow(title=_("Pixel Format"))
                    pix_row.set_subtitle(stream["pix_fmt"])
                    expander.add_row(pix_row)

            # Audio-specific information
            elif stream.get("codec_type") == "audio":
                # Sample rate
                if "sample_rate" in stream:
                    sample_row = Adw.ActionRow(title=_("Sample Rate"))
                    sample_rate = int(stream["sample_rate"])
                    sample_row.set_subtitle(f"{sample_rate:,} Hz")

                    # Add suffix for quality indicator
                    if sample_rate >= 44100:
                        quality_label = Gtk.Label(
                            label="CD Quality"
                            if sample_rate == 44100
                            else "Hi-Res Audio"
                        )
                        quality_label.add_css_class("caption")
                        quality_label.add_css_class("accent")
                        sample_row.add_suffix(quality_label)

                    expander.add_row(sample_row)

                # Channels
                if "channels" in stream:
                    channels_row = Adw.ActionRow(title=_("Channels"))
                    channels = stream["channels"]
                    channels_str = str(channels)
                    if channels == 1:
                        channels_str += " (Mono)"
                    elif channels == 2:
                        channels_str += " (Stereo)"
                    elif channels == 6:
                        channels_str += " (5.1 Surround)"
                    elif channels == 8:
                        channels_str += " (7.1 Surround)"
                    channels_row.set_subtitle(channels_str)
                    expander.add_row(channels_row)

                # Bit rate
                if "bit_rate" in stream:
                    bit_rate = int(stream["bit_rate"]) / 1000
                    bitrate_row = Adw.ActionRow(title=_("Bitrate"))
                    bitrate_row.set_subtitle(f"{bit_rate:.2f} kbps")
                    expander.add_row(bitrate_row)

            # Language and other tags
            if "tags" in stream:
                if "language" in stream["tags"]:
                    lang_row = Adw.ActionRow(title=_("Language"))
                    lang_row.set_subtitle(stream["tags"]["language"].upper())

                    # Try to get the full language name
                    try:
                        import locale

                        lang_code = stream["tags"]["language"]
                        lang_obj = locale.setlocale(locale.LC_ALL, f"{lang_code}.UTF-8")
                        if lang_obj:
                            lang_name = locale.nl_langinfo(locale.LANG_NAME)
                            if lang_name and lang_name != lang_code:
                                lang_label = Gtk.Label(label=lang_name)
                                lang_label.add_css_class("caption")
                                lang_row.add_suffix(lang_label)
                    except:
                        pass  # Ignore language name lookup errors

                    expander.add_row(lang_row)

                # Display other tags except title and language
                for tag, value in stream["tags"].items():
                    if tag not in ["title", "language"] and value:
                        tag_row = Adw.ActionRow(title=tag.capitalize())
                        tag_row.set_subtitle(str(value))
                        expander.add_row(tag_row)

            group.add(expander)

        self.info_box.append(group)

    def _add_format_info(self, format_data):
        """Add format-specific information"""
        group = Adw.PreferencesGroup(title=_("Format Details"))

        # Add selected format fields
        format_fields = [
            ("format_long_name", _("Format")),
            ("bit_rate", _("Bitrate (bps)")),
            ("probe_score", _("Detection Score")),
        ]

        for field, title in format_fields:
            if field in format_data:
                row = Adw.ActionRow(title=title)
                row.set_subtitle(str(format_data[field]))
                group.add(row)

        # Add metadata
        if "tags" in format_data:
            metadata_expander = Adw.ExpanderRow(title=_("Metadata"))

            # Flag to track if any rows were added
            rows_added = False

            for tag, value in format_data["tags"].items():
                if value:  # Only add non-empty values
                    tag_row = Adw.ActionRow(title=tag.capitalize())
                    tag_row.set_subtitle(str(value))
                    metadata_expander.add_row(tag_row)
                    rows_added = True

            # Only add the expander if there are metadata rows
            if rows_added:
                group.add(metadata_expander)

        self.info_box.append(group)

    def _show_error(self, message):
        """Show error message in the dialog"""
        # Remove loading indicators if they exist
        if hasattr(self, "loading_box") and self.loading_box in self.info_box:
            self.info_box.remove(self.loading_box)

        # Add error message
        error_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        error_box.set_margin_top(48)
        error_box.set_margin_bottom(48)
        error_box.set_valign(Gtk.Align.CENTER)
        error_box.set_halign(Gtk.Align.CENTER)

        error_icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
        error_icon.set_pixel_size(48)
        error_icon.add_css_class("error")
        error_box.append(error_icon)

        error_label = Gtk.Label(label=_("Error retrieving file information"))
        error_label.add_css_class("title-2")
        error_box.append(error_label)

        error_details = Gtk.Label(label=message)
        error_details.set_wrap(True)
        error_details.add_css_class("dim-label")
        error_box.append(error_details)

        # Add a retry button
        retry_button = Gtk.Button(label=_("Retry"))
        retry_button.add_css_class("pill")
        retry_button.add_css_class("suggested-action")
        retry_button.set_halign(Gtk.Align.CENTER)
        retry_button.set_margin_top(12)
        retry_button.connect("clicked", self._on_retry_clicked)
        error_box.append(retry_button)

        self.info_box.append(error_box)

    def _on_retry_clicked(self, button):
        """Handle retry button click"""
        # Clear the content box
        while True:
            child = self.info_box.get_first_child()
            if child:
                self.info_box.remove(child)
            else:
                break

        # Add loading indicator back
        self.loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.loading_box.set_margin_top(48)
        self.loading_box.set_margin_bottom(48)
        self.loading_box.set_valign(Gtk.Align.CENTER)
        self.loading_box.set_halign(Gtk.Align.CENTER)

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        self.spinner.start()
        self.loading_box.append(self.spinner)

        self.loading_label = Gtk.Label(label=_("Analyzing video file..."))
        self.loading_label.add_css_class("dim-label")
        self.loading_box.append(self.loading_label)

        self.info_box.append(self.loading_box)

        # Retry loading file info
        GLib.idle_add(self._load_file_info)


def get_video_file_info(file_path):
    """
    Get detailed information about a video file using ffprobe

    Args:
        file_path: Path to the video file

    Returns:
        Dictionary containing file information or None on error
    """
    try:
        # Import threading here to avoid circular import
        import threading

        # Ensure file exists
        if not os.path.exists(file_path):
            return None

        # Run ffprobe with JSON output
        command = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            file_path,
        ]

        result = subprocess.run(command, capture_output=True, text=True, check=True)

        # Parse JSON output
        info = json.loads(result.stdout)

        # Calculate bitrate if not provided by ffprobe
        if "format" in info:
            if "bit_rate" not in info["format"] or info["format"]["bit_rate"] == "N/A":
                if "duration" in info["format"] and "size" in info["format"]:
                    duration = float(info["format"]["duration"])
                    size = float(info["format"]["size"])
                    if duration > 0:
                        bitrate = (size * 8) / duration
                        info["format"]["bit_rate"] = str(int(bitrate))

        return info

    except subprocess.CalledProcessError:
        # ffprobe command failed
        return None
    except json.JSONDecodeError:
        # Invalid JSON output
        return None
    except Exception as e:
        print(f"Error getting file info: {e}")
        return None


def format_time_display(seconds):
    """Format time in seconds to a human-readable string"""
    if seconds is None:
        return "N/A"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60

    if hours > 0:
        return f"{hours}h {minutes}m {secs:.1f}s"
    elif minutes > 0:
        return f"{minutes}m {secs:.1f}s"
    else:
        return f"{secs:.1f}s"


def format_file_size(size_bytes):
    """Format file size in bytes to a human-readable string"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
