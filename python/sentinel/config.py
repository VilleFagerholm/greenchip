"""Every detection threshold, timing, and path for the Draft Sentinel (single config location).

UI-only timings (knob polling, view durations, sounds) live in sketch/ui_config.h.
Defaults: specs/002-draft-sentinel/data-model.md and research.md.
"""

import os
from pathlib import Path

# --- camera (research R2) ---
CAMERA_DEVICES = ("/dev/video0", "/dev/video1", "/dev/video2", "/dev/video3")
CAPTURE_SIZE = (640, 480)
FRAME_SIZE = (160, 120)
BLUR_KSIZE = 5
CAPTURE_FPS = 5
CAMERA_STALL_S = 3.0
CAMERA_REOPEN_S = 5.0

# --- live video preview ---
VIDEO_SERVER_ENABLED = True
VIDEO_SERVER_HOST = "0.0.0.0"
VIDEO_SERVER_PORT = 8080
VIDEO_JPEG_QUALITY = 75

# --- motion (research R3) ---
PIXEL_DIFF_THRESHOLD = 20
MOTION_MIN_FRACTION = 0.004
LIGHTING_FRACTION = 0.5
MIN_DETAIL_STD = 6.0

# --- occupancy ---
MOVEMENT_MIN_FRAMES = 2
MOVEMENT_WINDOW_S = 2.0
EMPTY_AFTER_S = 600.0

# --- window watch (research R4) ---
WINDOW_AREA = (0.0, 0.0, 1.0, 1.0)  # x0, y0, x1, y1 as fractions of the frame
GRID = (6, 4)  # columns, rows
CELL_DIFF_THRESHOLD = 0.8
MIN_CHANGED_CELLS = 3
WINDOW_PERSIST_S = 30.0
WINDOW_CLEAR_S = 10.0
WINDOW_SAMPLE_S = 1.0
MIN_AREA_STD = 2.0
CALIB_STILL_S = 5.0
CALIB_TIMEOUT_S = 60.0
CALIB_CAPTURE_S = 3.0

# --- outdoor noise (research R12): loudness only, never recorded ---
MIC_ENABLED = True
MIC_SAMPLE_RATE = 16000
MIC_STALL_S = 3.0
MIC_REOPEN_S = 5.0
SILENCE_DBFS = -100.0
NOISE_FLOOR_WINDOW_S = 10.0     # background = quiet part of the last 10 s
NOISE_FLOOR_PERCENTILE = 20     # ignores speech, doors, footsteps
NOISE_BASELINE_WINDOW_S = 600.0
NOISE_BASELINE_MIN_S = 120.0
NOISE_RISE_DB = 6.0
NOISE_HYSTERESIS_DB = 2.0
NOISE_PERSIST_S = 30.0
NOISE_CLEAR_S = 10.0
MIN_SIGNALS_FOR_DRAFT = 2       # any 2 of cold, window, noise (constitution II)

# --- temperature (research R5) ---
CURRENT_WINDOW_S = 10.0
NORMAL_WINDOW_S = 600.0
NORMAL_MIN_S = 120.0
COLD_HYSTERESIS_C = 0.2
NORMAL_MAX_RISE_C_PER_MIN = 0.1  # a hand or breath on the sensor cannot drag the normal up
THERMO_MIN_C = -20.0
THERMO_MAX_C = 60.0
THERMO_FROZEN_S = 300.0

# --- sensitivity (deadband) ---
SENS_DEFAULT_C = 1.0
SENS_MIN_C = 0.3
SENS_MAX_C = 2.0
SENS_STEP_C = 0.1
SENS_SAVE_DELAY_S = 2.0

# --- alerts (research R7) ---
GRACE_S = 60.0
REPEAT_S = 30.0
MAX_ALERT_S = 1800.0
CLEAR_CONFIRM_S = 20.0  # the 15 min snooze countdown lives in the sketch (SNOOZE_MS)
ALERT_STRONG_AFTER_BEEPS = 4  # beeps 5+ use the firmer three-note alert
THANKS_ON_CLOSE = True  # short chime when the window is closed after an alert

# --- loop, Bridge, log ---
LOOP_INTERVAL_S = 1.0
BRIDGE_TIMEOUT_S = 1.0
MCU_TIMEOUT_S = 3.0
STATUS_EVERY_S = 5.0
SUMMARY_EVERY_S = 3600.0
SELFTEST_REPEAT_S = 10.0

# --- files (research R9) ---
DATA_DIR = Path(os.environ.get("SENTINEL_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
EVENTS_MAX_LINES = 2000
CLOCK_VALID_YEAR = 2026
