import os
import time
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango

# Setup translation
import gettext
lang_translations = gettext.translation(
    "comm-big-converter", localedir="/usr/share/locale", fallback=True
)
lang_translations.install()
# define _ shortcut for translations
_ = lang_translations.gettext

class ProgressDialog(Adw.Window):
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
        file_name = os.path.basename(input_file) if input_file else _("Multiple files")
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
        
        # Set the window content
        self.set_content(content_box)
        
        self.process = None
        self.cancelled = False
        self.success = False
        
        # Connect to the close-request signal
        self.connect("close-request", self.on_close_request)
    
    def on_cancel_clicked(self, button):
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
        # Just cancel if closed directly
        self.cancelled = True
        
        if self.process:
            try:
                self.process.kill()
            except:
                pass
            
        return False  # Allow window to close
    
    def delayed_close(self):
        self.close()
        return False  # Don't repeat
    
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
        # Update status icon to success
        self.status_icon.set_from_icon_name("emblem-ok-symbolic")
    
    def was_cancelled(self):
        """Return whether the conversion was cancelled by the user"""
        return self.cancelled
