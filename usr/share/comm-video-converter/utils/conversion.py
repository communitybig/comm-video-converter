import os
import subprocess
import shlex
import threading
import re
import time
from gi.repository import GLib

from constants import CONVERT_SCRIPT_PATH

# Import translation function
import gettext

_ = gettext.gettext  # Will use the already initialized translation


def run_with_progress_dialog(
    app, cmd, title_suffix, input_file=None, delete_original=False, env_vars=None
):
    """Run a conversion command and show progress on the Progress page"""
    # Título correto
    if not title_suffix or title_suffix == "Unknown file":
        if input_file:
            title_suffix = os.path.basename(input_file)
        else:
            title_suffix = _("Video Conversion")

    cmd_str = " ".join([shlex.quote(arg) for arg in cmd])

    # Increment counter of active conversions
    app.conversions_running += 1

    # Start process
    try:
        # Print command for debugging
        print(f"Executing command: {cmd_str}")

        # IMPORTANTE: Verificação do diretório de saída
        output_folder = None
        if env_vars and "output_folder" in env_vars:
            output_folder = env_vars["output_folder"]
            print(f"Output folder from env_vars: {output_folder}")

            # Verificar se o diretório existe
            if not os.path.exists(output_folder):
                try:
                    os.makedirs(output_folder, exist_ok=True)
                    print(f"Created output directory: {output_folder}")
                except Exception as e:
                    print(f"Warning: Could not create output directory: {e}")

            # Garantir que o caminho é absoluto
            if not os.path.isabs(output_folder):
                abs_path = os.path.abspath(output_folder)
                env_vars["output_folder"] = abs_path
                output_folder = abs_path
                print(f"Converted relative path to absolute: {abs_path}")

        # Create a process group so we can terminate all related processes
        kwargs = {}
        if hasattr(os, "setsid"):  # Unix/Linux
            kwargs["preexec_fn"] = (
                os.setsid
            )  # Create new session, process becomes leader
        elif hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):  # Windows
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        # If env_vars is passed, use it, otherwise use os.environ
        env = env_vars if env_vars is not None else os.environ.copy()

        # Verificar variáveis críticas de ambiente
        print("Critical environment variables:")
        for key in ["output_folder", "output_file"]:
            if key in env:
                print(f"  {key}={env[key]}")
            else:
                print(f"  {key}=<not set>")

        # Use PIPE for stdout and stderr to monitor progress
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
            env=env,
            cwd=output_folder,
            **kwargs,
        )

        # Create conversion item on progress page
        progress_item = app.progress_page.add_conversion(
            title_suffix, input_file, process
        )

        # Configure option to delete original file
        if input_file:
            progress_item.set_delete_original(delete_original)

        # Start thread to monitor progress
        monitor_thread = threading.Thread(
            target=monitor_progress, args=(app, process, progress_item)
        )
        monitor_thread.daemon = True
        monitor_thread.start()

    except Exception as e:
        app.show_error_dialog(_("Error starting conversion: {0}").format(e))
        import traceback

        traceback.print_exc()
        app.conversions_running -= 1


def monitor_progress(app, process, progress_item):
    """Monitor the progress of a running conversion process"""
    # More accurate patterns for FFmpeg output
    time_pattern = re.compile(r"time=(\d+:\d+:\d+\.\d+)")
    duration_pattern = re.compile(r"Duration: (\d+:\d+:\d+\.\d+)")
    output_file_pattern = re.compile(r"Output #0.*?\'(.*?)\'")

    # Add patterns for frame count tracking
    frame_pattern = re.compile(r"frame=\s*(\d+)")
    fps_pattern = re.compile(r"fps=\s*(\d+\.?\d*)")

    # Multiple patterns to get fps from various parts of FFmpeg output
    video_fps_pattern = re.compile(r"Stream #\d+:\d+.*Video:.*\s(\d+(?:\.\d+)?)\s*fps")
    alt_fps_pattern = re.compile(r"Video:.*?(\d+(?:\.\d+)?)\s*(?:tbr|fps)")

    # Values to track progress
    duration_secs = None
    duration_str = None
    current_time_secs = 0
    output_file = None
    last_output_time = time.time()
    processing_start_time = time.time()

    # Variables for frame-based progress tracking
    total_frames = None
    current_frame = 0
    video_fps = None
    max_current_frame = 0

    # Flag to track duration detection
    duration_detected = False

    # Variables for improved time estimation
    progress_samples = []
    sample_window = 10

    # Set initial status
    GLib.idle_add(progress_item.update_status, _("Starting process..."))
    GLib.idle_add(progress_item.add_output_text, _("Starting FFmpeg process..."))

    try:
        # Read output line by line
        for line in iter(process.stderr.readline, ""):
            # Reset timeout counter with each line of output
            last_output_time = time.time()

            # Print the raw output for debugging
            print(f"FFMPEG: {line.strip()}")

            # Send output to terminal view
            GLib.idle_add(progress_item.add_output_text, line)

            # Check if the process was cancelled
            if progress_item.was_cancelled():
                print("Process was cancelled, stopping monitor thread")
                GLib.idle_add(
                    progress_item.add_output_text, _("Process cancelled by user")
                )
                break

            # Capture output file if available
            if "Output #0" in line and "'" in line:
                output_match = output_file_pattern.search(line)
                if output_match:
                    output_file = output_match.group(1)
                    print(f"Detected output file: {output_file}")
                    GLib.idle_add(
                        progress_item.add_output_text, f"Output file: {output_file}"
                    )

            # Extract video frame rate from input stream info
            if video_fps is None and "Stream #" in line and "Video:" in line:
                # Try primary pattern first
                fps_match = video_fps_pattern.search(line)
                if fps_match:
                    try:
                        video_fps = float(fps_match.group(1))
                        print(f"Detected video frame rate: {video_fps} fps")
                        GLib.idle_add(
                            progress_item.add_output_text,
                            f"Detected video frame rate: {video_fps} fps",
                        )
                    except (ValueError, TypeError) as e:
                        print(f"Error converting fps: {e}")
                else:
                    # Try alternative pattern
                    alt_match = alt_fps_pattern.search(line)
                    if alt_match:
                        try:
                            video_fps = float(alt_match.group(1))
                            print(
                                f"Detected video frame rate (alt pattern): {video_fps} fps"
                            )
                            GLib.idle_add(
                                progress_item.add_output_text,
                                f"Detected video frame rate: {video_fps} fps",
                            )
                        except (ValueError, TypeError) as e:
                            print(f"Error converting fps (alt pattern): {e}")

            # Extract duration if not already done
            if not duration_detected and "Duration" in line:
                duration_match = duration_pattern.search(line)
                if duration_match:
                    try:
                        duration_str = duration_match.group(1)
                        h, m, rest = duration_str.split(":")
                        s = rest.split(".")[0]  # Get seconds without milliseconds
                        ms = rest.split(".")[1] if "." in rest else "0"

                        # Calculate duration in seconds with millisecond precision
                        duration_secs = (
                            int(h) * 3600 + int(m) * 60 + int(s) + (int(ms) / 100)
                        )
                        duration_detected = True

                        print(
                            f"Detected duration: {duration_str} ({duration_secs:.3f} seconds)"
                        )
                        GLib.idle_add(
                            progress_item.add_output_text,
                            f"Detected duration: {duration_str}",
                        )

                        # Calculate total frames if we have both duration and fps
                        if video_fps is not None and video_fps > 0:
                            # Sanity check - make sure fps is reasonable (1-120)
                            if 1 <= video_fps <= 120:
                                total_frames = int(duration_secs * video_fps)
                                print(f"Estimated total frames: {total_frames}")
                                GLib.idle_add(
                                    progress_item.add_output_text,
                                    f"Estimated total frames: {total_frames}",
                                )
                            else:
                                print(
                                    f"Unreasonable fps detected: {video_fps}, not calculating total frames"
                                )
                    except Exception as e:
                        print(f"Error parsing duration: {e}")

            # Track current frame count when available
            if "frame=" in line:
                frame_match = frame_pattern.search(line)
                if frame_match:
                    try:
                        current_frame = int(frame_match.group(1))
                        max_current_frame = max(max_current_frame, current_frame)

                        # Get info about current fps
                        current_fps = None
                        fps_match = fps_pattern.search(line)
                        if fps_match:
                            try:
                                current_fps = float(fps_match.group(1))
                            except (ValueError, TypeError):
                                pass

                        # If we don't have total frames yet but have duration
                        if (
                            total_frames is None
                            and duration_secs is not None
                            and duration_secs > 0
                        ):
                            if current_fps is not None and 1 <= current_fps <= 120:
                                # Only use current_fps if it's reasonable
                                total_frames = int(duration_secs * current_fps)
                                print(
                                    f"Estimated total frames from current fps: {total_frames}"
                                )
                                GLib.idle_add(
                                    progress_item.add_output_text,
                                    f"Estimated total frames: {total_frames} (from current fps: {current_fps})",
                                )

                        # Sanity check for frame estimate
                        if (
                            total_frames is not None
                            and current_frame > total_frames * 1.5
                        ):
                            # Current frame count exceeds our total estimate by 50% - our estimate is likely wrong
                            # Recalculate based on observed frame count
                            if duration_secs and duration_secs > 0:
                                processing_time = time.time() - processing_start_time
                                # Estimate total frames based on elapsed time and observed frame count
                                if (
                                    processing_time > 5
                                ):  # Only do this after 5 seconds of processing
                                    estimated_total = (
                                        int(
                                            (current_frame * duration_secs)
                                            / current_time_secs
                                        )
                                        if current_time_secs > 0
                                        else 0
                                    )
                                    if estimated_total > total_frames:
                                        print(
                                            f"Adjusting total frame estimate from {total_frames} to {estimated_total}"
                                        )
                                        total_frames = estimated_total
                                        GLib.idle_add(
                                            progress_item.add_output_text,
                                            f"Adjusted total frames estimate to {total_frames}",
                                        )

                        # Calculate progress based on frames if total_frames is valid
                        if (
                            total_frames is not None
                            and total_frames > 0
                            and current_frame <= total_frames * 1.5
                        ):
                            # Cap progress at 99% until complete
                            progress = min(0.99, current_frame / total_frames)

                            # Process time estimation
                            processing_diff = time.time() - processing_start_time
                            if len(progress_samples) >= sample_window:
                                progress_samples.pop(0)

                            if progress > 0:
                                # Estimate remaining time
                                eta_seconds = (processing_diff / progress) * (
                                    1 - progress
                                )
                                progress_samples.append((progress, eta_seconds))

                                # Calculate average ETA from recent samples
                                if len(progress_samples) > 1:
                                    fps_display = (
                                        f"{current_fps:.1f}"
                                        if current_fps is not None
                                        else "N/A"
                                    )
                                    status_msg = f"_(Speed:) {fps_display} fps"
                                    GLib.idle_add(
                                        progress_item.update_progress,
                                        progress,
                                        f"{int(progress * 100)}%",
                                    )
                                    GLib.idle_add(
                                        progress_item.update_status, status_msg
                                    )

                        # Fallback to time-based progress if frames approach isn't working
                        elif (
                            "time=" in line
                            and duration_secs is not None
                            and duration_secs > 0
                        ):
                            time_match = time_pattern.search(line)
                            if time_match:
                                try:
                                    time_str = time_match.group(1)
                                    h, m, rest = time_str.split(":")
                                    s = rest.split(".")[
                                        0
                                    ]  # Get seconds without milliseconds
                                    ms = rest.split(".")[1] if "." in rest else "0"

                                    # Calculate current time in seconds
                                    current_time_secs = (
                                        int(h) * 3600
                                        + int(m) * 60
                                        + int(s)
                                        + (int(ms) / 100)
                                    )
                                    progress = min(
                                        0.99, current_time_secs / duration_secs
                                    )

                                    # Calculate processing time and ETA
                                    processing_diff = (
                                        time.time() - processing_start_time
                                    )
                                    if progress > 0:
                                        eta_seconds = (processing_diff / progress) * (
                                            1 - progress
                                        )

                                        # Modified status message to show only percentage and speed
                                        fps_display = (
                                            f"{current_fps:.1f}"
                                            if current_fps is not None
                                            else "N/A"
                                        )
                                        status_msg = f"{_('Speed:')} {fps_display} fps"
                                        GLib.idle_add(
                                            progress_item.update_progress,
                                            progress,
                                            f"{int(progress * 100)}%",
                                        )
                                        GLib.idle_add(
                                            progress_item.update_status, status_msg
                                        )
                                except Exception as e:
                                    print(f"Error calculating time progress: {e}")

                        # If neither frame nor time progress works, show frames processed with fps if available
                        else:
                            # Modified status message for indeterminate progress
                            if current_fps is not None:
                                status_msg = f"Processing frame {current_frame} - Speed: {current_fps:.1f} fps"
                            else:
                                status_msg = f"Processing frame {current_frame}"

                            # Use an arbitrary progress value based on frames processed
                            if max_current_frame > 0:
                                arbitrary_progress = min(
                                    0.8,
                                    (current_frame / (max_current_frame + 1000)) + 0.01,
                                )
                                GLib.idle_add(
                                    progress_item.update_progress, arbitrary_progress
                                )
                            else:
                                GLib.idle_add(progress_item.update_progress, 0.01)

                            GLib.idle_add(progress_item.update_status, status_msg)

                    except Exception as e:
                        print(f"Error processing frame progress: {e}")

            # Check for timeout
            if time.time() - last_output_time > 15:
                timeout_msg = _("No progress detected. Process may be stuck.")
                GLib.idle_add(progress_item.update_status, timeout_msg)
                GLib.idle_add(progress_item.add_output_text, timeout_msg)
                print("Process may be stuck - no output for 15 seconds")

        # Also check stdout for any remaining output (though FFmpeg usually uses stderr)
        for line in iter(process.stdout.readline, ""):
            GLib.idle_add(progress_item.add_output_text, line)
            print(f"FFMPEG stdout: {line.strip()}")

            # Check if the process was cancelled
            if progress_item.was_cancelled():
                break

    except (BrokenPipeError, IOError) as e:
        # This can happen if the process is killed during readline
        error_msg = f"Process pipe error: {e} - process likely terminated"
        print(error_msg)
        GLib.idle_add(progress_item.add_output_text, error_msg)
    except Exception as e:
        error_msg = f"Error reading process output: {e}"
        print(error_msg)
        GLib.idle_add(progress_item.add_output_text, error_msg)

    # Process finished or was canceled
    try:
        if progress_item.was_cancelled():
            # If process was cancelled, try to terminate it
            try:
                if process.poll() is None:  # If process is still running
                    process.kill()
                    process.wait(timeout=2)
                    term_msg = "Process terminated after cancellation"
                    print(term_msg)
                    GLib.idle_add(progress_item.add_output_text, term_msg)
            except Exception as e:
                error_msg = f"Error killing process after cancellation: {e}"
                print(error_msg)
                GLib.idle_add(progress_item.add_output_text, error_msg)

            # Update UI for cancellation
            cancel_msg = _("Conversion cancelled.")
            GLib.idle_add(progress_item.update_status, cancel_msg)
            GLib.idle_add(progress_item.update_progress, 0.0, _("Cancelled"))
            GLib.idle_add(progress_item.cancel_button.set_sensitive, False)

            # Remove conversion item from the page after a delay
            GLib.timeout_add(
                2000,
                lambda: app.progress_page.remove_conversion(
                    progress_item.conversion_id
                ),
            )
        else:
            # Process finished normally, get return code
            return_code = process.wait()
            finish_msg = f"Process finished with return code: {return_code}"
            print(finish_msg)
            GLib.idle_add(progress_item.add_output_text, finish_msg)

            # Update user interface from main thread
            if return_code == 0:
                # Mark as successful
                GLib.idle_add(progress_item.mark_success)

                # Update progress bar
                GLib.idle_add(progress_item.update_progress, 1.0, _("Completed!"))
                complete_msg = _("Conversion completed successfully!")
                GLib.idle_add(progress_item.update_status, complete_msg)

                # Check if we should delete the original file
                if progress_item.delete_original and progress_item.input_file:
                    input_file = progress_item.input_file

                    # Check if the output file exists and has a reasonable size
                    if output_file and os.path.exists(output_file):
                        input_size = os.path.getsize(input_file)
                        output_size = os.path.getsize(output_file)

                        size_info = f"Input file size: {input_size} bytes, Output file size: {output_size} bytes"
                        GLib.idle_add(progress_item.add_output_text, size_info)

                        # Consider the conversion successful if the output file exists with reasonable size
                        # The size should be at least 1MB or 10% of the original size
                        min_size_threshold = max(1024 * 1024, input_size * 0.1)
                        if output_size > min_size_threshold:
                            try:
                                os.remove(input_file)
                                delete_msg = f"Original file deleted: {input_file}"
                                GLib.idle_add(progress_item.add_output_text, delete_msg)
                                GLib.idle_add(
                                    lambda: show_info_dialog_and_close_progress(
                                        app,
                                        _(
                                            "Conversion completed successfully!\n\n"
                                            "The original file <b>{0}</b> was deleted."
                                        ).format(os.path.basename(input_file)),
                                        progress_item,
                                    )
                                )
                            except Exception as e:
                                error_msg = f"Could not delete the original file: {e}"
                                GLib.idle_add(progress_item.add_output_text, error_msg)
                                GLib.idle_add(
                                    lambda: show_info_dialog_and_close_progress(
                                        app,
                                        _(
                                            "Conversion completed successfully!\n\n"
                                            "Could not delete the original file: {0}"
                                        ).format(e),
                                        progress_item,
                                    )
                                )
                        else:
                            size_warning = "The original file was not deleted because the converted file size looks suspicious."
                            GLib.idle_add(progress_item.add_output_text, size_warning)
                            GLib.idle_add(
                                lambda: show_info_dialog_and_close_progress(
                                    app,
                                    _(
                                        "Conversion completed successfully!\n\n"
                                        "The original file was not deleted because the converted file size looks suspicious."
                                    ),
                                    progress_item,
                                )
                            )
                    else:
                        output_warning = (
                            f"Output file not found or not accessible: {output_file}"
                        )
                        GLib.idle_add(progress_item.add_output_text, output_warning)
                        GLib.idle_add(
                            lambda: show_info_dialog_and_close_progress(
                                app,
                                _("Conversion completed successfully!"),
                                progress_item,
                            )
                        )
                else:
                    GLib.idle_add(
                        lambda: show_info_dialog_and_close_progress(
                            app,
                            _("Conversion completed successfully!"),
                            progress_item,
                        )
                    )

                # Remove from progress page after delay
                GLib.timeout_add(
                    5000,
                    lambda: app.progress_page.remove_conversion(
                        progress_item.conversion_id
                    ),
                )
            else:
                error_msg = _("Conversion failed with code {0}").format(return_code)
                GLib.idle_add(progress_item.update_progress, 0.0, _("Error!"))
                GLib.idle_add(progress_item.update_status, error_msg)
                GLib.idle_add(progress_item.add_output_text, error_msg)
                GLib.idle_add(
                    lambda: show_error_dialog_and_close_progress(
                        app,
                        _(
                            "The conversion failed with error code {0}.\n\n"
                            "Check the log for more details."
                        ).format(return_code),
                        progress_item,
                    )
                )

                # Keep the error visible longer, but still remove eventually
                GLib.timeout_add(
                    10000,
                    lambda: app.progress_page.remove_conversion(
                        progress_item.conversion_id
                    ),
                )

            # Disable cancel button
            GLib.idle_add(progress_item.cancel_button.set_sensitive, False)
    finally:
        # Always decrement the conversion counter - even if exceptions occur
        app.conversions_running -= 1
        completion_msg = (
            f"Conversion finished, active conversions: {app.conversions_running}"
        )
        print(completion_msg)
        GLib.idle_add(progress_item.add_output_text, completion_msg)


def show_info_dialog_and_close_progress(app, message, progress_item):
    """Shows an information dialog"""
    # Remove the item from the progress page after a delay
    GLib.timeout_add(
        5000, lambda: app.progress_page.remove_conversion(progress_item.conversion_id)
    )
    app.show_info_dialog(_("Information"), message)


def show_error_dialog_and_close_progress(app, message, progress_item):
    """Shows an error dialog"""
    # Remove the item from the progress page after a delay
    GLib.timeout_add(
        5000, lambda: app.progress_page.remove_conversion(progress_item.conversion_id)
    )
    app.show_error_dialog(message)


def build_convert_command(input_file, settings):
    """Build the convert command and environment variables"""
    cmd = [CONVERT_SCRIPT_PATH, input_file]
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
        "only_extract_subtitles": "only-extract-subtitles",
    }

    # Process settings to environment variables
    for env_key, settings_key in settings_map.items():
        value = settings.get(settings_key)
        if value:
            env_vars[env_key] = value

    # Garantir que temos um diretório de saída definido
    if "output_folder" not in env_vars and input_file:
        # Se não estiver definido, use o diretório do arquivo de entrada
        env_vars["output_folder"] = os.path.dirname(input_file)
        print(
            f"Setting output folder to input file directory: {env_vars['output_folder']}"
        )

    return cmd, env_vars
