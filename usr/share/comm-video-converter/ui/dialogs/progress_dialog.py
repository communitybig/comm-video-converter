import os
import time
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango

# Setup translation
import gettext
_ = gettext.gettext

class ProgressDialog(Adw.Window):
    """
    Dialog window to display conversion progress.
    Provides UI to monitor and control the conversion process.
    """
    def __init__(self, parent, title, command, input_file=None):
        super().__init__(title=_(title))
        self.set_default_size(500, 200)
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_hide_on_close(True)
        
        # Store input file for possible later removal
        self.input_file = input_file
        self.delete_original = False  # Will be set by the caller
        
        # Create the main content box
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Add HeaderBar
        header_bar = Adw.HeaderBar()
        self.subtitle_label = Gtk.Label()
        self.subtitle_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        header_bar.set_title_widget(self.subtitle_label)
        header_bar.set_show_end_title_buttons(False)

        content_box.append(header_bar)
        
        # Main content area with proper margins
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        main_box.set_spacing(16)
        content_box.append(main_box)
        
        # Status card using Adw.PreferencesGroup
        status_group = Adw.PreferencesGroup()
        
        # File info
        file_name = os.path.basename(input_file) if input_file else _("Unknown file")
        self.subtitle_label.set_text(file_name)
        
        # Status row with progress bar
        status_row = Adw.ActionRow()
        status_row.set_title(_("Progress"))
        
        # Progress bar with a more compact style
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_text("0%")
        self.progress_bar.set_valign(Gtk.Align.CENTER)
        self.progress_bar.set_hexpand(True)
        status_row.add_suffix(self.progress_bar)
        status_row.set_activatable(False)
        status_group.add(status_row)
        
        # Create expandable terminal for FFmpeg output
        self.terminal_expander = Gtk.Expander()
        self.terminal_expander.set_label(_("Show Command Output"))
        self.terminal_expander.add_css_class("caption")
        self.terminal_expander.set_margin_top(8)
        self.terminal_expander.set_margin_start(16)
        self.terminal_expander.set_margin_end(16)
        self.terminal_expander.set_margin_bottom(16)
        
        # Container para o conteúdo do terminal 
        self.terminal_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.terminal_container.set_visible(False)  # Inicialmente oculto
        
        # Create scrolled window for the terminal
        terminal_scroll = Gtk.ScrolledWindow()
        terminal_scroll.set_min_content_height(200)
        terminal_scroll.set_vexpand(True)

        # Create terminal-like TextView
        self.terminal_view = Gtk.TextView()
        self.terminal_view.set_editable(False)
        self.terminal_view.set_cursor_visible(False)
        self.terminal_view.set_monospace(True)
        self.terminal_view.add_css_class("terminal")
        self.terminal_view.add_css_class("monospace")
        # Dark background and light text for terminal-like appearance
        self.terminal_view.add_css_class("card")
        self.terminal_buffer = self.terminal_view.get_buffer()

        # Add text view to scrolled window
        terminal_scroll.set_child(self.terminal_view)
        
        # Add scrolled window to container
        self.terminal_container.append(terminal_scroll)
        
        # Connect expander signal
        self.terminal_expander.connect("notify::expanded", self._on_expander_toggled)
        
        # Status message
        message_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        message_box.set_margin_top(8)
        
        # Store the status icon as an instance variable so we can update it
        self.status_icon = Gtk.Image.new_from_icon_name("emblem-synchronizing-symbolic")
        self.status_icon.set_margin_end(8)
        message_box.append(self.status_icon)
        
        self.status_label = Gtk.Label(label=_("Starting conversion..."))
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_hexpand(True)
        self.status_label.set_wrap(True)
        self.status_label.set_xalign(0)
        message_box.append(self.status_label)
        
        main_box.append(status_group)
        main_box.append(message_box)
        
        # Bottom action area with cancel button
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        button_box.set_halign(Gtk.Align.END)
        button_box.set_margin_top(16)
        
        self.cancel_button = Gtk.Button(label=_("Cancel"))
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        self.cancel_button.add_css_class("pill")
        self.cancel_button.add_css_class("destructive-action")
        button_box.append(self.cancel_button)
        
        main_box.append(button_box)
        
        # Add expander and container to content box
        main_box.append(self.terminal_expander)
        main_box.append(self.terminal_container)
        
        # Set the window content
        self.set_content(content_box)
        
        self.process = None
        self.cancelled = False
        self.success = False
        
        # Connect to the close-request signal
        self.connect("close-request", self.on_close_request)
    
    def _on_expander_toggled(self, expander, pspec):
        """Handle expander toggle to show/hide terminal"""
        expanded = expander.get_expanded()
        self.terminal_container.set_visible(expanded)
        
        # Se expandido, garanta que o terminal seja rolado para o final
        if expanded:
            end_mark = self.terminal_buffer.create_mark(None, self.terminal_buffer.get_end_iter(), False)
            self.terminal_view.scroll_to_mark(end_mark, 0.0, True, 0.0, 1.0)
            self.terminal_buffer.delete_mark(end_mark)
    
    def add_output_text(self, text):
        """Add text to the terminal view."""
        # Add newline if needed
        if not text.endswith('\n'):
            text += '\n'
        
        # Insert text at the end
        end_iter = self.terminal_buffer.get_end_iter()
        self.terminal_buffer.insert(end_iter, text)
        
        # Scroll to the end
        end_mark = self.terminal_buffer.create_mark(None, self.terminal_buffer.get_end_iter(), False)
        self.terminal_view.scroll_to_mark(end_mark, 0.0, True, 0.0, 1.0)
        self.terminal_buffer.delete_mark(end_mark)
    
    def on_cancel_clicked(self, button):
        """Handle cancel button click"""
        # Set cancelled flag first to prevent error messages
        self.cancelled = True
        
        # Update UI to show cancellation
        self.status_label.set_text(_("Cancelling..."))
        self.status_icon.set_from_icon_name("process-stop-symbolic")
        self.cancel_button.set_sensitive(False)
        
        # Kill process in a simple way
        if self.process:
            try:
                import signal
                
                # Try to kill process group on Unix
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                except:
                    # Fallback: try to kill just the process
                    self.process.kill()
                
                print("Process termination requested")
            except Exception as e:
                print(f"Error terminating process: {e}")
        
        # Close the dialog after a short delay
        GLib.timeout_add(500, self.close)
    
    def on_close_request(self, *args):
        """Handle close request"""
        # Just cancel if closed directly
        self.cancelled = True
        
        if self.process:
            try:
                self.process.kill()
            except:
                pass
            
        return False  # Allow window to close
    
    def delayed_close(self):
        """Close dialog after short delay"""
        self.close()
        return False  # Don't repeat
    
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