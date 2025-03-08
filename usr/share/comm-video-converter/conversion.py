import os
import subprocess
import shlex
import threading
import re
import time
from gi.repository import GLib
from constants import CONVERT_BIG_PATH, MKV_MP4_ALL_PATH

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
                        # The size should be at least 1MB or 10% of the original size
                        min_size_threshold = max(1024 * 1024, input_size * 0.1)  
                        if output_size > min_size_threshold:
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

def run_batch_with_multi_progress(app, search_dir, max_procs, min_mp4_size, log_file, delete_originals, env_vars=None):
    """Run batch conversion with multiple progress dialog for tracking individual files"""
    from multi_progress_dialog import MultiProgressDialog
    import glob
    import threading
    import queue
    
    # Find all MKV files in the directory
    mkv_files = glob.glob(os.path.join(search_dir, "**/*.mkv"), recursive=True)
    
    if not mkv_files:
        app.show_error_dialog(_("No MKV files found in the selected directory."))
        return
    
    # Create the multi-progress dialog
    progress_dialog = MultiProgressDialog(app.window, _("Converting MKV Files"))
    
    # Create a queue for processing files
    file_queue = queue.Queue()
    
    # Add all files to the queue
    for mkv_file in mkv_files:
        file_queue.put(mkv_file)
    
    # Create a list to track running threads
    running_threads = []
    
    # Function to process files from the queue
    def process_files_from_queue():
        while not file_queue.empty() and not progress_dialog.is_cancelled():
            try:
                # Get the next file from the queue
                mkv_file = file_queue.get_nowait()
                
                # Create environment for this process
                process_env = env_vars.copy() if env_vars else os.environ.copy()
                
                # Set min MP4 size and delete original options
                process_env["min_mp4_size"] = str(min_mp4_size)
                if delete_originals:
                    process_env["delete_original"] = "1"
                
                # Build command for this file
                cmd = [
                    CONVERT_BIG_PATH,
                    mkv_file
                ]
                
                # Start process for this file
                try:
                    # Create a new process group
                    kwargs = {}
                    if hasattr(os, 'setsid'):  # Unix/Linux
                        kwargs['preexec_fn'] = os.setsid
                    elif hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP'):  # Windows
                        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
                    
                    # Start the process
                    process = subprocess.Popen(
                        cmd, 
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        stdin=subprocess.PIPE,
                        universal_newlines=True,
                        bufsize=1,
                        env=process_env,
                        **kwargs
                    )
                    
                    # Add to multi-progress dialog
                    process_id = progress_dialog.add_conversion_process(
                        process, 
                        os.path.basename(mkv_file),
                        mkv_file,
                        delete_originals
                    )
                    
                    # Start monitoring thread for this process
                    monitor_thread = threading.Thread(
                        target=monitor_individual_progress,
                        args=(app, process, progress_dialog, process_id)
                    )
                    monitor_thread.daemon = True
                    monitor_thread.start()
                    
                    # Add to tracking list
                    running_threads.append(monitor_thread)
                    
                except Exception as e:
                    print(f"Error starting conversion for {mkv_file}: {e}")
                    file_queue.task_done()
                    
                # Optionally wait a bit to stagger process starts
                time.sleep(0.5)
                
            except queue.Empty:
                break
    
    # Start worker threads based on max_procs
    for i in range(min(max_procs, len(mkv_files))):
        worker_thread = threading.Thread(target=process_files_from_queue)
        worker_thread.daemon = True
        worker_thread.start()
    
    # Show dialog
    progress_dialog.present()
    
    # Return status info
    return {
        'dialog': progress_dialog,
        'threads': running_threads,
        'file_count': len(mkv_files)
    }

def monitor_individual_progress(app, process, multi_dialog, process_id):
    """Monitor progress of a single file conversion in the batch process"""
    # Patterns to extract progress from ffmpeg
    time_pattern = re.compile(r'time=(\d+:\d+:\d+.\d+)')
    duration_pattern = re.compile(r'Duration: (\d+:\d+:\d+.\d+)')
    output_file_pattern = re.compile(r'Output #0.*?\'(.*?)\'')
    
    duration_secs = None
    output_file = None
    last_output_time = time.time()
    processing_start_time = time.time()
    
    # Set initial status
    GLib.idle_add(multi_dialog.update_status, process_id, _("Starting process..."))
    
    try:
        # Read output line by line
        for line in iter(process.stderr.readline, ""):
            # Reset timeout counter with each line of output
            last_output_time = time.time()
            
            # Print the raw output for debugging
            print(f"FFMPEG ({process_id}): {line.strip()}")
            
            # Check if the process was cancelled
            if multi_dialog.is_cancelled(process_id) or multi_dialog.is_cancelled():
                print(f"Process {process_id} was cancelled, stopping monitor thread")
                break
            
            # Capture output file if available
            if "Output #0" in line and "'" in line:
                output_match = output_file_pattern.search(line)
                if output_match:
                    output_file = output_match.group(1)
                    print(f"Detected output file for process {process_id}: {output_file}")
            
            # Extract duration if not already done
            if "Duration" in line and not duration_secs:
                duration_match = duration_pattern.search(line)
                if duration_match:
                    duration_str = duration_match.group(1)
                    try:
                        h, m, s = map(float, duration_str.split(':'))
                        duration_secs = h * 3600 + m * 60 + s
                        GLib.idle_add(multi_dialog.update_status, process_id, _("Processing video..."))
                        print(f"Detected duration for process {process_id}: {duration_secs} seconds")
                    except Exception as e:
                        print(f"Error parsing duration for process {process_id}: {e}")
            
            # Extract current time and calculate progress
            if "time=" in line and duration_secs:
                time_match = time_pattern.search(line)
                if time_match:
                    time_str = time_match.group(1)
                    try:
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
                            GLib.idle_add(multi_dialog.update_progress, process_id, progress)
                            GLib.idle_add(
                                multi_dialog.update_status, 
                                process_id,
                                _("Time remaining:") + " {0:02d}:{1:02d}".format(
                                    remaining_mins, remaining_secs)
                            )
                    except Exception as e:
                        print(f"Error parsing time for process {process_id}: {e}")
            
            # Check for timeout (no output for 15 seconds)
            if time.time() - last_output_time > 15:
                GLib.idle_add(
                    multi_dialog.update_status, 
                    process_id, 
                    _("No progress detected. Process may be stuck.")
                )
                print(f"Process {process_id} may be stuck - no output for 15 seconds")
        
    except (BrokenPipeError, IOError) as e:
        print(f"Process {process_id} pipe error: {e} - process likely terminated")
    except Exception as e:
        print(f"Error reading process {process_id} output: {e}")
    
    # Process finished or was canceled
    try:
        if multi_dialog.is_cancelled(process_id) or multi_dialog.is_cancelled():
            # Process was cancelled - update UI
            GLib.idle_add(multi_dialog.update_status, process_id, _("Conversion cancelled."))
            GLib.idle_add(multi_dialog.update_progress, process_id, 0.0, _("Cancelled"))
        else:
            # Process finished normally
            return_code = process.wait()
            print(f"Process {process_id} finished with return code: {return_code}")
            
            if return_code == 0:
                # Successful conversion
                GLib.idle_add(multi_dialog.mark_success, process_id)
                GLib.idle_add(multi_dialog.update_progress, process_id, 1.0, _("Completed!"))
                GLib.idle_add(multi_dialog.update_status, process_id, _("Conversion completed successfully!"))
                
                # Handle file deletion if requested
                row = multi_dialog.progress_rows.get(process_id)
                if row and row["delete_original"] and row["input_file"]:
                    input_file = row["input_file"]
                    
                    # Check output file exists with reasonable size
                    if output_file and os.path.exists(output_file):
                        input_size = os.path.getsize(input_file)
                        output_size = os.path.getsize(output_file)
                        
                        # Consider successful if MP4 has reasonable size
                        min_size_threshold = max(1024 * 1024, input_size * 0.1)
                        if output_size > min_size_threshold:
                            try:
                                os.remove(input_file)
                                GLib.idle_add(
                                    multi_dialog.update_status,
                                    process_id,
                                    _("Conversion completed and original file deleted.")
                                )
                            except Exception as e:
                                GLib.idle_add(
                                    multi_dialog.update_status,
                                    process_id,
                                    _("Conversion completed but could not delete original: {0}").format(e)
                                )
                        else:
                            GLib.idle_add(
                                multi_dialog.update_status,
                                process_id,
                                _("Converted but output size looks suspicious - not deleting original.")
                            )
            else:
                # Failed conversion
                GLib.idle_add(multi_dialog.mark_failure, process_id)
                GLib.idle_add(multi_dialog.update_progress, process_id, 0.0, _("Error!"))
                GLib.idle_add(
                    multi_dialog.update_status, 
                    process_id, 
                    _("Conversion failed with code {0}").format(return_code)
                )
    except Exception as e:
        print(f"Error finalizing process {process_id}: {e}")