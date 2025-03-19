import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gdk

# Setup translation
import gettext

_ = gettext.gettext


class VideoEditHandlers:
    def __init__(self, page):
        self.page = page

    def on_position_changed(self, scale):
        """Handle position slider changes"""
        position = scale.get_value()
        if position != self.page.current_position:
            self.page.processor.extract_frame(position)

    def seek_relative(self, seconds):
        """Seek forward or backward by the given number of seconds"""
        if not self.page.current_video_path:
            return

        # Calculate target position
        target = max(
            0, min(self.page.current_position + seconds, self.page.video_duration)
        )

        # Update slider - this will trigger the position_changed handler
        self.page.ui.position_scale.set_value(target)

    def update_position_display(self, position):
        """Update position display with milliseconds"""
        self.page.ui.position_label.set_text(
            f"{self.format_time(position)} / {self.format_time(self.page.video_duration)}"
        )
        # Calculate and update frame number
        self.update_frame_counter(position)

    def format_time(self, seconds):
        """Format time in seconds to MM:SS.mmm format"""
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        milliseconds = int((seconds - int(seconds)) * 1000)
        return f"{minutes}:{secs:02d}.{milliseconds:03d}"

    def format_time_precise(self, seconds):
        """Format time with precision appropriate to video duration"""
        hours = int(seconds) // 3600
        minutes = (int(seconds) % 3600) // 60
        secs = int(seconds) % 60

        # For short videos, show milliseconds for more precision
        if self.page.video_duration < 60:
            milliseconds = int((seconds - int(seconds)) * 1000)
            if hours > 0:
                return f"{hours}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"
            else:
                return f"{minutes}:{secs:02d}.{milliseconds:03d}"
        # For medium length videos, show 2 decimal places
        elif self.page.video_duration < 600:  # Less than 10 minutes
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

    def on_set_start_time(self, button):
        """Set current position as start time"""
        if not self.page.current_video_path:
            return

        # Set start time to current position
        self.page.start_time = self.page.current_position
        self.update_trim_display()

    def on_set_end_time(self, button):
        """Set current position as end time"""
        if not self.page.current_video_path:
            return

        # Set end time to current position
        self.page.end_time = self.page.current_position
        self.update_trim_display()

    def on_reset_trim_points(self, button):
        """Reset trim points to beginning and end of video"""
        self.page.start_time = 0
        self.page.end_time = (
            self.page.video_duration if self.page.video_duration > 0 else None
        )
        self.update_trim_display()

    def update_trim_display(self):
        """Update the display of trim points and duration"""
        # Update start time display
        self.page.ui.start_time_label.set_text(self.format_time(self.page.start_time))

        # Update end time display
        if self.page.end_time is not None:
            self.page.ui.end_time_label.set_text(self.format_time(self.page.end_time))
        else:
            self.page.ui.end_time_label.set_text(_("End of video"))

        # Calculate and update trim duration
        if self.page.end_time is not None:
            trim_duration = self.page.end_time - self.page.start_time
            # Ensure duration is not negative
            if trim_duration < 0:
                trim_duration = 0
                self.page.end_time = self.page.start_time
                self.page.ui.end_time_label.set_text(
                    self.format_time(self.page.end_time)
                )
        else:
            trim_duration = self.page.video_duration - self.page.start_time

        self.page.ui.duration_label.set_text(self.format_time(trim_duration))

    def update_crop_spinbuttons(self):
        """Update the spinbuttons with current crop values"""
        # Set values directly
        self.page.ui.crop_left_spin.set_value(self.page.crop_left)
        self.page.ui.crop_right_spin.set_value(self.page.crop_right)
        self.page.ui.crop_top_spin.set_value(self.page.crop_top)
        self.page.ui.crop_bottom_spin.set_value(self.page.crop_bottom)

        # Update the result size label
        crop_width = self.page.video_width - self.page.crop_left - self.page.crop_right
        crop_height = (
            self.page.video_height - self.page.crop_top - self.page.crop_bottom
        )
        self.page.ui.crop_result_label.set_markup(
            f"<small>{_('Final size')}: {crop_width}×{crop_height}</small>"
        )

    def on_crop_value_changed(self, widget):
        """Handle changes to crop spinbutton values with delayed update"""
        # Store the new crop values directly
        self.page.crop_left = int(self.page.ui.crop_left_spin.get_value())
        self.page.crop_right = int(self.page.ui.crop_right_spin.get_value())
        self.page.crop_top = int(self.page.ui.crop_top_spin.get_value())
        self.page.crop_bottom = int(self.page.ui.crop_bottom_spin.get_value())

        # Save to GSettings
        self.page.settings.set_int("preview-crop-left", self.page.crop_left)
        self.page.settings.set_int("preview-crop-right", self.page.crop_right)
        self.page.settings.set_int("preview-crop-top", self.page.crop_top)
        self.page.settings.set_int("preview-crop-bottom", self.page.crop_bottom)

        # Calculate the resulting dimensions
        crop_width = self.page.video_width - self.page.crop_left - self.page.crop_right
        crop_height = (
            self.page.video_height - self.page.crop_top - self.page.crop_bottom
        )

        # Update the result size label immediately
        self.page.ui.crop_result_label.set_markup(
            f"<small>{_('Final size')}: {crop_width}×{crop_height}</small>"
        )

        # Cancel any existing timeout to avoid multiple updates
        if self.page.crop_update_timeout_id:
            GLib.source_remove(self.page.crop_update_timeout_id)

        # Set a new timeout for 300ms
        self.page.crop_update_timeout_id = GLib.timeout_add(
            300, self._delayed_crop_update
        )

    def _delayed_crop_update(self):
        """Handle the delayed update after crop values have changed"""
        # Clear the timeout ID since it has completed
        self.page.crop_update_timeout_id = None

        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()

        # Refresh the preview with the new crop settings
        self.page.processor.extract_frame(self.page.current_position)

        # Return False to ensure the timer doesn't repeat
        return False

    def reset_crop_value(self, position):
        """Reset a specific crop value to 0"""
        if position == "left":
            self.page.crop_left = 0
            self.page.settings.set_int("preview-crop-left", 0)
            self.page.ui.crop_left_spin.set_value(self.page.crop_left)
        elif position == "right":
            self.page.crop_right = 0
            self.page.settings.set_int("preview-crop-right", 0)
            self.page.ui.crop_right_spin.set_value(self.page.crop_right)
        elif position == "top":
            self.page.crop_top = 0
            self.page.settings.set_int("preview-crop-top", 0)
            self.page.ui.crop_top_spin.set_value(self.page.crop_top)
        elif position == "bottom":
            self.page.crop_bottom = 0
            self.page.settings.set_int("preview-crop-bottom", 0)
            self.page.ui.crop_bottom_spin.set_value(self.page.crop_bottom)

    # Video adjustment handlers
    def on_brightness_changed(self, scale, value_label=None):
        """Handle brightness slider changes"""
        self.page.brightness = scale.get_value()
        self.page.settings.set_double("preview-brightness", self.page.brightness)
        if value_label:
            value_label.set_text(f"{self.page.brightness:.1f}")
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        # Update current frame with new settings
        self.page.processor.extract_frame(self.page.current_position)

    def on_contrast_changed(self, scale, value_label=None):
        """Handle contrast slider changes"""
        self.page.contrast = scale.get_value()
        self.page.settings.set_double("preview-contrast", self.page.contrast)
        if value_label:
            value_label.set_text(f"{self.page.contrast:.1f}")
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        # Update current frame with new settings
        self.page.processor.extract_frame(self.page.current_position)

    def on_saturation_changed(self, scale, value_label=None):
        """Handle saturation slider changes"""
        self.page.saturation = scale.get_value()
        self.page.settings.set_double("preview-saturation", self.page.saturation)
        if value_label:
            value_label.set_text(f"{self.page.saturation:.1f}")
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        # Update current frame with new settings
        self.page.processor.extract_frame(self.page.current_position)

    def on_gamma_changed(self, scale, value_label=None):
        """Handle gamma slider changes"""
        self.page.gamma = scale.get_value()
        self.page.settings.set_double("preview-gamma", self.page.gamma)
        if value_label:
            value_label.set_text(f"{self.page.gamma:.1f}")
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

    def on_gamma_r_changed(self, scale, value_label=None):
        """Handle red gamma slider changes"""
        self.page.gamma_r = scale.get_value()
        self.page.settings.set_double("preview-gamma-r", self.page.gamma_r)
        if value_label:
            value_label.set_text(f"{self.page.gamma_r:.1f}")
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

    def on_gamma_g_changed(self, scale, value_label=None):
        """Handle green gamma slider changes"""
        self.page.gamma_g = scale.get_value()
        self.page.settings.set_double("preview-gamma-g", self.page.gamma_g)
        if value_label:
            value_label.set_text(f"{self.page.gamma_g:.1f}")
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

    def on_gamma_b_changed(self, scale, value_label=None):
        """Handle blue gamma slider changes"""
        self.page.gamma_b = scale.get_value()
        self.page.settings.set_double("preview-gamma-b", self.page.gamma_b)
        if value_label:
            value_label.set_text(f"{self.page.gamma_b:.1f}")
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

    def on_gamma_weight_changed(self, scale, value_label=None):
        """Handle gamma weight slider changes"""
        self.page.gamma_weight = scale.get_value()
        self.page.settings.set_double("preview-gamma-weight", self.page.gamma_weight)
        if value_label:
            value_label.set_text(f"{self.page.gamma_weight:.2f}")
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

    def on_hue_changed(self, scale, value_label=None):
        """Handle hue slider changes"""
        self.page.hue = scale.get_value()
        self.page.settings.set_double("preview-hue", self.page.hue)
        if value_label:
            value_label.set_text(f"{self.page.hue:.2f}")
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

    # Reset functions for adjustments
    def reset_brightness(self):
        """Reset brightness to default"""
        self.page.settings.set_double("preview-brightness", 0.0)
        self.page.brightness = 0.0
        self.page.ui.brightness_scale.set_value(self.page.brightness)
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

    def reset_contrast(self):
        """Reset contrast to default"""
        self.page.settings.set_double("preview-contrast", 1.0)
        self.page.contrast = 1.0
        self.page.ui.contrast_scale.set_value(self.page.contrast)
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

    def reset_saturation(self):
        """Reset saturation to default"""
        self.page.settings.set_double("preview-saturation", 1.0)
        self.page.saturation = 1.0
        self.page.ui.saturation_scale.set_value(self.page.saturation)
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

    def reset_gamma(self):
        """Reset gamma to default"""
        self.page.settings.set_double("preview-gamma", 1.0)
        self.page.gamma = 1.0
        self.page.ui.gamma_scale.set_value(self.page.gamma)
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

    def reset_gamma_r(self):
        """Reset red gamma to default"""
        self.page.settings.set_double("preview-gamma-r", 1.0)
        self.page.gamma_r = 1.0
        self.page.ui.red_gamma_scale.set_value(self.page.gamma_r)
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

    def reset_gamma_g(self):
        """Reset green gamma to default"""
        self.page.settings.set_double("preview-gamma-g", 1.0)
        self.page.gamma_g = 1.0
        self.page.ui.green_gamma_scale.set_value(self.page.gamma_g)
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

    def reset_gamma_b(self):
        """Reset blue gamma to default"""
        self.page.settings.set_double("preview-gamma-b", 1.0)
        self.page.gamma_b = 1.0
        self.page.ui.blue_gamma_scale.set_value(self.page.gamma_b)
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

    def reset_gamma_weight(self):
        """Reset gamma weight to default"""
        self.page.settings.set_double("preview-gamma-weight", 1.0)
        self.page.gamma_weight = 1.0
        self.page.ui.gamma_weight_scale.set_value(self.page.gamma_weight)
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

    def reset_hue(self):
        """Reset hue to default"""
        self.page.settings.set_double("preview-hue", 0.0)
        self.page.hue = 0.0
        self.page.ui.hue_scale.set_value(self.page.hue)
        # Invalidate cache for current position before extracting new frame
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

    def update_frame_counter(self, position):
        """Update the frame counter label based on the position"""
        # Estimate current frame number based on position and framerate
        # Default to 25fps if unknown
        fps = 25
        # Try to get fps from video info
        if hasattr(self.page, "video_fps") and self.page.video_fps > 0:
            fps = self.page.video_fps

        current_frame = (
            int(position * fps) + 1
        )  # +1 because frames typically count from 1
        total_frames = int(self.page.video_duration * fps)

        self.page.ui.frame_label.set_text(f"Frame: {current_frame}/{total_frames}")

    # Tooltip handlers
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

    def on_slider_motion(self, controller, x, y):
        """Show tooltip for timeline slider using direct GtkGizmo handling"""
        if self.page.video_duration <= 0:
            return

        # Calculate hover time directly using the GtkGizmo approach
        hover_time = self.get_slider_value_at_position(self.page.ui.position_scale, x)

        # Snap to frame boundaries if possible
        if hasattr(self.page, "video_fps") and self.page.video_fps > 0:
            frame_time = 1.0 / self.page.video_fps
            frame = round(hover_time / frame_time)
            hover_time = frame * frame_time

        # Update tooltip
        tooltip_text = self.format_time_precise(hover_time)
        self.page.ui.tooltip_label.set_text(tooltip_text)

        # Position tooltip
        rect = Gdk.Rectangle()
        rect.x = x
        rect.y = 0
        rect.width = 1
        rect.height = 1

        self.page.ui.tooltip_popover.set_pointing_to(rect)
        self.page.ui.tooltip_popover.set_parent(self.page.ui.position_scale)
        self.page.ui.tooltip_popover.popup()

        # Store hover position
        self.page.ui.hover_position = hover_time

    def on_slider_click(self, gesture, n_press, x, y):
        """Jump to position when slider is clicked - using same GtkGizmo handling"""
        if self.page.video_duration <= 0 or n_press != 1:
            return

        # Calculate click time using the same GtkGizmo approach for consistency
        click_time = self.get_slider_value_at_position(self.page.ui.position_scale, x)

        # Snap to frame boundaries
        if hasattr(self.page, "video_fps") and self.page.video_fps > 0:
            frame_time = 1.0 / self.page.video_fps
            frame = round(click_time / frame_time)
            click_time = frame * frame_time

        # Set position - this will trigger on_position_changed
        self.page.ui.position_scale.set_value(click_time)

    def on_slider_leave(self, controller):
        """Hide tooltip when mouse leaves the timeline slider"""
        # Hide the tooltip popover when mouse leaves the slider
        if hasattr(self.page.ui, "tooltip_popover"):
            self.page.ui.tooltip_popover.popdown()

    def on_adjustment_motion(self, controller, x, y):
        """Show tooltip for sliders using direct GtkGizmo handling"""
        slider = controller.get_widget()

        # Check if we have a tooltip for this slider
        if slider not in self.page.adjustment_tooltips:
            return

        tooltip_data = self.page.adjustment_tooltips[slider]
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
        if slider in self.page.adjustment_tooltips:
            self.page.adjustment_tooltips[slider]["popover"].popdown()

    def on_button_enter(self, controller):
        """Show tooltip when mouse enters a button"""
        button = controller.get_widget()

        # Check if we have a tooltip for this button
        if button not in self.page.button_tooltips:
            return

        tooltip_data = self.page.button_tooltips[button]
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

    def on_button_leave(self, controller):
        """Hide tooltip when mouse leaves a button"""
        button = controller.get_widget()
        if button in self.page.button_tooltips:
            self.page.button_tooltips[button]["popover"].popdown()

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
        if hasattr(self.page.app, "get_active_window") and callable(
            self.page.app.get_active_window
        ):
            parent_window = self.page.app.get_active_window()
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
        self.page.crop_left = 0
        self.page.crop_right = 0
        self.page.crop_top = 0
        self.page.crop_bottom = 0

        # Update settings
        self.page.settings.set_int("preview-crop-left", 0)
        self.page.settings.set_int("preview-crop-right", 0)
        self.page.settings.set_int("preview-crop-top", 0)
        self.page.settings.set_int("preview-crop-bottom", 0)

        # Update spinbuttons
        self.page.ui.crop_left_spin.set_value(0)
        self.page.ui.crop_right_spin.set_value(0)
        self.page.ui.crop_top_spin.set_value(0)
        self.page.ui.crop_bottom_spin.set_value(0)

        # Reset adjustment values
        self.page.brightness = 0.0
        self.page.contrast = 1.0
        self.page.saturation = 1.0
        self.page.gamma = 1.0
        self.page.gamma_r = 1.0
        self.page.gamma_g = 1.0
        self.page.gamma_b = 1.0
        self.page.gamma_weight = 1.0
        self.page.hue = 0.0

        # Update settings
        self.page.settings.set_double("preview-brightness", 0.0)
        self.page.settings.set_double("preview-contrast", 1.0)
        self.page.settings.set_double("preview-saturation", 1.0)
        self.page.settings.set_double("preview-gamma", 1.0)
        self.page.settings.set_double("preview-gamma-r", 1.0)
        self.page.settings.set_double("preview-gamma-g", 1.0)
        self.page.settings.set_double("preview-gamma-b", 1.0)
        self.page.settings.set_double("preview-gamma-weight", 1.0)
        self.page.settings.set_double("preview-hue", 0.0)

        # Update slider values
        self.page.ui.brightness_scale.set_value(0.0)
        self.page.ui.contrast_scale.set_value(1.0)
        self.page.ui.saturation_scale.set_value(1.0)
        self.page.ui.gamma_scale.set_value(1.0)
        self.page.ui.red_gamma_scale.set_value(1.0)
        self.page.ui.green_gamma_scale.set_value(1.0)
        self.page.ui.blue_gamma_scale.set_value(1.0)
        self.page.ui.gamma_weight_scale.set_value(1.0)
        self.page.ui.hue_scale.set_value(0.0)

        # Reset trim points
        self.page.start_time = 0
        if self.page.video_duration > 0:
            self.page.end_time = self.page.video_duration
        self.update_trim_display()

        # Invalidate cache and update preview
        self.page.invalidate_current_frame_cache()
        self.page.processor.extract_frame(self.page.current_position)

        # Show success message
        self.page.app.show_info_dialog(
            _("Settings Reset"),
            _("All video editing settings have been reset to their default values."),
        )
