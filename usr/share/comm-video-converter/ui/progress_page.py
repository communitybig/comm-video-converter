import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango

# Setup translation
import gettext

_ = gettext.gettext


class ProgressPage:
    """
    Page to display conversion progress in the main UI.
    Manages active conversions and their progress display.
    """

    def __init__(self, app):
        self.app = app

        # Root container using Box for vertical layout
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.page.set_vexpand(True)

        # Create an overlay for proper vertical centering
        overlay = Gtk.Overlay()
        overlay.set_vexpand(True)
        self.page.append(overlay)

        # Background that fills the entire space
        background = Gtk.Box()
        background.set_vexpand(True)
        overlay.set_child(background)

        # Main content container with vertical centering
        centered_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        centered_box.set_valign(Gtk.Align.CENTER)  # Center vertically
        centered_box.set_halign(Gtk.Align.FILL)  # Fill horizontally
        overlay.add_overlay(centered_box)

        # Create a scrolled window with appropriate padding
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled_window.set_propagate_natural_height(True)  # Use natural height
        self.scrolled_window.set_max_content_height(800)  # Limit max height
        centered_box.append(self.scrolled_window)

        # Main content box - no vertical expansion to allow centering
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.main_box.set_valign(Gtk.Align.CENTER)
        self.scrolled_window.set_child(self.main_box)

        # Use Adw.Clamp for responsive width constraints
        self.clamp = Adw.Clamp()
        self.clamp.set_maximum_size(800)
        self.clamp.set_tightening_threshold(600)
        self.main_box.append(self.clamp)

        # Content box with proper GNOME margins (24px)
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content_box.set_margin_top(24)
        self.content_box.set_margin_bottom(24)
        self.content_box.set_margin_start(24)
        self.content_box.set_margin_end(24)
        self.content_box.set_spacing(24)  # GNOME typically uses multiples of 6px
        self.clamp.set_child(self.content_box)

        # Dictionary to track active conversion processes
        self.active_conversions = {}

        # Counter for conversion IDs
        self.count = 0

    def get_page(self):
        """Return the page widget"""
        return self.page

    def add_conversion(self, command_title, input_file, process):
        """Add a new conversion to be tracked on the progress page"""
        # Create a unique ID for this conversion
        conversion_id = f"conversion_{self.count}"
        self.count += 1

        # If this is the first conversion, show the progress page
        if len(self.active_conversions) == 0:
            # Switch to progress page and disable tab navigation
            self.app.show_progress_page()

        # Create a box container styled as a card for the conversion item
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.add_css_class("card")
        card.set_margin_bottom(12)

        # Create the conversion item
        conversion_item = ConversionItem(
            self.app, command_title, input_file, process, conversion_id
        )

        # Add the item to the card
        card.append(conversion_item)

        # Add the card to the content box
        self.content_box.append(card)

        # Store reference to the item and container
        self.active_conversions[conversion_id] = {
            "item": conversion_item,
            "container": card,
        }

        # Return the item for tracking
        return conversion_item

    def remove_conversion(self, conversion_id):
        """Remove a conversion from the progress page"""
        if conversion_id in self.active_conversions:
            # Get the container
            container = self.active_conversions[conversion_id]["container"]

            # Remove from the UI
            self.content_box.remove(container)

            # Remove from the dictionary
            del self.active_conversions[conversion_id]

            # If no more conversions, return to the previous page
            if len(self.active_conversions) == 0:
                self.app.return_to_previous_page()

    def has_active_conversions(self):
        """Check if there are any active conversions"""
        return len(self.active_conversions) > 0


class ConversionItem(Gtk.Box):
    """Individual conversion item widget to display progress for a single conversion"""

    def __init__(self, app, title, input_file, process, conversion_id):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        self.app = app
        self.process = process
        self.input_file = input_file
        self.delete_original = False
        self.conversion_id = conversion_id
        self.cancelled = False
        self.success = False

        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)

        # Header with filename
        file_name = title
        if input_file and os.path.exists(input_file):
            file_name = os.path.basename(input_file)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        file_label = Gtk.Label()
        file_label.set_markup(f"<b>{GLib.markup_escape_text(file_name)}</b>")
        file_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        file_label.set_halign(Gtk.Align.START)
        file_label.set_hexpand(True)
        header.append(file_label)
        self.append(header)

        # Status row
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        status_box.set_margin_top(4)
        status_box.set_margin_bottom(4)

        # Status label
        self.status_label = Gtk.Label(label=_("Starting conversion..."))
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_hexpand(True)
        self.status_label.set_wrap(True)
        self.status_label.set_xalign(0)
        status_box.append(self.status_label)

        self.append(status_box)

        # Progress bar
        progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        progress_box.set_margin_top(4)
        progress_box.set_margin_bottom(8)

        # Create progress bar with proper styling
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_text("0%")
        self.progress_bar.set_valign(Gtk.Align.CENTER)
        self.progress_bar.set_hexpand(True)
        progress_box.append(self.progress_bar)

        self.append(progress_box)

        # Terminal output in an expander
        self.terminal_expander = Gtk.Expander()
        self.terminal_expander.set_label(_("Command Output"))
        self.terminal_expander.add_css_class("heading")
        self.append(self.terminal_expander)

        # Terminal output area
        terminal_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        terminal_box.set_margin_top(8)
        terminal_box.set_margin_bottom(8)

        # Create scrolled window for the terminal
        terminal_scroll = Gtk.ScrolledWindow()
        terminal_scroll.set_min_content_height(250)

        # Create terminal-like TextView with monospace font
        self.terminal_view = Gtk.TextView()
        self.terminal_view.set_editable(False)
        self.terminal_view.set_cursor_visible(False)
        self.terminal_view.set_monospace(True)

        # Use proper font styling - remove the default monospace class that might be bold
        # and add a custom CSS class for normal weight monospace
        self.terminal_view.add_css_class("terminal-text")

        # Create and apply custom CSS provider for the terminal font
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(
            b".terminal-text { font-family: monospace; font-weight: normal; }"
        )
        self.terminal_view.get_style_context().add_provider(
            css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.terminal_buffer = self.terminal_view.get_buffer()

        # Add text view to scrolled window
        terminal_scroll.set_child(self.terminal_view)
        terminal_box.append(terminal_scroll)

        self.terminal_expander.set_child(terminal_box)

        # Bottom action area with cancel button
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        button_box.set_halign(Gtk.Align.END)
        button_box.set_margin_top(8)

        self.cancel_button = Gtk.Button(label=_("Cancel"))
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        self.cancel_button.add_css_class("destructive-action")
        self.cancel_button.add_css_class("pill")
        button_box.append(self.cancel_button)

        self.append(button_box)

    def add_output_text(self, text):
        """Add text to the terminal view."""
        # Add newline if needed
        if not text.endswith("\n"):
            text += "\n"

        # Insert text at the end
        end_iter = self.terminal_buffer.get_end_iter()
        self.terminal_buffer.insert(end_iter, text)

        # Scroll to the end
        end_mark = self.terminal_buffer.create_mark(
            None, self.terminal_buffer.get_end_iter(), False
        )
        self.terminal_view.scroll_to_mark(end_mark, 0.0, True, 0.0, 1.0)
        self.terminal_buffer.delete_mark(end_mark)

    def on_cancel_clicked(self, button):
        """Handle cancel button click with improved process termination"""
        # Ensure os module is imported at the beginning of the method
        from os.path import basename
        import os
        import signal
        import subprocess

        # Set cancelled flag first to prevent error messages
        self.cancelled = True
        print("Cancel button clicked, setting cancelled flag")

        # Update UI to show cancellation
        self.status_label.set_text(_("Cancelling..."))
        self.status_icon.set_from_icon_name("process-stop-symbolic")
        self.cancel_button.set_sensitive(False)

        # Critical: Make sure app knows we're cancelling the current active conversion
        if (
            self.input_file
            and hasattr(self.app, "current_processing_file")
            and self.app.current_processing_file == self.input_file
        ):
            print(
                f"Removing currently processing file from active status: {self.input_file}"
            )
            self.app.current_processing_file = None
            self.app.currently_converting = False

        # Force immediate removal from the conversion queue
        if self.input_file and hasattr(self.app, "conversion_queue"):
            if self.input_file in self.app.conversion_queue:
                try:
                    self.app.conversion_queue.remove(self.input_file)
                    print(f"Directly removed {self.input_file} from queue")

                    # Force update the queue display
                    if hasattr(self.app, "conversion_page"):
                        self.app.conversion_page.update_queue_display()

                    # Add notification to terminal output with safe basename extraction
                    try:
                        filename = basename(
                            self.input_file
                        )  # Use the directly imported basename function
                    except Exception:
                        # Fallback in case of any error
                        parts = self.input_file.split("/")
                        filename = parts[-1] if parts else self.input_file

                    self.add_output_text(f"Removed from queue: {filename}")
                except Exception as e:
                    print(f"Error removing from queue: {e}")

        # CRITICAL: Make sure the file is COMPLETELY removed from the app's conversion queue
        if self.input_file:
            print(f"Ensuring {self.input_file} is removed from conversion queue")

            # Direct queue manipulation - this ensures the file is fully removed
            if (
                hasattr(self.app, "conversion_queue")
                and self.input_file in self.app.conversion_queue
            ):
                try:
                    self.app.conversion_queue.remove(self.input_file)
                    print(
                        f"Directly removed {self.input_file} from app.conversion_queue"
                    )
                except Exception as e:
                    print(f"Error removing from queue: {e}")

            # Also try the standard method if it exists
            if hasattr(self.app, "remove_from_queue"):
                try:
                    self.app.remove_from_queue(self.input_file)
                    print(f"Removed via app.remove_from_queue: {self.input_file}")
                except Exception as e:
                    print(f"Error in remove_from_queue: {e}")

            # Force UI update
            if hasattr(self.app, "conversion_page") and hasattr(
                self.app.conversion_page, "update_queue_display"
            ):
                try:
                    self.app.conversion_page.update_queue_display()
                    print("Updated queue display after removal")
                except Exception as e:
                    print(f"Error updating queue display: {e}")

            # Add notification to terminal output
            self.add_output_text(
                f"Removed from queue: {os.path.basename(self.input_file)}"
            )

        # Kill process
        if self.process:
            try:
                import signal
                import os
                import subprocess
                import psutil  # Try to use psutil for better process management

                print(f"Attempting to terminate process {self.process.pid}")

                # Notify the app to remove this file from the conversion queue
                if self.input_file and hasattr(self.app, "remove_from_queue"):
                    print(f"Removing cancelled file from queue: {self.input_file}")
                    self.app.remove_from_queue(self.input_file)

                # First make sure conversion isn't already removed from list
                found = False
                for (
                    conversion_id,
                    info,
                ) in self.app.progress_page.active_conversions.items():
                    if info["item"] == self:
                        found = True
                        break

                if not found:
                    print("Warning: Conversion already removed from active_conversions")
                    return

                # Forceful termination without creating a separate thread
                # This ensures we don't close the dialog before the process is killed
                try:
                    print(f"Direct process kill for PID {self.process.pid}")

                    # Try using psutil for better process tree killing
                    try:
                        import psutil

                        parent = psutil.Process(self.process.pid)
                        print(f"Found parent process: {parent}")

                        # Kill all child processes
                        for child in parent.children(recursive=True):
                            print(f"Killing child process {child.pid}")
                            child.kill()

                        # Kill the parent
                        parent.kill()
                        print("Killed process tree using psutil")
                    except ImportError:
                        # Fallback to os.killpg
                        print("psutil not available, using fallback kill methods")
                        try:
                            pgid = os.getpgid(self.process.pid)
                            os.killpg(pgid, signal.SIGKILL)
                            print(f"Sent SIGKILL to process group {pgid}")
                        except Exception as e:
                            print(
                                f"Error with killpg: {e}, falling back to direct kill"
                            )
                            self.process.kill()

                    # Wait a short time to ensure process is dead
                    try:
                        self.process.wait(timeout=0.5)
                        print("Process termination confirmed")
                    except subprocess.TimeoutExpired:
                        print("Warning: Process still not terminated after timeout")
                        # One more kill attempt
                        try:
                            self.process.kill()
                        except:
                            pass

                except Exception as e:
                    print(f"Error killing process: {e}")
                    import traceback

                    traceback.print_exc()

            except Exception as e:
                print(f"Error initiating process termination: {e}")
                import traceback

                traceback.print_exc()

    def set_process(self, process):
        """Set the conversion process for monitoring"""
        self.process = process

    def update_progress(self, fraction, text=None):
        """Update progress bar"""
        self.progress_bar.set_fraction(fraction)
        if text:
            self.progress_bar.set_text(text)
        else:
            self.progress_bar.set_text(f"{int(fraction * 100)}%")

    def update_status(self, status):
        """Update status message text"""
        self.status_label.set_text(status)

    def set_delete_original(self, delete_original):
        """Set whether to delete original file after conversion"""
        self.delete_original = delete_original

    def mark_success(self):
        """Mark conversion as successful and update UI"""
        self.success = True
        # Update status icon to success
        self.status_icon.set_from_icon_name("emblem-ok-symbolic")

    def was_cancelled(self):
        """Return whether the conversion was cancelled by the user"""
        return self.cancelled
