import os
import time
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango

# Setup translation
import gettext
lang_translations = gettext.translation(
    "comm-video-converter", localedir="/usr/share/locale", fallback=True
)
lang_translations.install()
# define _ shortcut for translations
_ = lang_translations.gettext

class MultiProgressDialog(Adw.Window):
    """Dialog to display multiple conversion processes with separate progress bars"""
    def __init__(self, parent, title):
        super().__init__(title=_(title))
        self.set_default_size(600, 400)
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_hide_on_close(True)
        
        # Store processes and progress bars
        self.processes = {}  # process_id -> process object
        self.progress_rows = {}  # process_id -> row dictionary
        self.cancelled = False
        self.next_id = 1  # Counter for generating unique process IDs
        
        # Create the main content box
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Add HeaderBar
        header_bar = Adw.HeaderBar()
        header_bar.set_title_widget(Gtk.Label(label=_("Multiple File Conversion")))
        header_bar.set_show_end_title_buttons(False)

        content_box.append(header_bar)
        
        # Create a scrolled window for the progress bars
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled_window.set_vexpand(True)
        self.scrolled_window.set_hexpand(True)
        
        # Main box inside scrolled window
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.main_box.set_margin_top(16)
        self.main_box.set_margin_bottom(16)
        self.main_box.set_margin_start(16)
        self.main_box.set_margin_end(16)
        self.main_box.set_spacing(12)
        self.scrolled_window.set_child(self.main_box)
        
        content_box.append(self.scrolled_window)
        
        # Status message at the bottom
        self.status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.status_box.set_margin_top(8)
        self.status_box.set_margin_bottom(16)
        self.status_box.set_margin_start(16)
        self.status_box.set_margin_end(16)
        
        self.status_icon = Gtk.Image.new_from_icon_name("emblem-synchronizing-symbolic")
        self.status_icon.set_margin_end(8)
        self.status_box.append(self.status_icon)
        
        self.status_label = Gtk.Label(label=_("Starting conversions..."))
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_hexpand(True)
        self.status_label.set_wrap(True)
        self.status_label.set_xalign(0)
        self.status_box.append(self.status_label)
        
        content_box.append(self.status_box)
        
        # Bottom action area with cancel button
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        button_box.set_halign(Gtk.Align.END)
        button_box.set_margin_bottom(16)
        button_box.set_margin_start(16)
        button_box.set_margin_end(16)
        
        self.cancel_button = Gtk.Button(label=_("Cancel All"))
        self.cancel_button.connect("clicked", self.on_cancel_clicked)
        self.cancel_button.add_css_class("pill")
        self.cancel_button.add_css_class("destructive-action")
        button_box.append(self.cancel_button)
        
        content_box.append(button_box)
        
        # Set the window content
        self.set_content(content_box)
        
        # Connect to the close-request signal
        self.connect("close-request", self.on_close_request)
        
        # Statistics
        self.completed_count = 0
        self.failed_count = 0
        self.total_count = 0
    
    def add_conversion_process(self, process, filename, input_file=None, delete_original=False):
        """Add a new conversion process with its own progress bar"""
        process_id = self.next_id
        self.next_id += 1
        
        # Create a frame for this process
        frame = Gtk.Frame()
        frame.set_margin_bottom(12)
        
        # Create a box inside the frame
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_spacing(8)
        frame.set_child(box)
        
        # File name label
        file_label = Gtk.Label(label=os.path.basename(filename))
        file_label.set_halign(Gtk.Align.START)
        file_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        file_label.add_css_class("heading")
        box.append(file_label)
        
        # Progress bar
        progress_bar = Gtk.ProgressBar()
        progress_bar.set_show_text(True)
        progress_bar.set_text("0%")
        progress_bar.set_valign(Gtk.Align.CENTER)
        progress_bar.set_hexpand(True)
        box.append(progress_bar)
        
        # Status message
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        status_box.set_margin_top(4)
        
        status_icon = Gtk.Image.new_from_icon_name("emblem-synchronizing-symbolic")
        status_icon.set_margin_end(8)
        status_box.append(status_icon)
        
        status_label = Gtk.Label(label=_("Starting conversion..."))
        status_label.set_halign(Gtk.Align.START)
        status_label.set_hexpand(True)
        status_label.set_wrap(True)
        status_label.set_xalign(0)
        status_box.append(status_label)
        
        # Add individual cancel button 
        cancel_button = Gtk.Button()
        cancel_button.set_icon_name("process-stop-symbolic")
        cancel_button.set_tooltip_text(_("Cancel this conversion"))
        cancel_button.add_css_class("circular")
        cancel_button.add_css_class("flat")
        cancel_button.connect("clicked", self.on_individual_cancel_clicked, process_id)
        status_box.append(cancel_button)
        
        box.append(status_box)
        
        # Add to the main box
        self.main_box.append(frame)
        
        # Store process and UI elements
        self.processes[process_id] = process
        self.progress_rows[process_id] = {
            "frame": frame,
            "progress_bar": progress_bar,
            "status_label": status_label,
            "status_icon": status_icon,
            "cancel_button": cancel_button,
            "filename": filename,
            "input_file": input_file,
            "delete_original": delete_original,
            "cancelled": False,
            "completed": False
        }
        
        # Update statistics
        self.total_count += 1
        self.update_status_message()
        
        return process_id
    
    def on_cancel_clicked(self, button):
        """Cancel all conversions"""
        # Set cancelled flag
        self.cancelled = True
        
        # Update UI
        self.status_label.set_text(_("Cancelling all conversions..."))
        self.status_icon.set_from_icon_name("process-stop-symbolic")
        self.cancel_button.set_sensitive(False)
        
        # Cancel each process
        for process_id, process in self.processes.items():
            if not self.progress_rows[process_id]["completed"]:
                self.progress_rows[process_id]["cancelled"] = True
                try:
                    import signal
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except:
                        process.kill()
                except Exception as e:
                    print(f"Error terminating process {process_id}: {e}")
                
                # Update UI for this process
                self.progress_rows[process_id]["status_label"].set_text(_("Cancelled"))
                self.progress_rows[process_id]["status_icon"].set_from_icon_name("process-stop-symbolic")
    
    def on_individual_cancel_clicked(self, button, process_id):
        """Cancel an individual conversion"""
        if process_id in self.processes and not self.progress_rows[process_id]["completed"]:
            # Mark as cancelled
            self.progress_rows[process_id]["cancelled"] = True
            
            # Kill the process
            try:
                import signal
                try:
                    os.killpg(os.getpgid(self.processes[process_id].pid), signal.SIGKILL)
                except:
                    self.processes[process_id].kill()
            except Exception as e:
                print(f"Error terminating process {process_id}: {e}")
            
            # Update UI for this process
            self.progress_rows[process_id]["status_label"].set_text(_("Cancelled"))
            self.progress_rows[process_id]["status_icon"].set_from_icon_name("process-stop-symbolic")
            self.progress_rows[process_id]["cancel_button"].set_sensitive(False)
            
            # Update status
            self.update_status_message()
    
    def on_close_request(self, *args):
        """Handle close request"""
        self.on_cancel_clicked(None)
        return False  # Allow window to close
    
    def update_progress(self, process_id, fraction, text=None):
        """Update progress for a specific process"""
        if process_id in self.progress_rows:
            row = self.progress_rows[process_id]
            row["progress_bar"].set_fraction(fraction)
            if text:
                row["progress_bar"].set_text(text)
            else:
                row["progress_bar"].set_text(f"{int(fraction * 100)}%")
    
    def update_status(self, process_id, status):
        """Update status message for a specific process"""
        if process_id in self.progress_rows:
            self.progress_rows[process_id]["status_label"].set_text(status)
    
    def mark_success(self, process_id):
        """Mark a process as successfully completed"""
        if process_id in self.progress_rows:
            row = self.progress_rows[process_id]
            row["status_icon"].set_from_icon_name("emblem-ok-symbolic")
            row["completed"] = True
            row["cancel_button"].set_sensitive(False)
            
            # Add success indicator to frame
            row["frame"].add_css_class("success")
            
            # Update statistics
            self.completed_count += 1
            self.update_status_message()
    
    def mark_failure(self, process_id):
        """Mark a process as failed"""
        if process_id in self.progress_rows:
            row = self.progress_rows[process_id]
            row["status_icon"].set_from_icon_name("dialog-error-symbolic")
            row["completed"] = True
            row["cancel_button"].set_sensitive(False)
            
            # Add failure indicator to frame
            row["frame"].add_css_class("error")
            
            # Update statistics
            self.failed_count += 1
            self.update_status_message()
    
    def update_status_message(self):
        """Update the global status message"""
        active = self.total_count - self.completed_count - self.failed_count
        message = _("Progress: {0} of {1} completed, {2} failed, {3} active").format(
            self.completed_count, self.total_count, self.failed_count, active
        )
        self.status_label.set_text(message)
        
        # If all completed, update status icon
        if active == 0:
            if self.failed_count == 0:
                self.status_icon.set_from_icon_name("emblem-ok-symbolic")
            else:
                self.status_icon.set_from_icon_name("dialog-warning-symbolic")
    
    def is_cancelled(self, process_id=None):
        """Check if a process or all processes are cancelled"""
        if process_id is not None:
            if process_id in self.progress_rows:
                return self.progress_rows[process_id]["cancelled"]
            return False
        return self.cancelled