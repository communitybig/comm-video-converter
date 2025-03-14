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

def run_with_progress_dialog(app, cmd, title_suffix, input_file=None, delete_original=False, env_vars=None):
    """Run a conversion command and show a progress dialog"""
    from ui.dialogs.progress_dialog import ProgressDialog
    
    # Título correto
    if not title_suffix or title_suffix == "Unknown file":
        if input_file:
            title_suffix = os.path.basename(input_file)
        else:
            title_suffix = _("Video Conversion")
    
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
        if hasattr(os, 'setsid'):  # Unix/Linux
            kwargs['preexec_fn'] = os.setsid  # Create new session, process becomes leader
        elif hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP'):  # Windows
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        
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
            stdin=subprocess.PIPE,  # Add stdin pipe to prevent potential blocking
            universal_newlines=True,
            bufsize=1,
            env=env,
            cwd=output_folder,  # CRUCIAL: Define o diretório de trabalho para o diretório de saída
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
    current_time_secs = 0
    output_file = None
    last_output_time = time.time()
    processing_start_time = time.time()
    
    # Variáveis para melhorar a estimativa de tempo
    progress_samples = []  # Lista para armazenar amostras recentes de progresso
    sample_window = 10     # Número de amostras para usar na média móvel
    
    # Set initial status
    GLib.idle_add(progress_dialog.update_status, _("Starting process..."))
    GLib.idle_add(progress_dialog.add_output_text, _("Starting FFmpeg process..."))
    
    try:
        # Read output line by line
        for line in iter(process.stderr.readline, ""):
            # Reset timeout counter with each line of output
            last_output_time = time.time()
            
            # Print the raw output for debugging
            print(f"FFMPEG: {line.strip()}")
            
            # Send output to terminal view
            GLib.idle_add(progress_dialog.add_output_text, line)
            
            # Check if the process was cancelled
            if progress_dialog.was_cancelled():
                print("Process was cancelled, stopping monitor thread")
                GLib.idle_add(progress_dialog.add_output_text, _("Process cancelled by user"))
                break
            
            # Capture output file if available
            if "Output #0" in line and "'" in line:
                output_match = output_file_pattern.search(line)
                if output_match:
                    output_file = output_match.group(1)
                    print(f"Detected output file: {output_file}")
                    GLib.idle_add(progress_dialog.add_output_text, f"Output file: {output_file}")
            
            # Extract duration if not already done
            if "Duration" in line and not duration_secs:
                duration_match = duration_pattern.search(line)
                if duration_match:
                    duration_str = duration_match.group(1)
                    h, m, s = map(float, duration_str.split(':'))
                    duration_secs = h * 3600 + m * 60 + s
                    status_msg = _("Processing video...")
                    GLib.idle_add(progress_dialog.update_status, status_msg)
                    GLib.idle_add(progress_dialog.add_output_text, f"Video duration: {duration_str} ({duration_secs:.2f} seconds)")
                    print(f"Detected duration: {duration_secs} seconds")
            
            # Extract current time and calculate progress
            if "time=" in line and duration_secs:
                time_match = time_pattern.search(line)
                if time_match:
                    time_str = time_match.group(1)
                    h, m, s = map(float, time_str.split(':'))
                    current_time_secs = h * 3600 + m * 60 + s
                    progress = min(current_time_secs / duration_secs, 1.0)
                    
                    # Armazene o par (tempo_atual, tempo_processamento) para calcular média móvel
                    elapsed_processing_time = time.time() - processing_start_time
                    progress_samples.append((current_time_secs, elapsed_processing_time))
                    
                    # Mantenha apenas as amostras mais recentes
                    if len(progress_samples) > sample_window:
                        progress_samples.pop(0)
                    
                    # Calcule a velocidade média de processamento usando as amostras recentes
                    if len(progress_samples) > 1:
                        # Use apenas as últimas amostras para calcular a taxa recente
                        recent_samples = progress_samples[-min(5, len(progress_samples)):]
                        first_sample = recent_samples[0]
                        last_sample = recent_samples[-1]
                        
                        time_diff = last_sample[0] - first_sample[0]  # Diferença no tempo do vídeo
                        processing_diff = last_sample[1] - first_sample[1]  # Diferença no tempo de processamento
                        
                        if processing_diff > 0:
                            # Taxa de processamento = quanto tempo de vídeo é processado por segundo de tempo real
                            processing_rate = time_diff / processing_diff
                            
                            # Tempo restante estimado = (duração_total - tempo_atual) / taxa_processamento
                            remaining_video_time = duration_secs - current_time_secs
                            remaining_secs = remaining_video_time / processing_rate
                            
                            # Limites razoáveis para o tempo estimado
                            remaining_secs = max(0, min(remaining_secs, duration_secs * 2))
                            
                            remaining_mins = int(remaining_secs / 60)
                            remaining_secs = int(remaining_secs % 60)
                            
                            # Update UI with progress and estimated time
                            GLib.idle_add(progress_dialog.update_progress, progress)
                            status_msg = _("Time remaining:") + f" {remaining_mins:02d}:{remaining_secs:02d}"
                            GLib.idle_add(progress_dialog.update_status, status_msg)
                    else:
                        # Se não temos amostras suficientes, apenas atualize o progresso
                        GLib.idle_add(progress_dialog.update_progress, progress)
            
            # Check for timeout (no output for 15 seconds)
            if time.time() - last_output_time > 15:
                timeout_msg = _("No progress detected. Process may be stuck.")
                GLib.idle_add(progress_dialog.update_status, timeout_msg)
                GLib.idle_add(progress_dialog.add_output_text, timeout_msg)
                print("Process may be stuck - no output for 15 seconds")
        
        # Also check stdout for any remaining output (though FFmpeg usually uses stderr)
        for line in iter(process.stdout.readline, ""):
            GLib.idle_add(progress_dialog.add_output_text, line)
            print(f"FFMPEG stdout: {line.strip()}")
            
            # Check if the process was cancelled
            if progress_dialog.was_cancelled():
                break
        
    except (BrokenPipeError, IOError) as e:
        # This can happen if the process is killed during readline
        error_msg = f"Process pipe error: {e} - process likely terminated"
        print(error_msg)
        GLib.idle_add(progress_dialog.add_output_text, error_msg)
    except Exception as e:
        error_msg = f"Error reading process output: {e}"
        print(error_msg)
        GLib.idle_add(progress_dialog.add_output_text, error_msg)
    
    # Process finished or was canceled
    try:
        if progress_dialog.was_cancelled():
            # If process was cancelled, try to terminate it
            try:
                if process.poll() is None:  # If process is still running
                    process.kill()
                    process.wait(timeout=2)
                    term_msg = "Process terminated after cancellation"
                    print(term_msg)
                    GLib.idle_add(progress_dialog.add_output_text, term_msg)
            except Exception as e:
                error_msg = f"Error killing process after cancellation: {e}"
                print(error_msg)
                GLib.idle_add(progress_dialog.add_output_text, error_msg)
            
            # Update UI for cancellation
            cancel_msg = _("Conversion cancelled.")
            GLib.idle_add(progress_dialog.update_status, cancel_msg)
            GLib.idle_add(progress_dialog.update_progress, 0.0, _("Cancelled"))
            GLib.idle_add(progress_dialog.cancel_button.set_sensitive, False)
        else:
            # Process finished normally, get return code
            return_code = process.wait()
            finish_msg = f"Process finished with return code: {return_code}"
            print(finish_msg)
            GLib.idle_add(progress_dialog.add_output_text, finish_msg)
            
            # Update user interface from main thread
            if return_code == 0:
                # Mark as successful
                GLib.idle_add(progress_dialog.mark_success)
                
                # Update progress bar
                GLib.idle_add(progress_dialog.update_progress, 1.0, _("Completed!"))
                complete_msg = _("Conversion completed successfully!")
                GLib.idle_add(progress_dialog.update_status, complete_msg)
                GLib.idle_add(progress_dialog.add_output_text, complete_msg)
                
                # Check if we should delete the original file
                if progress_dialog.delete_original and progress_dialog.input_file:
                    input_file = progress_dialog.input_file
                    
                    # Check if the output file exists and has a reasonable size
                    if output_file and os.path.exists(output_file):
                        input_size = os.path.getsize(input_file)
                        output_size = os.path.getsize(output_file)
                        
                        size_info = f"Input file size: {input_size} bytes, Output file size: {output_size} bytes"
                        GLib.idle_add(progress_dialog.add_output_text, size_info)
                        
                        # Consider the conversion successful if the output file exists with reasonable size
                        # The size should be at least 1MB or 10% of the original size
                        min_size_threshold = max(1024 * 1024, input_size * 0.1)  
                        if output_size > min_size_threshold:
                            try:
                                os.remove(input_file)
                                delete_msg = f"Original file deleted: {input_file}"
                                GLib.idle_add(progress_dialog.add_output_text, delete_msg)
                                GLib.idle_add(
                                    lambda: show_info_dialog_and_close_progress(
                                        app,
                                        _("Conversion completed successfully!\n\n"
                                          "The original file <b>{0}</b> was deleted.").format(os.path.basename(input_file)),
                                        progress_dialog
                                    )
                                )
                            except Exception as e:
                                error_msg = f"Could not delete the original file: {e}"
                                GLib.idle_add(progress_dialog.add_output_text, error_msg)
                                GLib.idle_add(
                                    lambda: show_info_dialog_and_close_progress(
                                        app,
                                        _("Conversion completed successfully!\n\n"
                                          "Could not delete the original file: {0}").format(e),
                                        progress_dialog
                                    )
                                )
                        else:
                            size_warning = "The original file was not deleted because the converted file size looks suspicious."
                            GLib.idle_add(progress_dialog.add_output_text, size_warning)
                            GLib.idle_add(
                                lambda: show_info_dialog_and_close_progress(
                                    app,
                                    _("Conversion completed successfully!\n\n"
                                      "The original file was not deleted because the converted file size looks suspicious."),
                                    progress_dialog
                                )
                            )
                    else:
                        output_warning = f"Output file not found or not accessible: {output_file}"
                        GLib.idle_add(progress_dialog.add_output_text, output_warning)
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
                error_msg = _("Conversion failed with code {0}").format(return_code)
                GLib.idle_add(progress_dialog.update_progress, 0.0, _("Error!"))
                GLib.idle_add(progress_dialog.update_status, error_msg)
                GLib.idle_add(progress_dialog.add_output_text, error_msg)
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
        completion_msg = f"Conversion finished, active conversions: {app.conversions_running}"
        print(completion_msg)
        GLib.idle_add(progress_dialog.add_output_text, completion_msg)

def show_info_dialog_and_close_progress(app, message, progress_dialog):
    """Shows an information dialog and closes the progress dialog"""
    progress_dialog.destroy()
    app.show_info_dialog(_("Information"), message)

def show_error_dialog_and_close_progress(app, message, progress_dialog):
    """Shows an error dialog and closes the progress dialog"""
    progress_dialog.destroy()
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
        "only_extract_subtitles": "only-extract-subtitles"
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
        print(f"Setting output folder to input file directory: {env_vars['output_folder']}")
    
    return cmd, env_vars