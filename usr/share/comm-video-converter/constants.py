"""
Constants for the Comm Video Converter application.
Global settings, paths, and configuration values.
"""

import os

# Application metadata
APP_ID = "org.communitybig.converter"
APP_NAME = "Comm Video Converter"
APP_VERSION = "1.0.0"

APP_DEVELOPERS = ["Tales A. Mendonça", "Bruno Gonçalves Araujo"]
APP_WEBSITES = ["communitybig.org", "biglinux.com.br"]

# GSettings schema ID
SCHEMA_ID = "org.communitybig.converter"

# Paths to executables
CONVERT_SCRIPT_PATH = "/usr/bin/comm-converter"

# During development, use local path if scripts are not installed
if not os.path.exists(CONVERT_SCRIPT_PATH):
    CONVERT_SCRIPT_PATH = "./comm-converter"

# UI constants
WINDOW_DEFAULT_WIDTH = 900
WINDOW_DEFAULT_HEIGHT = 620
CONTENT_MAX_WIDTH = 800
CONTENT_TIGHTENING_THRESHOLD = 600

# File dialog filters
VIDEO_FILE_MIME_TYPES = [
    "video/mp4",
    "video/x-matroska",
    "video/x-msvideo",
    "video/quicktime",
    "video/webm",
    "video/x-flv",
    "video/mpeg",
    "video/3gpp",
    "video/x-ms-wmv",
    "video/ogg",
    "video/mp2t",
]

# Encoding options
GPU_OPTIONS = ["Auto-detect", "nvidia", "amd", "intel", "software"]
VIDEO_QUALITY_OPTIONS = [
    "Default",
    "veryhigh",
    "high",
    "medium",
    "low",
    "verylow",
    "superlow",
]
VIDEO_CODEC_OPTIONS = [
    "Default (h264)",
    "h264 (MP4)",
    "h265 (HEVC)",
    "av1 (AV1)",
    "vp9 (VP9)",
]
PRESET_OPTIONS = [
    "Default",
    "ultrafast",
    "veryfast",
    "faster",
    "medium",
    "slow",
    "veryslow",
]
SUBTITLE_OPTIONS = ["embedded", "extract (SRT)", "none"]
AUDIO_OPTIONS = ["copy", "reencode", "none"]
