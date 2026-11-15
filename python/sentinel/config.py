"""Every detection threshold, timing, and path for the Draft Sentinel (single config location).

UI-only timings (knob polling, view durations, sounds) live in sketch/ui_config.h.
Defaults: specs/002-draft-sentinel/data-model.md and research.md.
"""

import os
from pathlib import Path

# --- camera (research R2; brick preview in DEV_BUILD for people count) ---
CAMERA_DEVICES = ("/dev/video0", "/dev/video1", "/dev/video2", "/dev/video3")
CAPTURE_SIZE = (640, 480)
FRAME_SIZE = (160, 120)
BLUR_KSIZE = 5
CAPTURE_FPS = 8  # keep loop responsive; presence is motion-first
CAMERA_STALL_S = 3.0
CAMERA_REOPEN_S = 5.0
PERSON_LABEL = "person"
DEFAULT_CONFIDENCE = 0.45  # VideoObjectDetection / YOLO brick threshold
PERSON_HOLD_S = 1.5
PRESENCE_HOLD_S = 1.5  # people_present clears within ~2 s (SC-002)
# Still-image ObjectDetection fallback: infer at most this often (keeps HUD smooth).
DETECT_INTERVAL_S = 0.12
UI_FPS = 10
DETECTIONS_MAX = 12
UI_RECENT_EVENTS = 5
PRODUCT_TITLE = "Draft Sentinel"
PRODUCT_TAGLINE = "Zero-cloud open-window & draft energy sentinel"


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
GRID = (6, 4)  # columns, rows — window calibration / area finder
ACTIVITY_GRID = (12, 8)  # activity density heatmap (2× window grid)
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
NOISE_UI_WINDOW_S = 0.5
NOISE_UI_MEDIAN_S = 10.0
DEFAULT_NOISE_THRESHOLD_DB = -35.0
NOISE_THRESHOLD_MIN_DB = -90.0
NOISE_THRESHOLD_MAX_DB = 0.0
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

# --- acoustic energy heatmap (feature 006): RAM-only derived bins, never PCM ---
HEATMAP_WINDOW_S = 600.0        # ~10 minutes visible
HEATMAP_BIN_S = 10.0            # coarse columns (allowed 5–10)
HEATMAP_LABEL = "Energy over time"
HEATMAP_RISE_FULL_DB = NOISE_RISE_DB  # rise_db → intensity 1.0 near outdoor-noise scale
HEATMAP_ABS_QUIET_DB = -60.0    # absolute fallback: quiet floor
HEATMAP_ABS_LOUD_DB = DEFAULT_NOISE_THRESHOLD_DB  # toward noisy UI threshold

# --- activity density heatmap (feature 007): vision grid, not temperature ---
ACTIVITY_DECAY_HALFLIFE_S = 5.0
ACTIVITY_ACOUSTIC_MAX = 1.75    # room-wide multiplier ceiling (≥1)
ACTIVITY_LABEL = "Activity / movement density · not temperature"
# Digital preview zoom via knob while Development Preview is on (1.0 … 3.0).
PREVIEW_ZOOM_MIN = 1.0
PREVIEW_ZOOM_MAX = 3.0
PREVIEW_ZOOM_DEFAULT = 1.0

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

# --- setup UI / Development Preview Mode (feature 003; constitution I) ---
# Default on for hackathon setup; set SENTINEL_DEV_BUILD=0 for a deployed product install.
DEV_BUILD = os.environ.get("SENTINEL_DEV_BUILD", "1") == "1"
UI_PORT = int(os.environ.get("SENTINEL_UI_PORT", "7000"))
PREVIEW_MAX_FPS = 10  # snappier YOLO preview; still rate-capped in DevPreviewState
PREVIEW_JPEG_SIZE = (480, 270)  # wider 16:9-ish preview for the rectangular HUD stage
PREVIEW_JPEG_QUALITY = 70  # slightly lighter encode for lower lag
PREVIEW_PUSH_EVERY_S = 5.0  # re-send set_preview_active so MCU reset recovers the mark
