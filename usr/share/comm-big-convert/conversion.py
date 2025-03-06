import os
import subprocess
import shlex
import threading
import re
import time
from gi.repository import GLib

# Paths to executables
CONVERT_BIG_PATH = "/usr/bin/convert-big"
MKV_MP4_ALL_PATH = "/usr/bin/mkv-mp4-all"

# Import translation function
import gettext
_ = gettext.gettext  # Will use the already initialized translation

def run_with_progress_dialog(app, cmd, title_suffix, input_file=None, delete_original=False, env_vars=None):
    """Run a conversion command and show a progress dialog"""
    from progress_dialog import ProgressDialog
    
    cmd_str = " ".join([shlex.quote(arg) for arg in cmd])
    progress_dialog = ProgressDialog(app.window, _("Converting..."), title_suffix, input_file)
    
    # Configure option to delete original file
    if input_file:
        progress_dialog.set_delete_original(delete_original)
    
    # Increment counter of active conversions
    app.conversions_running += 1
    
    # Start process
    try:
        # Print command for debugging
        print(f"Executing command: {cmd_str}")
        
        # Create a process group so we can terminate all related processes
        kwargs = {}
        if hasattr(os, 'setsid'):  # Unix/Linux
            kwargs['preexec_fn'] = os.setsid  # Create new session, process becomes leader
        elif hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP'):  # Windows
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        
        # If env_vars is passed, use it, otherwise use os.environ
        env = env_vars if env_vars is not None else os.environ.copy()
        
        # Use PIPE for stdout and stderr to monitor progress
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,  # Add stdin pipe to prevent potential blocking
            universal_newlines=True,
            bufsize=1,
            env=env,
            **kwargs
        )
        
        # Set the process in the progress dialog
        progress_dialog.set_process(process)
        
        # Start thread to monitor progress
        monitor_thread = threading.Thread(
            target=monitor_progress,
            args=(app, process, progress_dialog)
        )
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Present the dialog
        progress_dialog.present()
        
    except Exception as e:
        app.show_error_dialog(_("Error starting conversion: {0}").format(e))
        import traceback
        traceback.print_exc()  # Print the full traceback for debugging
        progress_dialog.destroy()
        app.conversions_running -= 1

def monitor_progress(app, process, progress_dialog):
    """Monitor the progress of a running conversion process"""
    # Patterns to extract progress from ffmpeg
    time_pattern = re.compile(r'time=(\d+:\d+:\d+.\d+)')
    duration_pattern = re.compile(r'Duration: (\d+:\d+:\d+.\d+)')
    output_file_pattern = re.compile(r'Output #0.*?\'(.*?)\'')
    
    duration_secs = None
    output_file = None
    last_output_time = time.time()
    processing_start_time = time.time()
    
    # Set initial status
    GLib.idle_add(progress_dialog.update_status, _("Starting process..."))
    
    try:
        # Read output line by line
        for line in iter(process.stderr.readline, ""):
            # Reset timeout counter with each line of output
            last_output_time = time.time()
            
            # Print the raw output for debugging
            print(f"FFMPEG: {line.strip()}")
            
            # Check if the process was cancelled
            if progress_dialog.was_cancelled():
                print("Process was cancelled, stopping monitor thread")
                break
            
            # Capture output file if available
            if "Output #0" in line and "'" in line:
                output_match = output_file_pattern.search(line)
                if output_match:
                    output_file = output_match.group(1)
                    print(f"Detected output file: {output_file}")
            
            # Extract duration if not already done
            if "Duration" in line and not duration_secs:
                duration_match = duration_pattern.search(line)
                if duration_match:
                    duration_str = duration_match.group(1)
                    h, m, s = map(float, duration_str.split(':'))
                    duration_secs = h * 3600 + m * 60 + s
                    GLib.idle_add(progress_dialog.update_status, _("Processing video..."))
                    print(f"Detected duration: {duration_secs} seconds")
            
            # Extract current time and calculate progress
            if "time=" in line and duration_secs:
                time_match = time_pattern.search(line)
                if time_match:
                    time_str = time_match.group(1)
                    h, m, s = map(float, time_str.split(':'))
                    current_time_secs = h * 3600 + m * 60 + s
                    progress = min(current_time_secs / duration_secs, 1.0)
                    
                    # Calculate estimated time remaining
                    if progress > 0:
                        elapsed_time = time.time() - processing_start_time
                        estimated_total_time = elapsed_time / progress
                        remaining_secs = max(0, estimated_total_time - elapsed_time)
                        remaining_mins = int(remaining_secs / 60)
                        remaining_secs = int(remaining_secs % 60)
                        
                        # Update UI with progress and estimated time
                        GLib.idle_add(progress_dialog.update_progress, progress)
                        GLib.idle_add(
                            progress_dialog.update_status, 
                            _("Time remaining:") + " {1:02d}:{2:02d}".format(
                                progress * 100, remaining_mins, remaining_secs)
                        )
            
            # Check for timeout (no output for 15 seconds)
            if time.time() - last_output_time > 15:
                GLib.idle_add(progress_dialog.update_status, _("No progress detected. Process may be stuck."))
                print("Process may be stuck - no output for 15 seconds")
        
    except (BrokenPipeError, IOError) as e:
        # This can happen if the process is killed during readline
        print(f"Process pipe error: {e} - process likely terminated")
    except Exception as e:
        print(f"Error reading process output: {e}")
    
    # Process finished or was canceled
    try:
        if progress_dialog.was_cancelled():
            # If process was cancelled, try to terminate it
            try:
                if process.poll() is None:  # If process is still running
                    process.kill()
                    process.wait(timeout=2)
                    print("Process terminated after cancellation")
            except Exception as e:
                print(f"Error killing process after cancellation: {e}")
            
            # Update UI for cancellation
            GLib.idle_add(progress_dialog.update_status, _("Conversion cancelled."))
            GLib.idle_add(progress_dialog.update_progress, 0.0, _("Cancelled"))
            GLib.idle_add(progress_dialog.cancel_button.set_sensitive, False)
        else:
            # Process finished normally, get return code
            return_code = process.wait()
            print(f"Process finished with return code: {return_code}")
            
            # Update user interface from main thread
            if return_code == 0:
                # Mark as successful
                GLib.idle_add(progress_dialog.mark_success)
                
                # Update progress bar
                GLib.idle_add(progress_dialog.update_progress, 1.0, _("Completed!"))
                GLib.idle_add(progress_dialog.update_status, _("Conversion completed successfully!"))
                
                # Check if we should delete the original file
                if progress_dialog.delete_original and progress_dialog.input_file:
                    input_file = progress_dialog.input_file
                    
                    # Check if the output file exists and has a reasonable size
                    if output_file and os.path.exists(output_file):
                        input_size = os.path.getsize(input_file)
                        output_size = os.path.getsize(output_file)
                        
                        # Consider the conversion successful if the MP4 file exists with reasonable size
                        if output_size > 1024 * 1024:  # 1MB in bytes
                            try:
                                os.remove(input_file)
                                GLib.idle_add(
                                    lambda: show_info_dialog_and_close_progress(
                                        app,
                                        _("Conversion completed successfully!\n\n"
                                          "The original file <b>{0}</b> was deleted.").format(os.path.basename(input_file)),
                                        progress_dialog
                                    )
                                )
                            except Exception as e:
                                GLib.idle_add(
                                    lambda: show_info_dialog_and_close_progress(
                                        app,
                                        _("Conversion completed successfully!\n\n"
                                          "Could not delete the original file: {0}").format(e),
                                        progress_dialog
                                    )
                                )
                        else:
                            GLib.idle_add(
                                lambda: show_info_dialog_and_close_progress(
                                    app,
                                    _("Conversion completed successfully!\n\n"
                                      "The original file was not deleted because the converted file size looks suspicious."),
                                    progress_dialog
                                )
                            )
                    else:
                        GLib.idle_add(
                            lambda: show_info_dialog_and_close_progress(
                                app,
                                _("Conversion completed successfully!"),
                                progress_dialog
                            )
                        )
                else:
                    GLib.idle_add(
                        lambda: show_info_dialog_and_close_progress(
                            app,
                            _("Conversion completed successfully!"),
                            progress_dialog
                        )
                    )
            else:
                GLib.idle_add(progress_dialog.update_progress, 0.0, _("Error!"))
                GLib.idle_add(progress_dialog.update_status, _("Conversion failed with code {0}").format(return_code))
                GLib.idle_add(
                    lambda: show_error_dialog_and_close_progress(
                        app,
                        _("The conversion failed with error code {0}.\n\n"
                          "Check the log for more details.").format(return_code),
                        progress_dialog
                    )
                )
            
            # Disable cancel button
            GLib.idle_add(progress_dialog.cancel_button.set_sensitive, False)
    finally:
        # Always decrement the conversion counter - even if exceptions occur
        app.conversions_running -= 1
        print(f"Conversion finished, active conversions: {app.conversions_running}")

def show_info_dialog_and_close_progress(app, message, progress_dialog):
    """Shows an information dialog and closes the progress dialog"""
    progress_dialog.destroy()
    app.show_info_dialog(_("Information"), message)

def show_error_dialog_and_close_progress(app, message, progress_dialog):
    """Shows an error dialog and closes the progress dialog"""
    progress_dialog.destroy()
    app.show_error_dialog(message)

def build_convert_big_command(input_file, settings):
    """Build the convert-big command and environment variables"""
    cmd = [CONVERT_BIG_PATH, input_file]
    env_vars = os.environ.copy()
    
    # Map settings to environment variables
    settings_map = {
        "output_file": "output-file",
        "output_folder": "output-folder",
        "gpu": "gpu-selection", 
        "video_quality": "video-quality",
        "video_encoder": "video-codec",
        "preset": "preset",
        "subtitle_extract": "subtitle-extract",
        "audio_handling": "audio-handling",
        "audio_bitrate": "audio-bitrate",
        "audio_channels": "audio-channels",
        "video_resolution": "video-resolution",
        "options": "additional-options",
        "gpu_partial": "gpu-partial",
        "force_copy_video": "force-copy-video",
        "only_extract_subtitles": "only-extract-subtitles"
    }
    
    # Process settings to environment variables
    for env_key, settings_key in settings_map.items():
        value = settings.get(settings_key)
        if value:
            env_vars[env_key] = value
    
    return cmd, env_vars

def build_mkv_mp4_all_command(search_dir, max_procs, min_mp4_size, log_file, delete_originals):
    """Build the mkv-mp4-all command"""
    cmd = [MKV_MP4_ALL_PATH, 
           "--dir", search_dir, 
           "--procs", str(max_procs), 
           "--size", str(min_mp4_size), 
           "--log", log_file]
    
    if not delete_originals:
        cmd.append("--nodelete")
    
    return cmd, os.environ.copy()
