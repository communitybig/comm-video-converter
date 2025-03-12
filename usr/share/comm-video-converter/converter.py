#!/usr/bin/env python3
"""
Handles video conversion with GPU acceleration, subtitle extraction,
and video effects processing.
"""

import os
import logging
import json
import subprocess
from pathlib import Path
from typing import Optional, Callable, Dict, Any

# Import dataclasses
from data_models import (
    ConversionOptions,
    VideoEffects,
    CropSettings,
    TrimSettings,
    EncodingSettings,
    AudioSettings,
    SubtitleSettings,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("comm-converter")


class VideoConverter:
    """Core video converter functionality"""

    # Quality presets
    QUALITY_PRESETS = {
        "veryhigh": {
            "cq_value": 19,
            "qp_value": 18,
            "global_quality": 18,
            "cq_value_nvidia": 19,
        },
        "high": {
            "cq_value": 24,
            "qp_value": 21,
            "global_quality": 21,
            "cq_value_nvidia": 24,
        },
        "medium": {
            "cq_value": 28,
            "qp_value": 24,
            "global_quality": 24,
            "cq_value_nvidia": 28,
        },
        "low": {
            "cq_value": 31,
            "qp_value": 27,
            "global_quality": 27,
            "cq_value_nvidia": 31,
        },
        "verylow": {
            "cq_value": 34,
            "qp_value": 30,
            "global_quality": 30,
            "cq_value_nvidia": 34,
        },
    }

    # NVIDIA preset values
    NVIDIA_PRESETS = {
        "ultrafast": 1,
        "veryfast": 2,
        "faster": 3,
        "medium": 4,
        "slow": 5,
        "veryslow": 6,
    }

    def __init__(self, settings_manager=None):
        """Initialize the converter with default settings"""
        self.settings_manager = settings_manager

        # Use dataclass for all conversion options
        self.options = ConversionOptions()

        # Initialize from settings manager if available
        if settings_manager:
            self._init_from_settings_manager()

        # Find ffmpeg executable
        self.ffmpeg_executable = self._find_ffmpeg_executable()

        # For storing subtitle files generated during extraction
        self.subtitle_files = []

        # Progress callback
        self.progress_callback = None

    def _init_from_settings_manager(self):
        """Initialize settings from the settings manager"""
        # Video effects
        self.options.video_effects = VideoEffects(
            brightness=self.settings_manager.get("brightness", 0.0),
            contrast=self.settings_manager.get("contrast", 1.0),
            saturation=self.settings_manager.get("saturation", 1.0),
            gamma=self.settings_manager.get("gamma", 1.0),
            gamma_r=self.settings_manager.get("gamma-r", 1.0),
            gamma_g=self.settings_manager.get("gamma-g", 1.0),
            gamma_b=self.settings_manager.get("gamma-b", 1.0),
            gamma_weight=self.settings_manager.get("gamma-weight", 1.0),
            hue=self.settings_manager.get("hue", 0.0),
            exposure=self.settings_manager.get("exposure", 0.0),
        )

        # Crop settings
        crop_params = self.settings_manager.get_crop_params()
        self.options.crop = CropSettings(
            left=crop_params["x"],
            top=crop_params["y"],
            width=crop_params.get("width", 0),
            height=crop_params.get("height", 0),
            right=self.settings_manager.get("crop-right", 0),
            bottom=self.settings_manager.get("crop-bottom", 0),
            enabled=crop_params.get("enabled", False),
        )

        # Trim settings
        start, end, duration = self.settings_manager.get_trim_times()
        self.options.trim = TrimSettings(
            start_time=start, end_time=end, duration=duration
        )

        # Encoding settings
        self.options.encoding = EncodingSettings(
            video_encoder=self.settings_manager.get_selected_encoder(),
            video_quality=self.settings_manager.get_selected_quality(),
            video_resolution=self.settings_manager.get("video-resolution", ""),
            gpu_selection=self.settings_manager.get("gpu-selection", 0),
            gpu_partial=self.settings_manager.get("gpu-partial", False),
            preset=self.settings_manager.get_selected_preset(),
            use_gpu=self.settings_manager.get_use_gpu(),
        )

        # Audio settings
        self.options.audio = AudioSettings(
            handling=self.settings_manager.get_selected_audio_mode(),
            bitrate=self.settings_manager.get("audio-bitrate", ""),
            channels=self.settings_manager.get("audio-channels", ""),
        )

        # Subtitle settings
        self.options.subtitle = SubtitleSettings(
            mode=self.settings_manager.get_selected_subtitle_mode()
        )

        # Additional options
        self.options.additional_options = self.settings_manager.get(
            "additional-options", ""
        )
        self.options.force_copy_video = self.settings_manager.get(
            "force-copy-video", False
        )
        self.options.only_extract_subtitles = self.settings_manager.get(
            "only-extract-subtitles", False
        )

    def update_from_settings_manager(self):
        """Update all settings from the settings manager"""
        if self.settings_manager:
            logger.info("Updating converter settings from settings manager")
            self._init_from_settings_manager()

    def _find_ffmpeg_executable(self) -> str:
        """Find the best FFmpeg executable available"""
        if os.path.exists("/usr/lib/jellyfin-ffmpeg/ffmpeg"):
            return "/usr/lib/jellyfin-ffmpeg/ffmpeg"
        return "ffmpeg"

    def set_progress_callback(self, callback: Callable[[float, str], None]) -> None:
        """Set a callback function for progress updates"""
        self.progress_callback = callback

    def set_input_file(self, file_path: str) -> None:
        """Set the input file path"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Input file not found: {file_path}")

        self.options.input_file = os.path.abspath(file_path)

        # Set default output file if not already set
        if not self.options.output_file and not self.options.output_folder:
            input_path = Path(file_path)
            self.options.output_file = str(input_path.with_suffix(".mp4"))
        elif self.options.output_folder and not self.options.output_file:
            input_path = Path(file_path)
            self.options.output_file = os.path.join(
                self.options.output_folder, input_path.stem + ".mp4"
            )

    def set_output_file(self, file_path: str) -> None:
        """Set the output file path"""
        self.options.output_file = file_path

    def set_output_folder(self, folder_path: str) -> None:
        """Set the output folder path"""
        self.options.output_folder = folder_path

        # Update output file path if input file is already set
        if self.options.input_file and not self.options.output_file:
            input_path = Path(self.options.input_file)
            self.options.output_file = os.path.join(
                folder_path, input_path.stem + ".mp4"
            )

    # Simplified settings methods using dataclasses
    def set_video_options(
        self, encoder: str = None, quality: str = None, preset: str = None
    ) -> None:
        """Set video encoding options in one call"""
        if encoder:
            valid_encoders = ["h264", "h265", "av1", "vp9"]
            self.options.encoding.video_encoder = (
                encoder.lower() if encoder.lower() in valid_encoders else "h264"
            )

        if quality:
            self.options.encoding.video_quality = (
                quality if quality in self.QUALITY_PRESETS else "medium"
            )

        if preset:
            valid_presets = [
                "ultrafast",
                "veryfast",
                "faster",
                "medium",
                "slow",
                "veryslow",
            ]
            if preset.lower() in valid_presets:
                self.options.encoding.preset = preset.lower()

    def set_audio_options(
        self, handling: str = None, bitrate: str = None, channels: str = None
    ) -> None:
        """Set audio encoding options in one call"""
        if handling:
            valid_modes = ["copy", "reencode", "none"]
            self.options.audio.handling = (
                handling.lower() if handling.lower() in valid_modes else "copy"
            )

        if bitrate:
            self.options.audio.bitrate = bitrate

        if channels:
            self.options.audio.channels = channels

    def set_subtitle_extract(self, mode: str) -> None:
        """Set subtitle extraction mode"""
        valid_modes = ["extract", "embedded", "none"]
        if mode.lower() in valid_modes:
            self.options.subtitle.mode = mode.lower()
        else:
            logger.warning(f"Unknown subtitle mode '{mode}', using 'extract'")
            self.options.subtitle.mode = "extract"

    def set_gpu_options(
        self,
        gpu_type: str = None,
        force_software: bool = None,
        gpu_partial: bool = None,
    ) -> None:
        """Set GPU options in one call"""
        # GPU type is determined by settings_manager.get_selected_gpu()
        if force_software is not None:
            self.options.encoding.use_gpu = not force_software

        if gpu_partial is not None:
            self.options.encoding.gpu_partial = gpu_partial

    def set_trim_times(
        self, start: Optional[float] = None, end: Optional[float] = None
    ) -> None:
        """Set trim start and end times in seconds"""
        if start and start > 0:
            self.options.trim.start_time = start

        if end and end > 0:
            self.options.trim.end_time = end

        logger.info(
            f"Set trim times: start={self.options.trim.start_time}, end={self.options.trim.end_time}"
        )

    def set_video_effects(
        self,
        brightness=None,
        contrast=None,
        saturation=None,
        gamma=None,
        gamma_r=None,
        gamma_g=None,
        gamma_b=None,
        gamma_weight=None,
        hue=None,
        exposure=None,
    ):
        """Set video effect parameters"""
        if brightness is not None:
            self.options.video_effects.brightness = max(
                -1.0, min(1.0, float(brightness))
            )
        if contrast is not None:
            self.options.video_effects.contrast = max(0.0, min(2.0, float(contrast)))
        if saturation is not None:
            self.options.video_effects.saturation = max(
                0.0, min(2.0, float(saturation))
            )
        if gamma is not None:
            self.options.video_effects.gamma = max(0.0, min(16.0, float(gamma)))
        if gamma_r is not None:
            self.options.video_effects.gamma_r = max(0.0, min(16.0, float(gamma_r)))
        if gamma_g is not None:
            self.options.video_effects.gamma_g = max(0.0, min(16.0, float(gamma_g)))
        if gamma_b is not None:
            self.options.video_effects.gamma_b = max(0.0, min(16.0, float(gamma_b)))
        if gamma_weight is not None:
            self.options.video_effects.gamma_weight = max(
                0.0, min(1.0, float(gamma_weight))
            )
        if hue is not None:
            self.options.video_effects.hue = max(-3.14, min(3.14, float(hue)))
        if exposure is not None:
            self.options.video_effects.exposure = max(-3.0, min(3.0, float(exposure)))

        logger.info(
            f"Set video effects: brightness={self.options.video_effects.brightness}, "
            + f"contrast={self.options.video_effects.contrast}"
        )

    def set_crop_margins(
        self,
        left=None,
        right=None,
        top=None,
        bottom=None,
        video_width=None,
        video_height=None,
    ):
        """Set crop margins for the video"""
        if left is not None:
            self.options.crop.left = max(0, int(left))
        if right is not None:
            self.options.crop.right = max(0, int(right))
        if top is not None:
            self.options.crop.top = max(0, int(top))
        if bottom is not None:
            self.options.crop.bottom = max(0, int(bottom))

        # Store original dimensions if provided
        if video_width is not None:
            self.options.video_width = max(0, int(video_width))
        if video_height is not None:
            self.options.video_height = max(0, int(video_height))

        # Update crop width and height
        if self.options.video_width > 0 and self.options.video_height > 0:
            self.options.crop.width = (
                self.options.video_width
                - self.options.crop.left
                - self.options.crop.right
            )
            self.options.crop.height = (
                self.options.video_height
                - self.options.crop.top
                - self.options.crop.bottom
            )

        # Update enabled flag
        self.options.crop.enabled = (
            self.options.crop.left > 0
            or self.options.crop.right > 0
            or self.options.crop.top > 0
            or self.options.crop.bottom > 0
        )

        logger.info(
            f"Set crop margins: left={self.options.crop.left}, right={self.options.crop.right}, "
            + f"top={self.options.crop.top}, bottom={self.options.crop.bottom}"
        )

    def get_crop_dimensions(self):
        """Get final crop dimensions as width:height:x:y format for ffmpeg"""
        # Update from settings manager if available
        if self.settings_manager:
            crop_params = self.settings_manager.get_crop_params()
            self.options.crop.left = crop_params["x"]
            self.options.crop.top = crop_params["y"]
            self.options.crop.right = self.settings_manager.get("crop-right", 0)
            self.options.crop.bottom = self.settings_manager.get("crop-bottom", 0)
            self.options.crop.enabled = crop_params["enabled"]

        # Only apply crop if we have valid video dimensions and crop is enabled
        if (
            not self.options.crop.enabled
            or self.options.video_width <= 0
            or self.options.video_height <= 0
        ):
            return None

        # Calculate the final dimensions
        width = (
            self.options.video_width - self.options.crop.left - self.options.crop.right
        )
        height = (
            self.options.video_height - self.options.crop.top - self.options.crop.bottom
        )

        # Ensure the dimensions are valid
        if width <= 0 or height <= 0:
            logger.warning(f"Invalid crop dimensions: width={width}, height={height}")
            return None

        crop_dim = f"{width}:{height}:{self.options.crop.left}:{self.options.crop.top}"
        return crop_dim

    def _build_video_filter(self) -> str:
        """Build video filter string for effects like brightness and crop"""
        # Update from settings manager if available
        if self.settings_manager:
            self._init_from_settings_manager()

        # Build filters
        effects = self.options.video_effects
        filters = []

        # Add crop filter if enabled
        crop_dimensions = self.get_crop_dimensions()
        if crop_dimensions:
            filters.append(f"crop={crop_dimensions}")

        # Add hue adjustment (separate filter)
        if effects.hue != 0.0:
            # FFmpeg hue filter uses degrees (0-360) rather than radians
            hue_degrees = effects.hue * 180 / 3.14159
            filters.append(f"hue=h={hue_degrees}")

        # Add exposure adjustment
        if effects.exposure != 0.0:
            filters.append(f"exposure=exposure={effects.exposure}")

        # Add color adjustments using eq filter
        eq_parts = []
        if effects.brightness != 0:
            eq_parts.append(f"brightness={effects.brightness}")

        if effects.contrast != 1.0:
            ff_contrast = (effects.contrast - 1.0) * 2  # Convert to FFmpeg scale
            eq_parts.append(f"contrast={ff_contrast}")

        if effects.saturation != 1.0:
            eq_parts.append(f"saturation={effects.saturation}")

        if effects.gamma != 1.0:
            eq_parts.append(f"gamma={effects.gamma}")

        if effects.gamma_r != 1.0:
            eq_parts.append(f"gamma_r={effects.gamma_r}")

        if effects.gamma_g != 1.0:
            eq_parts.append(f"gamma_g={effects.gamma_g}")

        if effects.gamma_b != 1.0:
            eq_parts.append(f"gamma_b={effects.gamma_b}")

        if effects.gamma_weight != 1.0:
            eq_parts.append(f"gamma_weight={effects.gamma_weight}")

        if eq_parts:
            filters.append("eq=" + ":".join(eq_parts))

        # Add resolution scaling if set
        if self.options.encoding.video_resolution:
            filters.append(f"scale={self.options.encoding.video_resolution}")

        # Combine all filters
        if filters:
            filter_str = ",".join(filters)
            return filter_str
        else:
            return ""

    # ...existing methods with dataclass improvements...

    def get_ffmpeg_filter_options(self):
        """Return the current video adjustments as FFmpeg filter options"""
        # Update from settings manager to ensure we have the latest values
        if self.settings_manager:
            self._init_from_settings_manager()

        # Build filter string using dataclasses
        effects = self.options.video_effects
        filters = []

        # Add crop filter if enabled
        crop_dimensions = self.get_crop_dimensions()
        if crop_dimensions:
            filters.append(f"crop={crop_dimensions}")

        # Add hue adjustment
        if effects.hue != 0.0:
            hue_degrees = effects.hue * 180 / 3.14159  # Convert radians to degrees
            filters.append(f"hue=h={hue_degrees}")

        # Add exposure adjustment
        if effects.exposure != 0.0:
            filters.append(f"exposure=exposure={effects.exposure}")

        # Add color adjustments using eq filter
        eq_parts = []
        if effects.brightness != 0:
            eq_parts.append(f"brightness={effects.brightness}")

        if effects.contrast != 1.0:
            ff_contrast = (effects.contrast - 1.0) * 2
            eq_parts.append(f"contrast={ff_contrast}")

        if effects.saturation != 1.0:
            eq_parts.append(f"saturation={effects.saturation}")

        if effects.gamma != 1.0:
            eq_parts.append(f"gamma={effects.gamma}")

        if effects.gamma_r != 1.0:
            eq_parts.append(f"gamma_r={effects.gamma_r}")

        if effects.gamma_g != 1.0:
            eq_parts.append(f"gamma_g={effects.gamma_g}")

        if effects.gamma_b != 1.0:
            eq_parts.append(f"gamma_b={effects.gamma_b}")

        if effects.gamma_weight != 1.0:
            eq_parts.append(f"gamma_weight={effects.gamma_weight}")

        if eq_parts:
            filters.append("eq=" + ":".join(eq_parts))

        # Combine all filters
        if filters:
            return ",".join(filters)
        else:
            return "null"  # Default filter for FFmpeg when no effect is needed

    def get_video_info(self) -> Dict[str, Any]:
        """
        Get detailed information about the video file using ffprobe
        
        Returns:
            dict: A dictionary containing video information with streams and format details
        """
        if not self.options.input_file or not os.path.exists(self.options.input_file):
            print(f"Error: Input file not found: {self.options.input_file}")
            return {}
            
        try:
            # Use ffprobe to get video information in JSON format
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                self.options.input_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Parse the JSON output
            info = json.loads(result.stdout)
            return info
            
        except subprocess.CalledProcessError as e:
            print(f"Error running ffprobe: {e}")
            if e.stderr:
                print(f"ffprobe stderr: {e.stderr}")
            return {}
        except json.JSONDecodeError as e:
            print(f"Error parsing ffprobe output: {e}")
            return {}
        except Exception as e:
            print(f"Unexpected error getting video info: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def extract_frame(self, position: float, output_file: str, quality: int = 2) -> bool:
        """
        Extract a single frame from the video at the given position with all effects applied
        
        Args:
            position (float): Position in seconds to extract frame from
            output_file (str): Path where to save the extracted frame
            quality (int): JPEG quality level (1-31, lower is better)
            
        Returns:
            bool: True if frame extraction was successful
        """
        if not self.options.input_file or not os.path.exists(self.options.input_file):
            print(f"Error: Input file not found: {self.options.input_file}")
            return False
        
        try:
            # Build video filter options based on current settings
            video_filter = self._build_video_filter()
            
            # Format the time position in HH:MM:SS.mmm format
            position_str = self._format_time(position)
            
            # Build the FFmpeg command
            cmd = [
                self.ffmpeg_executable,
                "-y",  # Overwrite output files without asking
                "-ss", position_str,  # Seek to position
                "-i", self.options.input_file,  # Input file
                "-vframes", "1",  # Extract one frame
                "-q:v", str(quality),  # Set quality level
            ]
            
            # Add filter if we have any
            if video_filter:
                cmd.extend(["-vf", video_filter])
            
            # Add output file
            cmd.append(output_file)
            
            # Run the command
            print(f"Extracting frame at position {position_str} to {output_file}")
            result = subprocess.run(cmd, 
                                   stderr=subprocess.PIPE, 
                                   stdout=subprocess.PIPE, 
                                   text=True)
            
            if result.returncode != 0:
                print(f"Frame extraction failed: {result.stderr}")
                return False
            
            return os.path.exists(output_file)
            
        except Exception as e:
            print(f"Error extracting frame: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def _format_time(self, seconds: float) -> str:
        """Format seconds as HH:MM:SS.mmm for FFmpeg"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:.3f}"

    def convert_with_progress(self, progress_dialog) -> tuple:
        """
        Run the conversion process with progress updates to a progress dialog
        
        Args:
            progress_dialog: Progress dialog object with update_progress and update_status methods
            
        Returns:
            tuple: (success, output_path, error_message)
        """
        if not self.options.input_file or not os.path.exists(self.options.input_file):
            return False, None, f"Input file not found: {self.options.input_file}"
        
        if not self.options.output_file:
            return False, None, "No output file specified"
        
        try:
            # Store the progress dialog to reference it later
            self.progress_dialog = progress_dialog
            
            # Make sure we're using the latest settings from settings manager
            if self.settings_manager:
                self._init_from_settings_manager()
            
            # Build the FFmpeg command
            cmd = self._build_ffmpeg_command()
            if not cmd:
                return False, None, "Failed to build FFmpeg command"
            
            # Print the full FFmpeg command for debugging
            cmd_str = " ".join(cmd)
            print(f"Running FFmpeg command: {cmd_str}")
            
            # Start the conversion process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Store the process in the progress dialog to allow cancellation
            if hasattr(progress_dialog, "set_process"):
                progress_dialog.set_process(process)
            
            # Initialize variables for tracking progress
            duration = None
            elapsed_time = 0
            output_file_created = False
            
            # Process FFmpeg output in real-time
            for line in process.stderr:
                # Check if we've been cancelled
                if hasattr(progress_dialog, "was_cancelled") and progress_dialog.was_cancelled():
                    process.terminate()
                    return False, None, "Conversion cancelled by user"
                
                # Extract video duration if not already known
                if not duration and "Duration:" in line:
                    try:
                        duration_str = line.split("Duration: ")[1].split(",")[0].strip()
                        h, m, s = map(float, duration_str.split(":"))
                        duration = h * 3600 + m * 60 + s
                    except Exception as e:
                        print(f"Error parsing duration: {e}")
                
                # Extract current time position
                if duration and "time=" in line:
                    try:
                        time_str = line.split("time=")[1].split()[0].strip()
                        if ":" in time_str:
                            h, m, s = map(float, time_str.split(":"))
                            elapsed_time = h * 3600 + m * 60 + s
                        else:
                            elapsed_time = float(time_str)
                        
                        # Calculate and report progress
                        if elapsed_time > 0 and duration > 0:
                            progress = min(0.99, elapsed_time / duration)
                            progress_dialog.update_progress(
                                progress, f"{int(progress * 100)}%"
                            )
                            progress_dialog.update_status(
                                f"Converting... {elapsed_time:.1f}s / {duration:.1f}s"
                            )
                    except Exception as e:
                        print(f"Error parsing progress: {e}")
                
                # Check if output file was created
                if not output_file_created and os.path.exists(self.options.output_file):
                    output_file_created = True
                
                # Print FFmpeg output for debugging
                print(line.strip())
            
            # Wait for process to finish
            process.wait()
            
            # Check if successful
            success = (process.returncode == 0)
            
            if success:
                progress_dialog.update_progress(1.0, "100%")
                progress_dialog.update_status("Conversion completed successfully!")
                logger.info(f"Conversion completed successfully: {self.options.output_file}")
                return True, self.options.output_file, None
            else:
                error_message = "Conversion failed with unknown error"
                return False, None, error_message
                
        except Exception as e:
            logger.error(f"Error during conversion: {e}")
            import traceback
            traceback.print_exc()
            return False, None, f"Error during conversion: {str(e)}"

    def _build_ffmpeg_command(self) -> list:
        """Build the FFmpeg command based on conversion options"""
        if not self.options.input_file or not self.options.output_file:
            return []
        
        # Basic FFmpeg command
        cmd = [self.ffmpeg_executable, "-y"]  # -y to overwrite output without asking
        
        # Add trim start option if set
        if self.options.trim.start_time and self.options.trim.start_time > 0:
            cmd.extend(["-ss", str(self.options.trim.start_time)])
        
        # Input file
        cmd.extend(["-i", self.options.input_file])
        
        # Add trim end option if set (use -t for duration after input)
        if self.options.trim.end_time and self.options.trim.end_time > 0:
            if self.options.trim.start_time and self.options.trim.start_time > 0:
                # Use duration instead of end time when start time is specified
                duration = self.options.trim.end_time - self.options.trim.start_time
                if duration > 0:
                    cmd.extend(["-t", str(duration)])
            else:
                # Use -to when no start time specified
                cmd.extend(["-to", str(self.options.trim.end_time)])
        
        # Video filters for effects and crop
        video_filter = self._build_video_filter()
        if video_filter:
            cmd.extend(["-vf", video_filter])
        
        # Video codec options
        if self.options.force_copy_video:
            # Just copy the video stream without re-encoding
            cmd.extend(["-c:v", "copy"])
        else:
            # Add video encoding options
            encoder = self.options.encoding.video_encoder
            quality = self.options.encoding.video_quality
            preset = self.options.encoding.preset
            
            if encoder == "h264":
                cmd.extend(["-c:v", "libx264"])
                cmd.extend(["-crf", str(self.QUALITY_PRESETS[quality]["cq_value"])])
                cmd.extend(["-preset", preset])
            elif encoder == "h265":
                cmd.extend(["-c:v", "libx265"])
                cmd.extend(["-crf", str(self.QUALITY_PRESETS[quality]["cq_value"])])
                cmd.extend(["-preset", preset])
            elif encoder == "av1":
                cmd.extend(["-c:v", "libaom-av1"])
                cmd.extend(["-crf", str(self.QUALITY_PRESETS[quality]["cq_value"])])
                cmd.extend(["-cpu-used", "5"])  # AV1 preset equivalent
            elif encoder == "vp9":
                cmd.extend(["-c:v", "libvpx-vp9"])
                cmd.extend(["-crf", str(self.QUALITY_PRESETS[quality]["cq_value"])])
                cmd.extend(["-b:v", "0"])  # Use CRF mode
            else:
                # Default to H.264
                cmd.extend(["-c:v", "libx264"])
                cmd.extend(["-crf", "23"])
                cmd.extend(["-preset", "medium"])
        
        # Audio handling
        if self.options.audio.handling == "copy":
            cmd.extend(["-c:a", "copy"])
        elif self.options.audio.handling == "reencode":
            cmd.extend(["-c:a", "aac"])
            if self.options.audio.bitrate:
                cmd.extend(["-b:a", self.options.audio.bitrate])
            if self.options.audio.channels:
                cmd.extend(["-ac", self.options.audio.channels])
        elif self.options.audio.handling == "none":
            cmd.extend(["-an"])  # No audio
        
        # Subtitle handling
        if self.options.subtitle.mode == "extract":
            cmd.extend(["-c:s", "mov_text"])  # Extract subtitles in MP4 format
        elif self.options.subtitle.mode == "embedded":
            cmd.extend(["-c:s", "copy"])  # Copy subtitles as-is
        elif self.options.subtitle.mode == "none":
            cmd.extend(["-sn"])  # No subtitles
        
        # Add output file
        cmd.append(self.options.output_file)
        
        return cmd
