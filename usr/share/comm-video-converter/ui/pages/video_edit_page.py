import os
import gi
import subprocess
import json

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk, GdkPixbuf

# Setup translation
import gettext

_ = gettext.gettext


class VideoEditPage:
    def __init__(self, app):
        self.app = app

        # Usar o settings_manager do app em vez de criar uma nova instância de Gio.Settings
        self.settings = app.settings_manager

        self.current_video_path = None
        self.video_duration = 0  # Duration in seconds
        self.current_position = 0  # Current position in seconds
        self.start_time = 0
        self.end_time = None  # None means end of video
        self.position_update_id = None
        self.position_changed_handler_id = None  # Store handler ID for blocking
        self.crop_update_timeout_id = None  # Timer ID for delayed crop updates

        # Crop selection variables - load from settings
        self.video_width = 0
        self.video_height = 0
        self.crop_left = self.settings.get_int("preview-crop-left", 0)
        self.crop_right = self.settings.get_int("preview-crop-right", 0)
        self.crop_top = self.settings.get_int("preview-crop-top", 0)
        self.crop_bottom = self.settings.get_int("preview-crop-bottom", 0)

        # Add property adjustment variables - load from settings
        self.brightness = self.settings.get_double("preview-brightness", 0.0)
        self.contrast = self.settings.get_double("preview-contrast", 1.0)
        self.saturation = self.settings.get_double("preview-saturation", 1.0)

        # Additional adjustment variables - load from settings
        self.gamma = self.settings.get_double("preview-gamma", 1.0)
        self.gamma_r = self.settings.get_double("preview-gamma-r", 1.0)
        self.gamma_g = self.settings.get_double("preview-gamma-g", 1.0)
        self.gamma_b = self.settings.get_double("preview-gamma-b", 1.0)
        self.gamma_weight = self.settings.get_double("preview-gamma-weight", 1.0)
        self.fps = None  # Custom FPS value
        self.hue = self.settings.get_double("preview-hue", 0.0)
        self.exposure = self.settings.get_double("preview-exposure", 0.0)

        # Create a dictionary to store tooltips for different sliders and buttons
        self.adjustment_tooltips = {}
        self.button_tooltips = {}

        self.page = self._create_page()

        # Add loading lock to prevent multiple simultaneous video loads
        self.loading_video = False
        self.requested_video_path = None

    # Add a destructor to ensure cleanup is called
    def __del__(self):
        self.cleanup()

    def set_video(self, file_path):
        """Set the video file from the main application and load it"""
        print(f"VideoEditPage.set_video called with file_path: {file_path}")

        # Verify path exists before loading
        if not file_path or not os.path.exists(file_path):
            print(f"Invalid file path for video: {file_path}")
            return False

        # Don't reload if it's already the current video
        if self.current_video_path == file_path:
            print(f"Video already loaded: {file_path}")
            return True

        # Store the requested path - do this first to prevent race conditions
        self.requested_video_path = file_path

        # If we're currently loading a video, don't start another load
        if self.loading_video:
            print("Already loading a video, can't load another one now")
            print(f"Will try again in 500ms: {file_path}")
            # Schedule another attempt after a short delay
            GLib.timeout_add(500, lambda: self._retry_load_video(file_path))
            return True

        # Start the loading process
        self.loading_video = True

        # Clear any existing video data
        self.current_video_path = None

        # Reset frame cache and position
        self.current_position = 0

        # Load video with a slight delay to ensure UI updates properly
        GLib.idle_add(lambda: self._delayed_load_video(file_path))
        return True

    def _retry_load_video(self, file_path):
        """Retry loading video after a short delay"""
        print(f"Retrying video load: {file_path}")

        # If still loading, reschedule
        if self.loading_video:
            print("Still loading previous video, will try again in 500ms")
            return True  # Continue trying

        # Check if the file still exists
        if not file_path or not os.path.exists(file_path):
            print(f"File no longer exists: {file_path}")
            return False

        # Try loading the video again
        return self.set_video(file_path)

    def _delayed_load_video(self, file_path):
        """Load video with a slight delay to ensure UI updates properly"""
        try:
            # Double-check requested path is still valid
            if not file_path or not os.path.exists(file_path):
                print(f"File no longer exists: {file_path}")
                self.loading_video = False
                return False

            # Make sure this is still the file we want to load
            if hasattr(self.app, "preview_file_path") and self.app.preview_file_path:
                if file_path != self.app.preview_file_path:
                    print(
                        f"Ignoring conflicting video load: requested={self.app.preview_file_path}, attempted={file_path}"
                    )
                    self.loading_video = False
                    return False

            # Make sure this is the file we're supposed to load
            if file_path != self.requested_video_path:
                print(
                    f"Conflicting load requests. Requested: {self.requested_video_path}, Loading: {file_path}"
                )
                # Don't reset loading flag here - let the proper requested file load
                return False

            # Update UI to indicate loading
            self.info_filename_label.set_text(_("Loading..."))

            # Perform the actual loading
            result = self.load_video(file_path)
            print(f"Video load result for {os.path.basename(file_path)}: {result}")

            # Always reset the loading flag when done, regardless of success
            self.loading_video = False

            return False  # Don't repeat
        except Exception as e:
            print(f"Error in delayed video loading: {e}")
            import traceback

            traceback.print_exc()
            # Make sure to reset loading flag even on error
            self.loading_video = False
            return False

    def get_page(self):
        return self.page

    def _create_page(self):
        # Create main container with a vertical BoxLayout
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Create a Paned container to allow resizing between video and controls
        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        paned.set_wide_handle(True)  # Make handle easier to grab
        paned.set_vexpand(True)

        # Add size constraints to prevent either part from becoming too small
        paned.set_shrink_start_child(
            False
        )  # Don't shrink the top part below its minimum
        paned.set_shrink_end_child(
            False
        )  # Don't shrink the bottom part below its minimum
        paned.set_resize_start_child(True)  # Allow the top part to be resized
        paned.set_resize_end_child(True)  # Allow the bottom part to be resized

        page.append(paned)

        # Create fixed preview area for the top pane - without any margins
        fixed_preview_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        fixed_preview_area.set_vexpand(True)
        fixed_preview_area.set_hexpand(True)
        fixed_preview_area.set_size_request(-1, 200)  # Set minimum height to 200px
        fixed_preview_area.add_css_class("background")

        # Create a simple image widget for the preview - directly in the container
        self.preview_image = Gtk.Picture()
        self.preview_image.set_can_shrink(True)
        self.preview_image.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.preview_image.set_hexpand(True)
        self.preview_image.set_vexpand(True)

        # Add the image directly to the fixed area for better screen usage
        fixed_preview_area.append(self.preview_image)

        # Add the fixed preview area to the top pane
        paned.set_start_child(fixed_preview_area)

        # Add ScrolledWindow for the rest of the content in the bottom pane
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_hexpand(True)
        scrolled_window.set_vexpand(True)
        scrolled_window.set_size_request(-1, 200)  # Set minimum height to 200px

        # This is our reference to the scrolled window
        self.scrolled_window = scrolled_window

        # Container for scrollable content
        scrollable_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scrollable_content.set_vexpand(True)
        scrolled_window.set_child(scrollable_content)

        # Add the scrolled window to the bottom pane
        paned.set_end_child(scrolled_window)

        # Set initial position (approximately 60% for the video, 40% for controls)
        # This will be adjusted when the window is resized
        GLib.idle_add(lambda: paned.set_position(400))

        # Use Adw.Clamp for consistent width
        clamp = Adw.Clamp()
        clamp.set_maximum_size(900)
        clamp.set_tightening_threshold(700)
        scrollable_content.append(clamp)

        # Main content box for scrollable area
        main_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_content.set_spacing(24)
        main_content.set_margin_start(12)
        main_content.set_margin_end(12)
        main_content.set_margin_bottom(24)
        clamp.set_child(main_content)

        # Cleaner playback controls implementation
        playback_group = Adw.PreferencesGroup()

        # Create position controls box directly in the group (no ActionRow wrapper)
        position_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        position_box.set_margin_top(12)
        position_box.set_margin_bottom(12)
        position_box.set_margin_start(12)
        position_box.set_margin_end(12)
        position_box.set_hexpand(True)

        # Position slider
        slider_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        adjustment = Gtk.Adjustment(value=0, lower=0, upper=100, step_increment=1)
        self.position_scale = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment
        )
        self.position_scale.set_draw_value(False)
        self.position_scale.set_hexpand(True)
        self.position_changed_handler_id = self.position_scale.connect(
            "value-changed", self.on_position_changed
        )

        # Create a custom tooltip popover for immediate display
        self.tooltip_popover = Gtk.Popover()
        self.tooltip_popover.set_autohide(False)  # Don't hide when clicked elsewhere
        self.tooltip_popover.set_position(Gtk.PositionType.TOP)

        # Add a label to the popover
        self.tooltip_label = Gtk.Label()
        self.tooltip_label.set_margin_start(8)
        self.tooltip_label.set_margin_end(8)
        self.tooltip_label.set_margin_top(4)
        self.tooltip_label.set_margin_bottom(4)
        self.tooltip_popover.set_child(self.tooltip_label)

        # Add motion controller for tooltip hover functionality
        motion_controller = Gtk.EventControllerMotion.new()
        motion_controller.connect("motion", self.on_slider_motion)
        motion_controller.connect("leave", self.on_slider_leave)
        self.position_scale.add_controller(motion_controller)

        # Store current hover position for tooltips
        self.hover_position = 0

        slider_box.append(self.position_scale)

        position_box.append(slider_box)

        # Create a combined info and navigation bar
        info_nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        info_nav_box.set_hexpand(True)

        # Position label on the left side
        self.position_label = Gtk.Label(label="0:00.000 / 0:00.000")
        self.position_label.set_halign(Gtk.Align.START)
        self.position_label.set_hexpand(True)
        info_nav_box.append(self.position_label)

        # Navigation buttons in center
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        nav_box.set_halign(Gtk.Align.CENTER)
        nav_box.set_hexpand(True)

        # Previous/next frame buttons
        prev_frame_button = Gtk.Button()
        prev_frame_button.set_icon_name("go-previous-symbolic")
        self.add_tooltip_to_button(prev_frame_button, _("Previous frame"))
        prev_frame_button.connect("clicked", lambda b: self.seek_relative(-1 / 25))
        nav_box.append(prev_frame_button)

        # Step back 1 second
        step_back_button = Gtk.Button()
        step_back_button.set_icon_name("media-seek-backward-symbolic")
        self.add_tooltip_to_button(step_back_button, _("Back 1 second"))
        step_back_button.connect("clicked", lambda b: self.seek_relative(-1))
        nav_box.append(step_back_button)

        # Step back 10 seconds
        step_back10_button = Gtk.Button()
        step_back10_button.set_icon_name("media-skip-backward-symbolic")
        self.add_tooltip_to_button(step_back10_button, _("Back 10 seconds"))
        step_back10_button.connect("clicked", lambda b: self.seek_relative(-10))
        nav_box.append(step_back10_button)

        # Reset button (replacing extract frame button)
        reset_button = Gtk.Button()

        reset_button = Gtk.Button(label=_("Reset"))
        reset_button.add_css_class("destructive-action")  # Red styling for warning
        self.add_tooltip_to_button(reset_button, _("Reset all settings"))
        reset_button.connect("clicked", self.on_reset_all_settings)
        nav_box.append(reset_button)

        # Step forward 10 seconds
        step_fwd10_button = Gtk.Button()
        step_fwd10_button.set_icon_name("media-skip-forward-symbolic")
        self.add_tooltip_to_button(step_fwd10_button, _("Forward 10 seconds"))
        step_fwd10_button.connect("clicked", lambda b: self.seek_relative(10))
        nav_box.append(step_fwd10_button)

        # Step forward 1 second
        step_fwd_button = Gtk.Button()
        step_fwd_button.set_icon_name("media-seek-forward-symbolic")
        self.add_tooltip_to_button(step_fwd_button, _("Forward 1 second"))
        step_fwd_button.connect("clicked", lambda b: self.seek_relative(1))
        nav_box.append(step_fwd_button)

        # Next frame button
        next_frame_button = Gtk.Button()
        next_frame_button.set_icon_name("go-next-symbolic")
        self.add_tooltip_to_button(next_frame_button, _("Next frame"))
        next_frame_button.connect("clicked", lambda b: self.seek_relative(1 / 25))
        nav_box.append(next_frame_button)

        info_nav_box.append(nav_box)

        # Frame counter on the right side
        self.frame_label = Gtk.Label(label="Frame: 0/0")
        self.frame_label.set_halign(Gtk.Align.END)
        self.frame_label.set_hexpand(True)
        info_nav_box.append(self.frame_label)

        position_box.append(info_nav_box)

        # Add position controls directly to the group
        playback_group.add(position_box)

        # Add playback controls as the first element in the scrollable content
        main_content.append(playback_group)

        # Add all other control sections to the scrollable area
        # Improved trimming controls - with consistent styling like crop section
        trim_group = Adw.PreferencesGroup(title=_("Trim by Time"))

        # Create an ActionRow for trim controls
        trim_row = Adw.ActionRow()
        trim_row.set_activatable(False)

        # Create a single row for all trim controls
        trim_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        trim_box.set_margin_top(12)
        trim_box.set_margin_bottom(12)

        # Start time section
        start_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        start_box.set_hexpand(True)

        self.start_time_label = Gtk.Label(label="0:00.000")
        self.start_time_label.set_halign(Gtk.Align.START)
        self.start_time_label.set_width_chars(8)

        set_start_button = Gtk.Button(label=_("Start"))
        self.add_tooltip_to_button(
            set_start_button, _("Set timeline marked time as start")
        )
        set_start_button.connect("clicked", self.on_set_start_time)

        start_box.append(set_start_button)
        start_box.append(self.start_time_label)
        trim_box.append(start_box)

        # End time section
        end_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        end_box.set_hexpand(True)

        self.end_time_label = Gtk.Label()
        self.end_time_label.set_halign(Gtk.Align.START)
        self.end_time_label.set_width_chars(8)

        set_end_button = Gtk.Button(label=_("End"))
        self.add_tooltip_to_button(set_end_button, _("Set timeline marked time as end"))
        set_end_button.connect("clicked", self.on_set_end_time)

        end_box.append(set_end_button)
        end_box.append(self.end_time_label)
        trim_box.append(end_box)

        # Duration section
        duration_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        duration_box.set_hexpand(False)

        duration_label = Gtk.Label(label=_("Duration:"))
        duration_label.set_halign(Gtk.Align.END)

        self.duration_label = Gtk.Label(label="0:00.000")
        self.duration_label.set_halign(Gtk.Align.START)

        duration_box.append(duration_label)
        duration_box.append(self.duration_label)
        trim_box.append(duration_box)

        # Reset button with icon (similar to video adjustments)
        reset_button = Gtk.Button()
        reset_button.set_icon_name("edit-undo-symbolic")
        reset_button.add_css_class("flat")
        reset_button.add_css_class("circular")
        self.add_tooltip_to_button(reset_button, _("Reset trim points"))
        reset_button.connect("clicked", self.on_reset_trim_points)
        trim_box.append(reset_button)

        # Add the trim box to the row and the row to the group
        trim_row.add_suffix(trim_box)
        trim_group.add(trim_row)

        main_content.append(trim_group)

        # Crop controls - using margin-based approach (left, right, top, bottom)
        crop_group = Adw.PreferencesGroup(title=_("Crop by Edges"))

        # Crop dimension controls with new terminology
        crop_controls_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        crop_controls_box.set_margin_top(12)
        crop_controls_box.set_margin_bottom(12)
        crop_controls_box.set_margin_start(16)
        crop_controls_box.set_margin_end(16)
        crop_controls_box.add_css_class("card")
        crop_controls_box.set_margin_start(0)
        crop_controls_box.set_margin_end(0)

        # Create a box for the crop margin inputs in a single horizontal row
        crop_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        crop_box.set_halign(Gtk.Align.FILL)
        # Add card styling to match other widgets
        crop_box.set_margin_top(8)
        crop_box.set_margin_bottom(12)
        crop_box.set_margin_start(12)
        crop_box.set_margin_end(12)
        # Use individual margins instead of set_padding (which doesn't exist)
        crop_box.set_margin_top(crop_box.get_margin_top() + 12)
        crop_box.set_margin_bottom(crop_box.get_margin_bottom() + 12)
        crop_box.set_margin_start(crop_box.get_margin_start() + 12)
        crop_box.set_margin_end(crop_box.get_margin_end() + 12)

        # Create a common width for all spinbuttons for alignment

        # Left margin - vertical layout with label at top
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left_box.set_hexpand(True)
        left_box.set_halign(Gtk.Align.CENTER)

        left_label = Gtk.Label(label=_("Left Side"))
        left_label.set_halign(Gtk.Align.CENTER)
        left_box.append(left_label)

        left_input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        left_input_box.set_halign(Gtk.Align.CENTER)

        adjustment = Gtk.Adjustment(value=0, lower=0, upper=9999, step_increment=1)
        self.crop_left_spin = Gtk.SpinButton()
        self.crop_left_spin.set_adjustment(adjustment)
        self.crop_left_spin.set_numeric(True)
        self.crop_left_spin.set_width_chars(5)  # Set uniform width
        self.crop_left_spin.connect("value-changed", self.on_crop_value_changed)
        left_input_box.append(self.crop_left_spin)

        left_reset = Gtk.Button()
        left_reset.set_icon_name("edit-undo-symbolic")
        left_reset.add_css_class("flat")
        left_reset.add_css_class("circular")
        self.add_tooltip_to_button(left_reset, _("Reset to default"))
        left_reset.connect("clicked", lambda b: self.reset_crop_value("left"))
        left_input_box.append(left_reset)

        left_box.append(left_input_box)
        crop_box.append(left_box)

        # Right margin - vertical layout with label at top
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right_box.set_hexpand(True)
        right_box.set_halign(Gtk.Align.CENTER)

        right_label = Gtk.Label(label=_("Right Side"))
        right_label.set_halign(Gtk.Align.CENTER)
        right_box.append(right_label)

        right_input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        right_input_box.set_halign(Gtk.Align.CENTER)

        adjustment = Gtk.Adjustment(value=0, lower=0, upper=9999, step_increment=1)
        self.crop_right_spin = Gtk.SpinButton()
        self.crop_right_spin.set_adjustment(adjustment)
        self.crop_right_spin.set_numeric(True)
        self.crop_right_spin.set_width_chars(5)  # Set uniform width
        self.crop_right_spin.connect("value-changed", self.on_crop_value_changed)
        right_input_box.append(self.crop_right_spin)

        right_reset = Gtk.Button()
        right_reset.set_icon_name("edit-undo-symbolic")
        right_reset.add_css_class("flat")
        right_reset.add_css_class("circular")
        self.add_tooltip_to_button(right_reset, _("Reset to default"))
        right_reset.connect("clicked", lambda b: self.reset_crop_value("right"))
        right_input_box.append(right_reset)

        right_box.append(right_input_box)
        crop_box.append(right_box)

        # Top margin - vertical layout with label at top
        top_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        top_box.set_hexpand(True)
        top_box.set_halign(Gtk.Align.CENTER)

        top_label = Gtk.Label(label=_("Top Side"))
        top_label.set_halign(Gtk.Align.CENTER)
        top_box.append(top_label)

        top_input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        top_input_box.set_halign(Gtk.Align.CENTER)

        adjustment = Gtk.Adjustment(value=0, lower=0, upper=9999, step_increment=1)
        self.crop_top_spin = Gtk.SpinButton()
        self.crop_top_spin.set_adjustment(adjustment)
        self.crop_top_spin.set_numeric(True)
        self.crop_top_spin.set_width_chars(5)  # Set uniform width
        self.crop_top_spin.connect("value-changed", self.on_crop_value_changed)
        top_input_box.append(self.crop_top_spin)

        top_reset = Gtk.Button()
        top_reset.set_icon_name("edit-undo-symbolic")
        top_reset.add_css_class("flat")
        top_reset.add_css_class("circular")
        self.add_tooltip_to_button(top_reset, _("Reset to default"))
        top_reset.connect("clicked", lambda b: self.reset_crop_value("top"))
        top_input_box.append(top_reset)

        top_box.append(top_input_box)
        crop_box.append(top_box)

        # Bottom margin - vertical layout with label at top
        bottom_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        bottom_box.set_hexpand(True)
        bottom_box.set_halign(Gtk.Align.CENTER)

        bottom_label = Gtk.Label(label=_("Bottom Side"))
        bottom_label.set_halign(Gtk.Align.CENTER)
        bottom_box.append(bottom_label)

        bottom_input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bottom_input_box.set_halign(Gtk.Align.CENTER)

        adjustment = Gtk.Adjustment(value=0, lower=0, upper=9999, step_increment=1)
        self.crop_bottom_spin = Gtk.SpinButton()
        self.crop_bottom_spin.set_adjustment(adjustment)
        self.crop_bottom_spin.set_numeric(True)
        self.crop_bottom_spin.set_width_chars(5)  # Set uniform width
        self.crop_bottom_spin.connect("value-changed", self.on_crop_value_changed)
        bottom_input_box.append(self.crop_bottom_spin)

        bottom_reset = Gtk.Button()
        bottom_reset.set_icon_name("edit-undo-symbolic")
        bottom_reset.add_css_class("flat")
        bottom_reset.add_css_class("circular")
        self.add_tooltip_to_button(bottom_reset, _("Reset to default"))
        bottom_reset.connect("clicked", lambda b: self.reset_crop_value("bottom"))
        bottom_input_box.append(bottom_reset)

        bottom_box.append(bottom_input_box)
        crop_box.append(bottom_box)

        # Result size indicator below the crop controls
        result_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        result_box.set_halign(Gtk.Align.CENTER)

        result_label = Gtk.Label()
        result_label.set_markup(
            "<small>" + _("Final size: calculating...") + "</small>"
        )
        result_label.set_halign(Gtk.Align.CENTER)
        result_box.append(result_label)
        self.crop_result_label = result_label

        crop_controls_box.append(crop_box)
        crop_controls_box.append(result_box)

        # Add the crop controls directly to the group for better layout
        crop_group.add(crop_controls_box)

        main_content.append(crop_group)

        # Add the adjustments group for brightness/contrast/saturation
        adjustments_group = Adw.PreferencesGroup(title=_("Video Adjustments"))

        # Brightness adjustment
        brightness_row = Adw.ActionRow(title=_("Brightness"))
        brightness_row.set_subtitle(_("Between -1.0 and 1.0. Default: 0.0"))
        brightness_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        brightness_box.set_margin_top(8)
        brightness_box.set_margin_bottom(8)

        self.brightness_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, -1.0, 1.0, 0.05
        )
        self.brightness_scale.set_value(self.brightness)
        self.brightness_scale.set_size_request(
            400, -1
        )  # Double the width from 200 to 400
        self.brightness_scale.set_draw_value(True)
        self.brightness_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.brightness_scale.connect("value-changed", self.on_brightness_changed)

        # Add tooltip functionality to the brightness scale
        self.add_tooltip_to_slider(self.brightness_scale, lambda x: f"{x:.2f}")

        brightness_reset = Gtk.Button()
        brightness_reset.set_icon_name("edit-undo-symbolic")
        brightness_reset.add_css_class("flat")
        brightness_reset.add_css_class("circular")
        self.add_tooltip_to_button(brightness_reset, _("Reset to default"))
        brightness_reset.connect("clicked", lambda b: self.reset_brightness())

        brightness_box.append(self.brightness_scale)
        brightness_box.append(brightness_reset)
        brightness_row.add_suffix(brightness_box)
        adjustments_group.add(brightness_row)

        # Contrast adjustment
        contrast_row = Adw.ActionRow(title=_("Contrast"))
        contrast_row.set_subtitle(_("Between 0.0 and 2.0. Default: 1.0"))
        contrast_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        contrast_box.set_margin_top(8)
        contrast_box.set_margin_bottom(8)

        self.contrast_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, 2.0, 0.05
        )
        self.contrast_scale.set_value(self.contrast)
        self.contrast_scale.set_size_request(
            400, -1
        )  # Double the width from 200 to 400
        self.contrast_scale.set_draw_value(True)
        self.contrast_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.contrast_scale.connect("value-changed", self.on_contrast_changed)

        # Add tooltip functionality to the contrast scale
        self.add_tooltip_to_slider(self.contrast_scale, lambda x: f"{x:.2f}")

        contrast_reset = Gtk.Button()
        contrast_reset.set_icon_name("edit-undo-symbolic")
        contrast_reset.add_css_class("flat")
        contrast_reset.add_css_class("circular")
        self.add_tooltip_to_button(contrast_reset, _("Reset to default"))
        contrast_reset.connect("clicked", lambda b: self.reset_contrast())

        contrast_box.append(self.contrast_scale)
        contrast_box.append(contrast_reset)
        contrast_row.add_suffix(contrast_box)
        adjustments_group.add(contrast_row)

        # Saturation adjustment
        saturation_row = Adw.ActionRow(title=_("Saturation"))
        saturation_row.set_subtitle(_("Between 0.0 and 2.0. Default: 1.0"))
        saturation_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        saturation_box.set_margin_top(8)
        saturation_box.set_margin_bottom(8)

        self.saturation_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, 2.0, 0.05
        )
        self.saturation_scale.set_value(self.saturation)
        self.saturation_scale.set_size_request(
            400, -1
        )  # Double the width from 200 to 400
        self.saturation_scale.set_draw_value(True)
        self.saturation_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.saturation_scale.connect("value-changed", self.on_saturation_changed)

        # Add tooltip functionality to the saturation scale
        self.add_tooltip_to_slider(self.saturation_scale, lambda x: f"{x:.2f}")

        saturation_reset = Gtk.Button()
        saturation_reset.set_icon_name("edit-undo-symbolic")
        saturation_reset.add_css_class("flat")
        saturation_reset.add_css_class("circular")
        self.add_tooltip_to_button(saturation_reset, _("Reset to default"))
        saturation_reset.connect("clicked", lambda b: self.reset_saturation())

        saturation_box.append(self.saturation_scale)
        saturation_box.append(saturation_reset)
        saturation_row.add_suffix(saturation_box)
        adjustments_group.add(saturation_row)

        # Exposure adjustment
        exposure_row = Adw.ActionRow(title=_("Exposure"))
        exposure_row.set_subtitle(_("Between -3.0 and 3.0 EV. Default: 0.0"))
        exposure_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        exposure_box.set_margin_top(8)
        exposure_box.set_margin_bottom(8)

        self.exposure_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, -3.0, 3.0, 0.1
        )
        self.exposure_scale.set_value(self.exposure)
        self.exposure_scale.set_size_request(
            400, -1
        )  # Double the width from 200 to 400
        self.exposure_scale.set_draw_value(True)
        self.exposure_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.exposure_scale.connect("value-changed", self.on_exposure_changed)

        # Add tooltip functionality to the exposure scale
        self.add_tooltip_to_slider(self.exposure_scale, lambda x: f"{x:.2f}")

        exposure_reset = Gtk.Button()
        exposure_reset.set_icon_name("edit-undo-symbolic")
        exposure_reset.add_css_class("flat")
        exposure_reset.add_css_class("circular")
        self.add_tooltip_to_button(exposure_reset, _("Reset to default"))
        exposure_reset.connect("clicked", lambda b: self.reset_exposure())

        exposure_box.append(self.exposure_scale)
        exposure_box.append(exposure_reset)
        exposure_row.add_suffix(exposure_box)
        adjustments_group.add(exposure_row)

        # Gamma adjustment
        gamma_row = Adw.ActionRow(title=_("Gamma"))
        gamma_row.set_subtitle(_("Between 0.0 and 16.0. Default: 1.0"))
        gamma_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        gamma_box.set_margin_top(8)
        gamma_box.set_margin_bottom(8)

        self.gamma_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, 16.0, 0.1
        )
        self.gamma_scale.set_value(self.gamma)
        self.gamma_scale.set_size_request(400, -1)  # Double the width from 200 to 400
        self.gamma_scale.set_draw_value(True)
        self.gamma_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.gamma_scale.connect("value-changed", self.on_gamma_changed)

        # Add tooltip functionality to the gamma scale
        self.add_tooltip_to_slider(self.gamma_scale, lambda x: f"{x:.2f}")

        gamma_reset = Gtk.Button()
        gamma_reset.set_icon_name("edit-undo-symbolic")
        gamma_reset.add_css_class("flat")
        gamma_reset.add_css_class("circular")
        self.add_tooltip_to_button(gamma_reset, _("Reset to default"))
        gamma_reset.connect("clicked", lambda b: self.reset_gamma())

        gamma_box.append(self.gamma_scale)
        gamma_box.append(gamma_reset)
        gamma_row.add_suffix(gamma_box)
        adjustments_group.add(gamma_row)

        # Red Gamma adjustment
        gamma_r_row = Adw.ActionRow(title=_("Red Gamma"))
        gamma_r_row.set_subtitle(_("Between 0.0 and 16.0. Default: 1.0"))
        gamma_r_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        gamma_r_box.set_margin_top(8)
        gamma_r_box.set_margin_bottom(8)

        self.gamma_r_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, 16.0, 0.1
        )
        self.gamma_r_scale.set_value(self.gamma_r)
        self.gamma_r_scale.set_size_request(400, -1)  # Double the width from 200 to 400
        self.gamma_r_scale.set_draw_value(True)
        self.gamma_r_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.gamma_r_scale.connect("value-changed", self.on_gamma_r_changed)

        # Add tooltip functionality to the red gamma scale
        self.add_tooltip_to_slider(self.gamma_r_scale, lambda x: f"{x:.2f}")

        gamma_r_reset = Gtk.Button()
        gamma_r_reset.set_icon_name("edit-undo-symbolic")
        gamma_r_reset.add_css_class("flat")
        gamma_r_reset.add_css_class("circular")
        self.add_tooltip_to_button(gamma_r_reset, _("Reset to default"))
        gamma_r_reset.connect("clicked", lambda b: self.reset_gamma_r())

        gamma_r_box.append(self.gamma_r_scale)
        gamma_r_box.append(gamma_r_reset)
        gamma_r_row.add_suffix(gamma_r_box)
        adjustments_group.add(gamma_r_row)

        # Green Gamma adjustment
        gamma_g_row = Adw.ActionRow(title=_("Green Gamma"))
        gamma_g_row.set_subtitle(_("Between 0.0 and 16.0. Default: 1.0"))
        gamma_g_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        gamma_g_box.set_margin_top(8)
        gamma_g_box.set_margin_bottom(8)

        self.gamma_g_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, 16.0, 0.1
        )
        self.gamma_g_scale.set_value(self.gamma_g)
        self.gamma_g_scale.set_size_request(400, -1)  # Double the width from 200 to 400
        self.gamma_g_scale.set_draw_value(True)
        self.gamma_g_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.gamma_g_scale.connect("value-changed", self.on_gamma_g_changed)

        # Add tooltip functionality to the green gamma scale
        self.add_tooltip_to_slider(self.gamma_g_scale, lambda x: f"{x:.2f}")

        gamma_g_reset = Gtk.Button()
        gamma_g_reset.set_icon_name("edit-undo-symbolic")
        gamma_g_reset.add_css_class("flat")
        gamma_g_reset.add_css_class("circular")
        self.add_tooltip_to_button(gamma_g_reset, _("Reset to default"))
        gamma_g_reset.connect("clicked", lambda b: self.reset_gamma_g())

        gamma_g_box.append(self.gamma_g_scale)
        gamma_g_box.append(gamma_g_reset)
        gamma_g_row.add_suffix(gamma_g_box)
        adjustments_group.add(gamma_g_row)

        # Blue Gamma adjustment
        gamma_b_row = Adw.ActionRow(title=_("Blue Gamma"))
        gamma_b_row.set_subtitle(_("Between 0.0 and 16.0. Default: 1.0"))
        gamma_b_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        gamma_b_box.set_margin_top(8)
        gamma_b_box.set_margin_bottom(8)

        self.gamma_b_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, 16.0, 0.1
        )
        self.gamma_b_scale.set_value(self.gamma_b)
        self.gamma_b_scale.set_size_request(400, -1)  # Double the width from 200 to 400
        self.gamma_b_scale.set_draw_value(True)
        self.gamma_b_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.gamma_b_scale.connect("value-changed", self.on_gamma_b_changed)

        # Add tooltip functionality to the blue gamma scale
        self.add_tooltip_to_slider(self.gamma_b_scale, lambda x: f"{x:.2f}")

        gamma_b_reset = Gtk.Button()
        gamma_b_reset.set_icon_name("edit-undo-symbolic")
        gamma_b_reset.add_css_class("flat")
        gamma_b_reset.add_css_class("circular")
        self.add_tooltip_to_button(gamma_b_reset, _("Reset to default"))
        gamma_b_reset.connect("clicked", lambda b: self.reset_gamma_b())

        gamma_b_box.append(self.gamma_b_scale)
        gamma_b_box.append(gamma_b_reset)
        gamma_b_row.add_suffix(gamma_b_box)
        adjustments_group.add(gamma_b_row)

        # Gamma Weight adjustment
        gamma_weight_row = Adw.ActionRow(title=_("Gamma Weight"))
        gamma_weight_row.set_subtitle(_("Between 0.0 and 1.0. Default: 1.0"))
        gamma_weight_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        gamma_weight_box.set_margin_top(8)
        gamma_weight_box.set_margin_bottom(8)

        self.gamma_weight_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01
        )
        self.gamma_weight_scale.set_value(self.gamma_weight)
        self.gamma_weight_scale.set_size_request(
            400, -1
        )  # Double the width from 200 to 400
        self.gamma_weight_scale.set_draw_value(True)
        self.gamma_weight_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.gamma_weight_scale.connect("value-changed", self.on_gamma_weight_changed)

        # Add tooltip functionality to the gamma weight scale
        self.add_tooltip_to_slider(self.gamma_weight_scale, lambda x: f"{x:.2f}")

        gamma_weight_reset = Gtk.Button()
        gamma_weight_reset.set_icon_name("edit-undo-symbolic")
        gamma_weight_reset.add_css_class("flat")
        gamma_weight_reset.add_css_class("circular")
        self.add_tooltip_to_button(gamma_weight_reset, _("Reset to default"))
        gamma_weight_reset.connect("clicked", lambda b: self.reset_gamma_weight())

        gamma_weight_box.append(self.gamma_weight_scale)
        gamma_weight_box.append(gamma_weight_reset)
        gamma_weight_row.add_suffix(gamma_weight_box)
        adjustments_group.add(gamma_weight_row)

        # Hue adjustment
        hue_row = Adw.ActionRow(title=_("Hue"))
        hue_row.set_subtitle(_("Between -3.14 and 3.14 radians. Default: 0.0"))
        hue_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hue_box.set_margin_top(8)
        hue_box.set_margin_bottom(8)

        self.hue_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, -3.14, 3.14, 0.05
        )
        self.hue_scale.set_value(self.hue)
        self.hue_scale.set_size_request(400, -1)  # Double the width from 200 to 400
        self.hue_scale.set_draw_value(True)
        self.hue_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.hue_scale.connect("value-changed", self.on_hue_changed)

        # Add tooltip functionality to the hue scale
        self.add_tooltip_to_slider(self.hue_scale, lambda x: f"{x:.2f}")

        hue_reset = Gtk.Button()
        hue_reset.set_icon_name("edit-undo-symbolic")
        hue_reset.add_css_class("flat")
        hue_reset.add_css_class("circular")
        self.add_tooltip_to_button(hue_reset, _("Reset to default"))
        hue_reset.connect("clicked", lambda b: self.reset_hue())

        hue_box.append(self.hue_scale)
        hue_box.append(hue_reset)
        hue_row.add_suffix(hue_box)
        adjustments_group.add(hue_row)

        # Add the adjustments group to the main content
        main_content.append(adjustments_group)

        # Add video info display at the bottom with a more concise layout - changed to per-line display
        info_group = Adw.PreferencesGroup(title=_("Video Information"))

        # Create individual rows for each piece of information
        self.info_filename_row = Adw.ActionRow(title=_("Filename"))
        self.info_filename_label = Gtk.Label(label=_("Unknown"))
        self.info_filename_label.set_halign(Gtk.Align.END)
        self.info_filename_row.add_suffix(self.info_filename_label)
        info_group.add(self.info_filename_row)

        self.info_dimensions_row = Adw.ActionRow(title=_("Resolution"))
        self.info_dimensions_label = Gtk.Label(label=_("Unknown"))
        self.info_dimensions_label.set_halign(Gtk.Align.END)
        self.info_dimensions_row.add_suffix(self.info_dimensions_label)
        info_group.add(self.info_dimensions_row)

        self.info_codec_row = Adw.ActionRow(title=_("Codec"))
        self.info_codec_label = Gtk.Label(label=_("Unknown"))
        self.info_codec_label.set_halign(Gtk.Align.END)
        self.info_codec_row.add_suffix(self.info_codec_label)
        info_group.add(self.info_codec_row)

        # Add format row for displaying the format_long_name
        self.info_format_row = Adw.ActionRow(title=_("Format"))
        self.info_format_label = Gtk.Label(label=_("Unknown"))
        self.info_format_label.set_halign(Gtk.Align.END)
        self.info_format_row.add_suffix(self.info_format_label)
        info_group.add(self.info_format_row)

        self.info_filesize_row = Adw.ActionRow(title=_("File Size"))
        self.info_filesize_label = Gtk.Label(label=_("Unknown"))
        self.info_filesize_label.set_halign(Gtk.Align.END)
        self.info_filesize_row.add_suffix(self.info_filesize_label)
        info_group.add(self.info_filesize_row)

        self.info_duration_row = Adw.ActionRow(title=_("Duration"))
        self.info_duration_label = Gtk.Label(label=_("Unknown"))
        self.info_duration_label.set_halign(Gtk.Align.END)
        self.info_duration_row.add_suffix(self.info_duration_label)
        info_group.add(self.info_duration_row)

        self.info_fps_row = Adw.ActionRow(title=_("Frame Rate"))
        self.info_fps_label = Gtk.Label(label=_("Unknown"))
        self.info_fps_label.set_halign(Gtk.Align.END)
        self.info_fps_row.add_suffix(self.info_fps_label)
        info_group.add(self.info_fps_row)

        main_content.append(info_group)

        return page

    def add_tooltip_to_slider(self, slider, format_func):
        """Add instant tooltip functionality to any slider"""
        # Store the format function with the slider for use in the motion handler
        slider.format_func = format_func

        # Create a unique tooltip popover for this slider
        tooltip_popover = Gtk.Popover()
        tooltip_popover.set_autohide(False)
        tooltip_popover.set_position(Gtk.PositionType.TOP)

        # Add a label to the popover
        tooltip_label = Gtk.Label()
        tooltip_label.set_margin_start(8)
        tooltip_label.set_margin_end(8)
        tooltip_label.set_margin_top(4)
        tooltip_label.set_margin_bottom(4)
        tooltip_popover.set_child(tooltip_label)

        # Store the tooltip popover in our dictionary with the slider as the key
        self.adjustment_tooltips[slider] = {
            "popover": tooltip_popover,
            "label": tooltip_label,
        }

        # Add motion controller to show tooltip
        motion_controller = Gtk.EventControllerMotion.new()
        motion_controller.connect("motion", self.on_adjustment_motion)
        motion_controller.connect("leave", self.on_adjustment_leave)
        slider.add_controller(motion_controller)

    def add_tooltip_to_button(self, button, tooltip_text):
        """Add custom tooltip functionality to any button"""
        # Create a unique tooltip popover for this button
        tooltip_popover = Gtk.Popover()
        tooltip_popover.set_autohide(False)
        tooltip_popover.set_position(Gtk.PositionType.TOP)

        # Add a label to the popover
        tooltip_label = Gtk.Label()
        tooltip_label.set_text(tooltip_text)
        tooltip_label.set_margin_start(8)
        tooltip_label.set_margin_end(8)
        tooltip_label.set_margin_top(4)
        tooltip_label.set_margin_bottom(4)
        tooltip_popover.set_child(tooltip_label)

        # Store the tooltip popover in our dictionary with the button as the key
        self.button_tooltips[button] = {
            "popover": tooltip_popover,
            "label": tooltip_label,
            "text": tooltip_text,
        }

        # Add motion controller to show/hide tooltip
        motion_controller = Gtk.EventControllerMotion.new()
        motion_controller.connect("enter", self.on_button_enter)
        motion_controller.connect("leave", self.on_button_leave)
        button.add_controller(motion_controller)

        # Remove the standard tooltip if it exists
        button.set_tooltip_text(None)

    def on_button_enter(self, controller, *args):
        """Show tooltip when mouse enters a button"""
        button = controller.get_widget()

        # Check if we have a tooltip for this button
        if button not in self.button_tooltips:
            return

        tooltip_data = self.button_tooltips[button]
        tooltip_popover = tooltip_data["popover"]

        # Position tooltip above button
        rect = Gdk.Rectangle()
        rect.x = button.get_width() / 2
        rect.y = 0
        rect.width = 1
        rect.height = 1

        tooltip_popover.set_pointing_to(rect)
        tooltip_popover.set_parent(button)
        tooltip_popover.popup()

    def on_button_leave(self, controller, *args):
        """Hide tooltip when mouse leaves a button"""
        button = controller.get_widget()
        if button in self.button_tooltips:
            self.button_tooltips[button]["popover"].popdown()

    def find_slider_gizmo(self, slider):
        """Find the GtkGizmo child that represents the actual slider track"""
        # Try to find the slider's primary GtkGizmo - the track/trough component
        if not slider or not hasattr(slider, "get_first_child"):
            return None

        # In GTK4 scale implementation, the slider track is typically the first GtkGizmo
        # child or grandchild of the scale widget
        def find_gizmo(widget):
            if not widget:
                return None

            # Check if this widget is a GtkGizmo
            widget_type = type(widget).__name__
            if "Gizmo" in widget_type:
                return widget

            # Check first child
            child = (
                widget.get_first_child() if hasattr(widget, "get_first_child") else None
            )
            gizmo = find_gizmo(child)
            if gizmo:
                return gizmo

            # Check next sibling
            sibling = (
                widget.get_next_sibling()
                if hasattr(widget, "get_next_sibling")
                else None
            )
            return find_gizmo(sibling)

        return find_gizmo(slider.get_first_child())

    def get_slider_value_at_position(self, slider, x):
        """Calculate value at a given x-position for a slider, using GtkGizmo if possible"""
        # Get slider adjustment values
        adjustment = slider.get_adjustment()
        min_value = adjustment.get_lower()
        max_value = adjustment.get_upper()

        # Try to find the slider track GtkGizmo
        gizmo = self.find_slider_gizmo(slider)

        if gizmo:
            # Let's use the GtkGizmo directly to calculate the position
            # Get GtkGizmo allocation coordinates relative to the slider
            gizmo_alloc = [0, 0]  # [x, width]

            # In GTK4, we need to traverse upward to get the allocation
            # relative to the slider widget
            parent = gizmo
            while parent and parent != slider:
                if hasattr(parent, "get_allocation"):
                    allocation = parent.get_allocation()
                    gizmo_alloc[0] += allocation.x if hasattr(allocation, "x") else 0
                parent = parent.get_parent() if hasattr(parent, "get_parent") else None

            # Get the GtkGizmo dimensions
            if hasattr(gizmo, "get_width"):
                gizmo_width = gizmo.get_width()
            else:
                # Fallback - use the slider width
                gizmo_width = slider.get_width()

            # Calculate the relative position within the GtkGizmo
            gizmo_relative_x = x - gizmo_alloc[0]

            # Clamp to GtkGizmo boundaries
            if gizmo_relative_x <= 0:
                return min_value
            elif gizmo_relative_x >= gizmo_width:
                return max_value
            else:
                # Calculate ratio within the GtkGizmo bounds
                ratio = gizmo_relative_x / gizmo_width
                return min_value + (ratio * (max_value - min_value))
        else:
            # Fallback if we couldn't find the GtkGizmo
            width = slider.get_width()
            if width <= 0:
                return 0

            # Simple ratio calculation
            ratio = max(0.0, min(1.0, x / width))
            return min_value + (ratio * (max_value - min_value))

    def on_adjustment_motion(self, controller, x, y):
        """Show tooltip for sliders using direct GtkGizmo handling"""
        slider = controller.get_widget()

        # Check if we have a tooltip for this slider
        if slider not in self.adjustment_tooltips:
            return

        tooltip_data = self.adjustment_tooltips[slider]
        tooltip_popover = tooltip_data["popover"]
        tooltip_label = tooltip_data["label"]

        # Get the hover value directly using the GtkGizmo approach
        hover_value = self.get_slider_value_at_position(slider, x)

        # Format and display tooltip
        if hasattr(slider, "format_func"):
            tooltip_text = slider.format_func(hover_value)
            tooltip_label.set_text(tooltip_text)

            # Position tooltip above cursor
            rect = Gdk.Rectangle()
            rect.x = x
            rect.y = 0
            rect.width = 1
            rect.height = 1

            tooltip_popover.set_pointing_to(rect)
            tooltip_popover.set_parent(slider)
            tooltip_popover.popup()

    def on_adjustment_leave(self, controller):
        """Hide tooltip when mouse leaves an adjustment slider"""
        slider = controller.get_widget()
        if slider in self.adjustment_tooltips:
            self.adjustment_tooltips[slider]["popover"].popdown()

    def on_scroll_event(self, controller, dx, dy):
        """Handle scroll events from the fixed area and propagate them to the scrolled window"""
        # Get current scroll position
        vadj = self.scrolled_window.get_vadjustment()

        # Calculate new position (more scroll speed for better responsiveness)
        new_value = vadj.get_value() + dy * 25  # Multiply by 25 for faster scrolling

        # Clamp to valid range
        new_value = max(
            vadj.get_lower(), min(new_value, vadj.get_upper() - vadj.get_page_size())
        )

        # Apply the new scroll position
        vadj.set_value(new_value)

        # Return True to stop event propagation
        return True

    def load_video(self, file_path):
        """Load video metadata and extract the first frame"""
        if not file_path or not os.path.exists(file_path):
            print(f"Cannot load video - invalid path: {file_path}")
            return False

        # Double-check we're loading the right video
        if file_path != self.requested_video_path:
            print(
                f"Video path mismatch: requested={self.requested_video_path}, loading={file_path}"
            )
            return False

        # Force a re-request of this video after a short delay if it fails
        self.current_requested_file = file_path

        # Update the UI with the file path - set this early to prevent race conditions
        self.current_video_path = file_path

        # Get video duration and dimensions using FFmpeg
        try:
            # Run FFprobe to get video metadata
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                file_path,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)

            # Find the video stream
            video_stream = None
            for stream in info.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break

            if not video_stream:
                print("Error: No video stream found")
                return False

            # Get video dimensions
            self.video_width = int(video_stream.get("width", 0))
            self.video_height = int(video_stream.get("height", 0))

            # Get video duration (in seconds)
            duration_str = video_stream.get("duration") or info.get("format", {}).get(
                "duration"
            )
            if duration_str:
                self.video_duration = float(duration_str)
            else:
                # If duration not available, estimate it from bitrate and filesize
                format_info = info.get("format", {})
                if "size" in format_info and "bit_rate" in format_info:
                    size_bytes = float(format_info["size"])
                    bit_rate = float(format_info["bit_rate"])
                    self.video_duration = (size_bytes * 8) / bit_rate

            # Update position slider range
            self.position_scale.set_range(0, self.video_duration)

            # Get FPS info
            fps = video_stream.get("avg_frame_rate", "unknown").split("/")
            if len(fps) == 2 and int(fps[1]) != 0:
                fps_value = round(int(fps[0]) / int(fps[1]), 2)
                # Store fps for frame calculations
                self.video_fps = fps_value
            else:
                fps_value = "unknown"
                self.video_fps = 25  # Default to 25fps if unknown

            # Get file size and format it
            file_size_bytes = 0
            try:
                file_size_bytes = int(info.get("format", {}).get("size", 0))
            except (ValueError, TypeError):
                file_size_bytes = os.path.getsize(file_path)

            # Format file size
            if file_size_bytes < 1024:
                file_size_str = f"{file_size_bytes} B"
            elif file_size_bytes < 1024 * 1024:
                file_size_str = f"{file_size_bytes / 1024:.2f} KB"
            elif file_size_bytes < 1024 * 1024 * 1024:
                file_size_str = f"{file_size_bytes / (1024 * 1024):.2f} MB"
            else:
                file_size_str = f"{file_size_bytes / (1024 * 1024 * 1024):.2f} GB"

            # Format duration in a more readable way
            hours = int(self.video_duration // 3600)
            minutes = int((self.video_duration % 3600) // 60)
            seconds = int(self.video_duration % 60)

            if hours > 0:
                duration_str = f"{hours}h {minutes}m {seconds}s"
            else:
                duration_str = f"{minutes}m {seconds}s"

            # Update all info labels
            filename = os.path.basename(file_path)
            self.info_filename_label.set_text(filename)
            self.info_dimensions_label.set_text(
                f"{self.video_width}×{self.video_height}"
            )
            self.info_codec_label.set_text(video_stream.get("codec_name", "unknown"))

            # Get and display format_long_name
            format_info = info.get("format", {})
            format_long_name = format_info.get("format_long_name", "Unknown format")
            self.info_format_label.set_text(format_long_name)

            self.info_filesize_label.set_text(file_size_str)
            self.info_duration_label.set_text(duration_str)
            self.info_fps_label.set_text(f"{fps_value} fps")

            # Initialize crop dimensions to 0 (no cropping)
            self.crop_left = 0
            self.crop_right = 0
            self.crop_top = 0
            self.crop_bottom = 0
            self.update_crop_spinbuttons()

            # Reset trim points
            self.start_time = 0
            self.end_time = self.video_duration
            self.update_trim_display()

            # Set current position to middle of video for better initial preview
            # (first frame is often black or blank)
            self.current_position = self.video_duration / 2

            # Update slider to middle position
            self.position_scale.set_value(self.current_position)

            # Extract a frame from the middle of the video
            self.extract_frame(self.current_position)

            return True

        except Exception as e:
            print(f"Error getting video info: {e}")
            import traceback

            traceback.print_exc()
            # Clear current_video_path on failure
            self.current_video_path = None
            self.loading_video = False  # Ensure loading flag is reset on error
            return False

    def extract_frame(self, position):
        """Extract a frame at the specified position using FFmpeg directly to memory"""
        if not self.current_video_path:
            print("Cannot extract frame - no video loaded")
            return None

        # Ensure we're extracting frames from the correct video
        if (
            self.current_video_path != self.requested_video_path
            and self.requested_video_path is not None
        ):
            print(
                f"Warning: Video path mismatch when extracting frame: current={self.current_video_path}, requested={self.requested_video_path}"
            )

        try:
            # Validate position is within valid range
            safe_end = max(0, self.video_duration - 0.1)
            if position >= safe_end:
                position = safe_end
                # Update current_position and slider without triggering events
                self.current_position = position
                if hasattr(self, "position_scale") and hasattr(
                    self, "position_changed_handler_id"
                ):
                    self.position_scale.handler_block(self.position_changed_handler_id)
                    self.position_scale.set_value(position)
                    self.position_scale.handler_unblock(
                        self.position_changed_handler_id
                    )

            # Build filter string for FFmpeg
            filters = []

            # Add crop filter if needed
            if (
                self.crop_left > 0
                or self.crop_right > 0
                or self.crop_top > 0
                or self.crop_bottom > 0
            ):
                crop_width = self.video_width - self.crop_left - self.crop_right
                crop_height = self.video_height - self.crop_top - self.crop_bottom
                filters.append(
                    f"crop={crop_width}:{crop_height}:{self.crop_left}:{self.crop_top}"
                )

            # Add hue adjustment
            if self.hue != 0.0:
                hue_degrees = self.hue * 180 / 3.14159
                filters.append(f"hue=h={hue_degrees}")

            # Add exposure adjustment
            if self.exposure != 0.0:
                filters.append(f"exposure=exposure={self.exposure}")

            # Add color adjustments
            eq_parts = []
            if self.brightness != 0:
                eq_parts.append(f"brightness={self.brightness}")
            if self.contrast != 1.0:
                ff_contrast = (self.contrast - 1.0) * 2
                eq_parts.append(f"contrast={ff_contrast}")
            if self.saturation != 1.0:
                eq_parts.append(f"saturation={self.saturation}")
            if self.gamma != 1.0:
                eq_parts.append(f"gamma={self.gamma}")
            if self.gamma_r != 1.0:
                eq_parts.append(f"gamma_r={self.gamma_r}")
            if self.gamma_g != 1.0:
                eq_parts.append(f"gamma_g={self.gamma_g}")
            if self.gamma_b != 1.0:
                eq_parts.append(f"gamma_b={self.gamma_b}")
            if self.gamma_weight != 1.0:
                eq_parts.append(f"gamma_weight={self.gamma_weight}")

            if eq_parts:
                filters.append("eq=" + ":".join(eq_parts))

            filter_arg = ",".join(filters) if filters else "null"

            # Optimized FFmpeg command - using MJPEG which is faster to encode/decode than PNG
            cmd = [
                "ffmpeg",
                "-loglevel",
                "error",  # Reduce log output for performance
                "-ss",
                str(position),
                "-i",
                self.current_video_path,
                "-vf",
                filter_arg,
                "-vframes",
                "1",
                "-c:v",
                "mjpeg",  # Use MJPEG instead of PNG - much faster
                "-q:v",
                "3",  # Quality setting (1-31, lower is better)
                "-f",
                "image2pipe",
                "-",
            ]

            # Execute FFmpeg directly and capture output
            process = subprocess.run(cmd, capture_output=True, check=False)

            if process.returncode != 0:
                print(
                    f"FFmpeg error: {process.stderr.decode('utf-8', errors='replace')}"
                )
                return False

            # Create a memory input stream directly from the stdout bytes
            if process.stdout:
                # Convert the byte data directly to a memory stream
                input_stream = Gio.MemoryInputStream.new_from_bytes(
                    GLib.Bytes.new(process.stdout)
                )

                # Create a pixbuf from the stream first
                pixbuf = GdkPixbuf.Pixbuf.new_from_stream(input_stream, None)

                # Then create a texture from the pixbuf
                texture = Gdk.Texture.new_for_pixbuf(pixbuf)

                # Set the image in the UI
                self.preview_image.set_paintable(texture)

                # Update position tracking
                self.current_position = position
                self.update_position_display(position)
                self.update_frame_counter(position)

                return True
            else:
                print("Error: No image data received from ffmpeg")
                return False

        except Exception as e:
            print(f"Error extracting frame: {e}")
            import traceback

            traceback.print_exc()
            return False

    def invalidate_current_frame_cache(self):
        """Invalidate the cache for the current position - no longer needed"""
        # This is now a no-op since we're not caching frames
        pass

    def update_position_display(self, position):
        """Update position display with milliseconds"""
        self.position_label.set_text(
            f"{self.format_time(position)} / {self.format_time(self.video_duration)}"
        )
        # Calculate and update frame number
        self.update_frame_counter(position)

    def on_extract_frame(self, button):
        """Extract current frame and save it to a file"""
        if not self.current_video_path:
            return

        # Ask user for a location to save the frame
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Save Frame As"))
        dialog.set_initial_name(f"frame_{int(self.current_position)}.jpg")
        dialog.save(callback=self.on_save_frame_response)

    def on_save_frame_response(self, dialog, result):
        """Handle save frame dialog response"""
        try:
            file = dialog.save_finish(result)
            if file:
                file_path = file.get_path()

                # Create filter string for FFmpeg
                filters = []

                # Add crop filter if any crop value is non-zero
                if (
                    self.crop_left > 0
                    or self.crop_right > 0
                    or self.crop_top > 0
                    or self.crop_bottom > 0
                ):
                    # Calculate crop dimensions directly from crop values
                    crop_width = self.video_width - self.crop_left - self.crop_right
                    crop_height = self.video_height - self.crop_top - self.crop_bottom
                    filters.append(
                        f"crop={crop_width}:{crop_height}:{self.crop_left}:{self.crop_top}"
                    )

                # Add color adjustments
                eq_parts = []
                if self.brightness != 0:
                    eq_parts.append(f"brightness={self.brightness}")

                if self.contrast != 1.0:
                    ff_contrast = (self.contrast - 1.0) * 2
                    eq_parts.append(f"contrast={ff_contrast}")

                if self.saturation != 1.0:
                    eq_parts.append(f"saturation={self.saturation}")

                if eq_parts:
                    filters.append("eq=" + ":".join(eq_parts))

                filter_arg = ",".join(filters) if filters else "null"

                # High quality export
                cmd = [
                    "ffmpeg",
                    "-y",  # Don't include -v quiet to see errors
                    "-ss",
                    str(self.current_position),
                    "-i",
                    self.current_video_path,
                    "-vf",
                    filter_arg,
                    "-vframes",
                    "1",
                    "-q:v",
                    "1",  # Highest quality
                    file_path,
                ]

                # Run FFmpeg
                print(f"Executing save frame: {' '.join(cmd)}")
                result = subprocess.run(
                    cmd, capture_output=True, text=True, check=False
                )

                if result.returncode == 0 and os.path.exists(file_path):
                    # Notify user
                    self.app.show_info_dialog(
                        _("Frame Saved"),
                        _("Current frame has been saved to {0}").format(file_path),
                    )
                else:
                    error_msg = result.stderr if result.stderr else "Unknown error"
                    self.app.show_error_dialog(
                        _("Error saving frame: {0}").format(error_msg)
                    )

        except GLib.Error as error:
            print(f"Error saving frame: {error.message}")
            self.app.show_error_dialog(
                _("Error saving frame: {0}").format(error.message)
            )

    def on_position_changed(self, scale):
        """Handle position slider changes"""
        position = scale.get_value()
        if position != self.current_position:
            self.extract_frame(position)

    def seek_relative(self, seconds):
        """Seek forward or backward by the given number of seconds"""
        if not self.current_video_path:
            return

        # Calculate target position
        target = max(0, min(self.current_position + seconds, self.video_duration))

        # Update slider - this will trigger the position_changed handler
        self.position_scale.set_value(target)

    def format_time(self, seconds):
        """Format time in seconds to MM:SS.mmm format"""
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        milliseconds = int((seconds - int(seconds)) * 1000)
        return f"{minutes}:{secs:02d}.{milliseconds:03d}"

    def on_set_start_time(self, button):
        """Set current position as start time"""
        if not self.current_video_path:
            return

        # Set start time to current position
        self.start_time = self.current_position
        self.update_trim_display()

    def on_set_end_time(self, button):
        """Set current position as end time"""
        if not self.current_video_path:
            return

        # Set end time to current position
        self.end_time = self.current_position
        self.update_trim_display()

    def on_reset_trim_points(self, button):
        """Reset trim points to beginning and end of video"""
        self.start_time = 0
        self.end_time = self.video_duration if self.video_duration > 0 else None
        self.update_trim_display()

    def update_trim_display(self):
        """Update the display of trim points and duration"""
        # Update start time display
        self.start_time_label.set_text(self.format_time(self.start_time))

        # Update end time display
        if self.end_time is not None:
            self.end_time_label.set_text(self.format_time(self.end_time))
        else:
            self.end_time_label.set_text(_("End of video"))

        # Calculate and update trim duration
        if self.end_time is not None:
            trim_duration = self.end_time - self.start_time
            # Ensure duration is not negative
            if trim_duration < 0:
                trim_duration = 0
                self.end_time = self.start_time
                self.end_time_label.set_text(self.format_time(self.end_time))
        else:
            trim_duration = self.video_duration - self.start_time

        self.duration_label.set_text(self.format_time(trim_duration))

    def cleanup(self):
        """Clean up resources when the page is destroyed"""
        # Cancel any pending crop update
        if hasattr(self, "crop_update_timeout_id") and self.crop_update_timeout_id:
            GLib.source_remove(self.crop_update_timeout_id)
            self.crop_update_timeout_id = None

        # Clear any update timers
        if hasattr(self, "position_update_id") and self.position_update_id:
            GLib.source_remove(self.position_update_id)
            self.position_update_id = None

    def set_crop_visibility(self, visible=True):
        """Show or hide crop functionality - optimized version"""
        # Fast direct lookup by title
        for child in (
            self.page.get_first_child()
            .get_first_child()
            .get_first_child()
            .get_child()
            .get_children()
        ):
            if isinstance(child, Adw.PreferencesGroup):
                if child.get_title() == _("Crop"):  # Match actual title used
                    # Hide crop section completely for faster loading
                    child.set_visible(visible)
                    break

    def on_crop_value_changed(self, widget):
        """Handle changes to crop spinbutton values with delayed update"""
        # Store the new crop values directly
        self.crop_left = int(self.crop_left_spin.get_value())
        self.crop_right = int(self.crop_right_spin.get_value())
        self.crop_top = int(self.crop_top_spin.get_value())
        self.crop_bottom = int(self.crop_bottom_spin.get_value())

        # Save to GSettings
        self.settings.set_int("preview-crop-left", self.crop_left)
        self.settings.set_int("preview-crop-right", self.crop_right)
        self.settings.set_int("preview-crop-top", self.crop_top)
        self.settings.set_int("preview-crop-bottom", self.crop_bottom)

        # Calculate the resulting dimensions
        crop_width = self.video_width - self.crop_left - self.crop_right
        crop_height = self.video_height - self.crop_top - self.crop_bottom

        # Update the result size label immediately
        self.crop_result_label.set_markup(
            f"<small>{_('Final size')}: {crop_width}×{crop_height}</small>"
        )

        # Cancel any existing timeout to avoid multiple updates
        if self.crop_update_timeout_id:
            GLib.source_remove(self.crop_update_timeout_id)

        # Set a new timeout for 1 second
        self.crop_update_timeout_id = GLib.timeout_add(300, self._delayed_crop_update)

    def _delayed_crop_update(self):
        """Handle the delayed update after crop values have changed"""
        # Clear the timeout ID since it has completed
        self.crop_update_timeout_id = None

        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()

        # Refresh the preview with the new crop settings
        self.extract_frame(self.current_position)

        # Return False to ensure the timer doesn't repeat
        return False

    def reset_crop_value(self, position):
        """Reset a specific crop value to 0"""
        if position == "left":
            self.crop_left = 0
            self.settings.set_int("preview-crop-left", 0)
            self.crop_left_spin.set_value(self.crop_left)
        elif position == "right":
            self.crop_right = 0
            self.settings.set_int("preview-crop-right", 0)
            self.crop_right_spin.set_value(self.crop_right)
        elif position == "top":
            self.crop_top = 0
            self.settings.set_int("preview-crop-top", 0)
            self.crop_top_spin.set_value(self.crop_top)
        elif position == "bottom":
            self.crop_bottom = 0
            self.settings.set_int("preview-crop-bottom", 0)
            self.crop_bottom_spin.set_value(self.crop_bottom)

    def update_crop_spinbuttons(self):
        """Update the spinbuttons with current crop values - simplified"""
        # Set values directly
        self.crop_left_spin.set_value(self.crop_left)
        self.crop_right_spin.set_value(self.crop_right)
        self.crop_top_spin.set_value(self.crop_top)
        self.crop_bottom_spin.set_value(self.crop_bottom)

        # Update the result size label
        crop_width = self.video_width - self.crop_left - self.crop_right
        crop_height = self.video_height - self.crop_top - self.crop_bottom
        self.crop_result_label.set_markup(
            f"<small>{_('Final size')}: {crop_width}×{crop_height}</small>"
        )

    def on_brightness_changed(self, scale, value_label=None):
        """Handle brightness slider changes"""
        self.brightness = scale.get_value()

        # Save to GSettings
        self.settings.set_double("preview-brightness", self.brightness)

        if value_label:
            value_label.set_text(f"{self.brightness:.1f}")

        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()

        # Update current frame with new settings
        self.extract_frame(self.current_position)

    def on_contrast_changed(self, scale, value_label=None):
        """Handle contrast slider changes"""
        self.contrast = scale.get_value()

        # Save to GSettings
        self.settings.set_double("preview-contrast", self.contrast)

        if value_label:
            value_label.set_text(f"{self.contrast:.1f}")

        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()

        # Update current frame with new settings
        self.extract_frame(self.current_position)

    def on_saturation_changed(self, scale, value_label=None):
        """Handle saturation slider changes"""
        self.saturation = scale.get_value()

        # Save to GSettings
        self.settings.set_double("preview-saturation", self.saturation)

        if value_label:
            value_label.set_text(f"{self.saturation:.1f}")

        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()

        # Update current frame with new settings
        self.extract_frame(self.current_position)

    def reset_brightness(self):
        """Reset brightness to default"""
        # Default brightness is 0.0
        self.settings.set_double("preview-brightness", 0.0)
        self.brightness = 0.0
        self.brightness_scale.set_value(self.brightness)
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def reset_contrast(self):
        """Reset contrast to default"""
        # Default contrast is 1.0
        self.settings.set_double("preview-contrast", 1.0)
        self.contrast = 1.0
        self.contrast_scale.set_value(self.contrast)
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def reset_saturation(self):
        """Reset saturation to default"""
        # Default saturation is 1.0
        self.settings.set_double("preview-saturation", 1.0)
        self.saturation = 1.0
        self.saturation_scale.set_value(self.saturation)
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def show_error(self, message):
        """Show an error message"""
        print(f"Error: {message}")
        self.position_label.set_text(f"Error: {message}")

    def update_frame_counter(self, position):
        """Update the frame counter label based on the position"""
        # Estimate current frame number based on position and framerate
        # Default to 25fps if unknown
        fps = 25
        # Try to get fps from video info
        if hasattr(self, "video_fps") and self.video_fps > 0:
            fps = self.video_fps

        current_frame = (
            int(position * fps) + 1
        )  # +1 because frames typically count from 1
        total_frames = int(self.video_duration * fps)

        self.frame_label.set_text(f"Frame: {current_frame}/{total_frames}")

    # Add handlers for new adjustments
    def on_gamma_changed(self, scale, value_label=None):
        """Handle gamma slider changes"""
        self.gamma = scale.get_value()
        self.settings.set_double("preview-gamma", self.gamma)
        if value_label:
            value_label.set_text(f"{self.gamma:.1f}")
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def on_gamma_r_changed(self, scale, value_label=None):
        """Handle red gamma slider changes"""
        self.gamma_r = scale.get_value()
        self.settings.set_double("preview-gamma-r", self.gamma_r)
        if value_label:
            value_label.set_text(f"{self.gamma_r:.1f}")
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def on_gamma_g_changed(self, scale, value_label=None):
        """Handle green gamma slider changes"""
        self.gamma_g = scale.get_value()
        self.settings.set_double("preview-gamma-g", self.gamma_g)
        if value_label:
            value_label.set_text(f"{self.gamma_g:.1f}")
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def on_gamma_b_changed(self, scale, value_label=None):
        """Handle blue gamma slider changes"""
        self.gamma_b = scale.get_value()
        self.settings.set_double("preview-gamma-b", self.gamma_b)
        if value_label:
            value_label.set_text(f"{self.gamma_b:.1f}")
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def on_gamma_weight_changed(self, scale, value_label=None):
        """Handle gamma weight slider changes"""
        self.gamma_weight = scale.get_value()
        self.settings.set_double("preview-gamma-weight", self.gamma_weight)
        if value_label:
            value_label.set_text(f"{self.gamma_weight:.2f}")
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def on_hue_changed(self, scale, value_label=None):
        """Handle hue slider changes"""
        self.hue = scale.get_value()
        self.settings.set_double("preview-hue", self.hue)
        if value_label:
            value_label.set_text(f"{self.hue:.2f}")
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def on_exposure_changed(self, scale, value_label=None):
        """Handle exposure slider changes"""
        self.exposure = scale.get_value()
        self.settings.set_double("preview-exposure", self.exposure)
        if value_label:
            value_label.set_text(f"{self.exposure:.1f}")
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    # Add reset functions for new adjustments
    def reset_gamma(self):
        """Reset gamma to default"""
        # Default gamma is 1.0
        self.settings.set_double("preview-gamma", 1.0)
        self.gamma = 1.0
        self.gamma_scale.set_value(self.gamma)
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def reset_gamma_r(self):
        """Reset red gamma to default"""
        # Default gamma_r is 1.0
        self.settings.set_double("preview-gamma-r", 1.0)
        self.gamma_r = 1.0
        self.gamma_r_scale.set_value(self.gamma_r)
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def reset_gamma_g(self):
        """Reset green gamma to default"""
        # Default gamma_g is 1.0
        self.settings.set_double("preview-gamma-g", 1.0)
        self.gamma_g = 1.0
        self.gamma_g_scale.set_value(self.gamma_g)
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def reset_gamma_b(self):
        """Reset blue gamma to default"""
        # Default gamma_b is 1.0
        self.settings.set_double("preview-gamma-b", 1.0)
        self.gamma_b = 1.0
        self.gamma_b_scale.set_value(self.gamma_b)
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def reset_gamma_weight(self):
        """Reset gamma weight to default"""
        # Default gamma_weight is 1.0
        self.settings.set_double("preview-gamma-weight", 1.0)
        self.gamma_weight = 1.0
        self.gamma_weight_scale.set_value(self.gamma_weight)
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def reset_hue(self):
        """Reset hue to default"""
        # Default hue is 0.0
        self.settings.set_double("preview-hue", 0.0)
        self.hue = 0.0
        self.hue_scale.set_value(self.hue)
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def reset_exposure(self):
        """Reset exposure to default"""
        # Default exposure is 0.0
        self.settings.set_double("preview-exposure", 0.0)
        self.exposure = 0.0
        self.exposure_scale.set_value(self.exposure)
        # Invalidate cache for current position before extracting new frame
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

    def on_slider_motion(self, controller, x, y):
        """Show tooltip for timeline slider using direct GtkGizmo handling"""
        if self.video_duration <= 0:
            return

        # Calculate hover time directly using the GtkGizmo approach
        hover_time = self.get_slider_value_at_position(self.position_scale, x)

        # Snap to frame boundaries if possible
        if hasattr(self, "video_fps") and self.video_fps > 0:
            frame_time = 1.0 / self.video_fps
            frame = round(hover_time / frame_time)
            hover_time = frame * frame_time

        # Update tooltip
        tooltip_text = self.format_time_precise(hover_time)
        self.tooltip_label.set_text(tooltip_text)

        # Position tooltip
        rect = Gdk.Rectangle()
        rect.x = x
        rect.y = 0
        rect.width = 1
        rect.height = 1

        self.tooltip_popover.set_pointing_to(rect)
        self.tooltip_popover.set_parent(self.position_scale)
        self.tooltip_popover.popup()

        # Store hover position
        self.hover_position = hover_time

    def on_slider_click(self, gesture, n_press, x, y):
        """Jump to position when slider is clicked - using same GtkGizmo handling"""
        if self.video_duration <= 0 or n_press != 1:
            return

        # Calculate click time using the same GtkGizmo approach for consistency
        click_time = self.get_slider_value_at_position(self.position_scale, x)

        # Snap to frame boundaries
        if hasattr(self, "video_fps") and self.video_fps > 0:
            frame_time = 1.0 / self.video_fps
            frame = round(click_time / frame_time)
            click_time = frame * frame_time

        # Set position - this will trigger on_position_changed
        self.position_scale.set_value(click_time)

    def format_time_precise(self, seconds):
        """Format time with precision appropriate to video duration"""
        hours = int(seconds) // 3600
        minutes = (int(seconds) % 3600) // 60
        secs = int(seconds) % 60

        # For short videos, show milliseconds for more precision
        if self.video_duration < 60:
            milliseconds = int((seconds - int(seconds)) * 1000)
            if hours > 0:
                return f"{hours}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"
            else:
                return f"{minutes}:{secs:02d}.{milliseconds:03d}"
        # For medium length videos, show 2 decimal places
        elif self.video_duration < 600:  # Less than 10 minutes
            decimal_secs = seconds % 60
            if hours > 0:
                return f"{hours}:{minutes:02d}:{decimal_secs:05.2f}"
            else:
                return f"{minutes}:{decimal_secs:05.2f}"
        # For longer videos, just show whole seconds
        else:
            if hours > 0:
                return f"{hours}:{minutes:02d}:{secs:02d}"
            else:
                return f"{minutes}:{secs:02d}"

    def on_slider_leave(self, controller):
        """Hide tooltip when mouse leaves the timeline slider"""
        # Hide the tooltip popover when mouse leaves the slider
        if hasattr(self, "tooltip_popover"):
            self.tooltip_popover.popdown()

    def on_reset_all_settings(self, button):
        """Show confirmation dialog before resetting all settings"""
        # Create dialog first, then set properties
        dialog = Adw.MessageDialog()
        dialog.set_heading(_("Reset All Settings"))
        dialog.set_body(
            _(
                "Are you sure you want to reset all video editing settings to their default values?"
            )
        )

        # Set parent window properly
        if hasattr(self.app, "get_active_window") and callable(
            self.app.get_active_window
        ):
            parent_window = self.app.get_active_window()
            if parent_window:
                dialog.set_transient_for(parent_window)

        # Add cancel button
        dialog.add_response("cancel", _("Cancel"))
        dialog.set_response_appearance("cancel", Adw.ResponseAppearance.DEFAULT)

        # Add confirm button
        dialog.add_response("reset", _("Reset"))
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)

        # Set default response
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        # Connect response handler
        dialog.connect("response", self._on_reset_confirmed)

        # Show dialog
        dialog.present()

    def _on_reset_confirmed(self, dialog, response):
        """Handle the response from the reset confirmation dialog"""
        if response != "reset":
            # User canceled the operation
            return

        # User confirmed, proceed with reset
        self._perform_reset_all_settings()

    def _perform_reset_all_settings(self):
        """Reset all video settings to their default values"""
        # Reset crop values
        self.crop_left = 0
        self.crop_right = 0
        self.crop_top = 0
        self.crop_bottom = 0

        # Update settings
        self.settings.set_int("preview-crop-left", 0)
        self.settings.set_int("preview-crop-right", 0)
        self.settings.set_int("preview-crop-top", 0)
        self.settings.set_int("preview-crop-bottom", 0)

        # Update spinbuttons
        self.crop_left_spin.set_value(0)
        self.crop_right_spin.set_value(0)
        self.crop_top_spin.set_value(0)
        self.crop_bottom_spin.set_value(0)

        # Reset adjustment values
        self.brightness = 0.0
        self.contrast = 1.0
        self.saturation = 1.0
        self.gamma = 1.0
        self.gamma_r = 1.0
        self.gamma_g = 1.0
        self.gamma_b = 1.0
        self.gamma_weight = 1.0
        self.hue = 0.0
        self.exposure = 0.0

        # Update settings
        self.settings.set_double("preview-brightness", 0.0)
        self.settings.set_double("preview-contrast", 1.0)
        self.settings.set_double("preview-saturation", 1.0)
        self.settings.set_double("preview-gamma", 1.0)
        self.settings.set_double("preview-gamma-r", 1.0)
        self.settings.set_double("preview-gamma-g", 1.0)
        self.settings.set_double("preview-gamma-b", 1.0)
        self.settings.set_double("preview-gamma-weight", 1.0)
        self.settings.set_double("preview-hue", 0.0)
        self.settings.set_double("preview-exposure", 0.0)

        # Update slider values
        self.brightness_scale.set_value(0.0)
        self.contrast_scale.set_value(1.0)
        self.saturation_scale.set_value(1.0)
        self.gamma_scale.set_value(1.0)
        self.gamma_r_scale.set_value(1.0)
        self.gamma_g_scale.set_value(1.0)
        self.gamma_b_scale.set_value(1.0)
        self.gamma_weight_scale.set_value(1.0)
        self.hue_scale.set_value(0.0)
        self.exposure_scale.set_value(0.0)

        # Reset trim points
        self.start_time = 0
        if self.video_duration > 0:
            self.end_time = self.video_duration
        self.update_trim_display()

        # Invalidate cache and update preview
        self.invalidate_current_frame_cache()
        self.extract_frame(self.current_position)

        # Show success message
        self.app.show_info_dialog(
            _("Settings Reset"),
            _("All video editing settings have been reset to their default values."),
        )
