#!/usr/bin/env python3
"""
Constants for the Comm Big Converter application.
Contains paths to executables, application settings, and other constants.
"""

import os

# Application metadata
APP_ID = "org.communitybig.converter"
APP_NAME = "Comm Video Converter"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Tales A. Mendonça"
APP_CONTACT = "talesam@gmail.com"

# GSettings schema ID
SCHEMA_ID = "org.communitybig.converter"

# Paths to executables
CONVERT_BIG_PATH = "/usr/bin/convert-big"
MKV_MP4_ALL_PATH = "/usr/bin/mkv-mp4-all"

# During development, use local path if scripts are not installed
if not os.path.exists(CONVERT_BIG_PATH):
    CONVERT_BIG_PATH = "./convert-big.sh"
if not os.path.exists(MKV_MP4_ALL_PATH):
    MKV_MP4_ALL_PATH = "./mkv-mp4-all.sh"

# Default settings
DEFAULT_MAX_PROCESSES = 2
DEFAULT_MIN_MP4_SIZE_KB = 1024  # 1MB
DEFAULT_LOG_FILENAME = "mkv-mp4-convert.log"

# UI constants
WINDOW_DEFAULT_WIDTH = 800
WINDOW_DEFAULT_HEIGHT = 600
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
    "video/mp2t"
]

# Encoding options
GPU_OPTIONS = ["Auto-detect", "nvidia", "amd", "intel", "software"]
VIDEO_QUALITY_OPTIONS = ["Default", "veryhigh", "high", "medium", "low", "verylow"]
VIDEO_CODEC_OPTIONS = ["Default (h264)", "h264 (MP4)", "h265 (HEVC)", "av1 (AV1)", "vp9 (VP9)"]
PRESET_OPTIONS = ["Default", "ultrafast", "veryfast", "faster", "medium", "slow", "veryslow"]
SUBTITLE_OPTIONS = ["Default (extract)", "extract (SRT)", "embedded", "none"]
AUDIO_OPTIONS = ["Default (copy)", "copy", "reencode", "none"]
