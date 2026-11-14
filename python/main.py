"""Draft Sentinel, Linux side: camera motion + window watch, fusion, alerts, events, settings.

Frames are downscaled, compared, and dropped; only derived numbers leave the camera thread.
Contracts: specs/002-draft-sentinel/contracts/.
"""

import threading
import time
import traceback
from collections import deque
from datetime import datetime

import numpy as np
from arduino.app_utils import App, Bridge, Logger

from sentinel import config, motion
from sentinel import settings as settings_store
from sentinel.alerts import AUDIBLE, CAPPED, SNOOZED, VISUAL, AlertEngine
from sentinel.bridge_state import (
    KNOB_CALIBRATE, KNOB_SUMMARY, McuState, ResetDetector, parse_knob_event, parse_mcu_state,
)
from sentinel.events import EventLog, event_line
from sentinel.fusion import DRAFT, SUSPECT, fuse
from sentinel.occupancy import EMPTY, OCCUPIED, Occupancy
from sentinel.noise_watch import NoiseWatch, rms_dbfs
from sentinel.room_normal import RoomNormal
from sentinel.selftest import DISABLED, MISSING, NO_DETAIL, OK, STALLED, Parts, ThermoRules
from sentinel.status_line import format_status
from sentinel.window_watch import DONE, READY, WAITING, Calibration, WindowWatch, summarize

logger = Logger("sentinel")
START = time.monotonic()


def uptime() -> float:
    return time.monotonic() - START


def wall_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


lock = threading.Lock()

# --- state shared with Bridge callbacks and the camera thread (guarded by lock) ---
mcu: McuState | None = None
mcu_seen_at: float | None = None
mcu_reset = False
knob_events: deque[int] = deque()

camera_state = MISSING
last_frame_at: float | None = None
latest_sample: motion.MotionSample | None = None
latest_summary = None
want_area_map = False
area_sum = None
area_count = 0
occupancy = Occupancy()
noise = NoiseWatch()
mic_state = MISSING if config.MIC_ENABLED else DISABLED
last_chunk_at: float | None = None

# --- loop-only state ---
stored = settings_store.load(config.DATA_DIR)
window = WindowWatch(stored.window_reference)
room = RoomNormal()
alerts = AlertEngine()
event_log = EventLog(config.DATA_DIR)
parts = Parts()
thermo_rules = ThermoRules()
resets = ResetDetector()
calibration: Calibration | None = None
settings_synced = False
sens_changed_at: float | None = None
thermo_was_ok = False


def mcu_call(name: str, *args, default=None):
    """Call a sketch function; a Bridge problem never stops the app."""
    try:
        return Bridge.call(name, *args, timeout=config.BRIDGE_TIMEOUT_S)
    except Exception as exc:
        logger.debug(f"Bridge call {name} failed: {exc}")
        return default


# --- sketch -> Python notifications ---

def on_mcu_state(thermo, temp_x100, hum_x10, knob, buzzer, sens_x10, snooze_s, matrix, uptime_s) -> None:
    global mcu, mcu_seen_at, mcu_reset
    state = parse_mcu_state((thermo, temp_x100, hum_x10, knob, buzzer, sens_x10, snooze_s, matrix, uptime_s))
    if state is None:
        logger.warning("Malformed mcu_state")
        return
    with lock:
        if resets.update(state.uptime_s):
            mcu_reset = True
        mcu = state
        mcu_seen_at = uptime()


def on_knob_event(kind) -> None:
    kind = parse_knob_event(kind)
    if kind is not None:
        with lock:
            knob_events.append(kind)


# --- camera thread (research R2): derived numbers only ---

def open_camera():
    import cv2

    for dev in config.CAMERA_DEVICES:
        cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAPTURE_SIZE[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAPTURE_SIZE[1])
            ok, frame = cap.read()
            if ok and frame is not None:
                logger.info(f"Camera opened on {dev}")
                return cap
        cap.release()
    return None


def camera_loop() -> None:
    global camera_state, last_frame_at, latest_sample, latest_summary, area_sum, area_count
    period = 1.0 / config.CAPTURE_FPS
    while True:
        cap = None
        try:
            cap = open_camera()
            if cap is None:
                with lock:
                    camera_state = MISSING
                time.sleep(config.CAMERA_REOPEN_S)
                continue
            prev = None
            last_summary_at = -config.WINDOW_SAMPLE_S
            while True:
                started = uptime()
                ok, frame = cap.read()
                now = uptime()
                if not ok or frame is None:
                    with lock:
                        stale = last_frame_at is None or now - last_frame_at > config.CAMERA_STALL_S
                    if stale:
                        break
                    time.sleep(0.1)
                    continue
                cur = motion.prepare(frame)
                del frame
                if prev is not None:
                    sample = motion.compute(prev, cur, now)
                    state = NO_DETAIL if sample.detail < config.MIN_DETAIL_STD else OK
                    summary = None
                    if now - last_summary_at >= config.WINDOW_SAMPLE_S:
                        last_summary_at = now
                        summary = summarize(cur)
                    with lock:
                        camera_state = state
                        last_frame_at = now
                        latest_sample = sample
                        if summary is not None:
                            latest_summary = summary
                        occupancy.update(now, sample, state == OK)
                        if want_area_map:
                            cells = motion.cell_motion_map(prev, cur)
                            area_sum = cells if area_sum is None else [
                                [a + b for a, b in zip(ra, rb)] for ra, rb in zip(area_sum, cells)]
                            area_count += 1
                prev = cur
                time.sleep(max(0.0, period - (uptime() - started)))
        except Exception as exc:
            logger.warning(f"Camera error: {exc}")
        finally:
            if cap is not None:
                cap.release()
        with lock:
            camera_state = STALLED if last_frame_at is not None else MISSING
        time.sleep(config.CAMERA_REOPEN_S)


# --- microphone thread (research R12): one loudness number per chunk, audio dropped ---

def open_microphone():
    from arduino.app_peripherals.microphone import Microphone

    try:
        return Microphone(Microphone.USB_MIC_1, sample_rate=Microphone.RATE_16K,
                          channels=Microphone.CHANNELS_MONO)
    except Exception as exc:
        logger.warning(f"USB microphone not available ({exc}); trying the default device")
        return Microphone(sample_rate=Microphone.RATE_16K, channels=Microphone.CHANNELS_MONO)


def microphone_loop() -> None:
    global mic_state, last_chunk_at
    warned = False
    while True:
        try:
            mic = open_microphone()
            mic.start()
            logger.info("Microphone opened")
            warned = False
            for chunk in mic.stream():
                if chunk is None:
                    continue
                level = rms_dbfs(np.asarray(chunk, dtype=np.int16))
                del chunk
                now = uptime()
                with lock:
                    noise.add_chunk(now, level)
                    last_chunk_at = now
                    mic_state = OK
        except Exception as exc:
            if not warned:
                logger.warning(f"Microphone error: {exc}")
                warned = True
        with lock:
            mic_state = MISSING
        time.sleep(config.MIC_REOPEN_S)


def ensure_camera_thread() -> None:
    global camera_thread
    if not camera_thread.is_alive():
        logger.warning("Camera thread stopped; restarting")
        camera_thread = threading.Thread(target=camera_loop, daemon=True)
        camera_thread.start()


# --- loop helpers ---

def handle_knob_event(kind: int, now: float, moving: bool) -> None:
    global calibration, want_area_map, area_sum, area_count
    if kind == KNOB_CALIBRATE and calibration is None:
        calibration = Calibration(now)
        with lock:
            want_area_map, area_sum, area_count = True, None, 0
        logger.info("Window calibration started")
    elif kind == KNOB_SUMMARY:
        summary = event_log.summary_today(datetime.now())
        mcu_call("show_summary", summary.events, int(round(summary.degree_minutes)))
        print(summary.line(), flush=True)


def run_calibration(now: float, summary, moving: bool) -> None:
    global calibration, want_area_map, area_sum, area_count
    phase = calibration.update(now, summary, moving, wall_iso())
    mcu_call("show_calibration", phase, calibration.seconds)
    if phase == WAITING:
        with lock:
            grid, count = area_sum, area_count
            area_sum, area_count = None, 0
        if grid and count:
            rows = [" ".join(str(min(9, round(v / count))) for v in row) for row in grid]
            print(f"AREA {config.GRID[0]}x{config.GRID[1]}\n" + "\n".join(rows), flush=True)
    if not calibration.finished:
        return
    if phase == DONE:
        stored.window_reference = calibration.reference
        settings_store.save(config.DATA_DIR, stored)
        window.set_reference(calibration.reference)
        logger.info("Window reference saved")
    else:
        logger.warning("Window calibration failed (no stillness or no usable image)")
    calibration = None
    with lock:
        want_area_map = False


def view_state(fusion, level: str) -> int:
    if fusion.state == DRAFT or level in (VISUAL, AUDIBLE, CAPPED, SNOOZED):
        return 3 if level in (AUDIBLE, CAPPED) else 2
    return 1 if fusion.state == SUSPECT else 0


OCC_CODES = {"unknown": 0, EMPTY: 1, OCCUPIED: 2}
SOUND_ALERT, SOUND_ALERT_STRONG, SOUND_THANKS = 1, 4, 5  # contracts/bridge-rpc.md play_sound kinds

last_status_at = -config.STATUS_EVERY_S
last_status_key: tuple = ()
last_summary_at = uptime()
selftest_first_at: float | None = None
selftest_repeated = False


def tick() -> None:
    global settings_synced, sens_changed_at, thermo_was_ok, mcu_reset
    global last_status_at, last_status_key, last_summary_at, selftest_first_at, selftest_repeated

    now = uptime()
    ensure_camera_thread()

    with lock:
        m, seen_at, reset = mcu, mcu_seen_at, mcu_reset
        mcu_reset = False
        events = list(knob_events)
        knob_events.clear()
        cam = camera_state
        if last_frame_at is not None and now - last_frame_at > config.CAMERA_STALL_S and cam == OK:
            cam = STALLED
        if cam != OK:
            occupancy.update(now, None, False)
        sample, summary = latest_sample, latest_summary
        occ = occupancy.state(now)
        moving = occupancy.moving_now(now)
        last_move = None if occupancy.last_movement_t is None else now - occupancy.last_movement_t
        mic = mic_state
        if mic == OK and (last_chunk_at is None or now - last_chunk_at > config.MIC_STALL_S):
            mic = STALLED
        if mic == OK:
            noise.update(now, freeze=occ == OCCUPIED or noise.signal or alerts.event is not None)
        noise_signal, noise_rise = noise.signal, noise.rise_db

    alive = m is not None and seen_at is not None and now - seen_at <= config.MCU_TIMEOUT_S
    if reset or not alive:
        settings_synced = False

    # part status
    thermo_state = thermo_rules.check(m.temp_c if alive and m.thermo_ok else None, now)
    parts.set("thermo", thermo_state, now)
    parts.set("knob", OK if alive and m.knob_ok else MISSING, now)
    parts.set("buzzer", OK if alive and m.buzzer_ok else MISSING, now)
    parts.set("matrix", OK if alive and m.matrix_ok else MISSING, now)
    parts.set("camera", cam, now)
    parts.set("mic", mic, now)
    thermo_ok = parts.ok("thermo")
    if thermo_ok and not thermo_was_ok:
        room.reset()
    thermo_was_ok = thermo_ok

    # settings sync and persistence (research R6)
    if alive and not settings_synced:
        if abs(m.sensitivity_c - stored.sensitivity_c) < 0.05:
            settings_synced = True
        else:
            mcu_call("set_settings", int(round(stored.sensitivity_c * 10)),
                     int(round(config.SENS_MIN_C * 10)), int(round(config.SENS_MAX_C * 10)))
    elif alive and abs(m.sensitivity_c - stored.sensitivity_c) >= 0.05:
        stored.sensitivity_c = settings_store.clamp_sensitivity(m.sensitivity_c)
        sens_changed_at = now
    if sens_changed_at is not None and now - sens_changed_at >= config.SENS_SAVE_DELAY_S:
        sens_changed_at = None
        settings_store.save(config.DATA_DIR, stored)
    sensitivity = stored.sensitivity_c

    for kind in events:
        handle_knob_event(kind, now, moving)
    if calibration is not None:
        run_calibration(now, summary, moving)

    # decision chain
    if thermo_ok:
        room.update(now, m.temp_c, sensitivity, freeze=room.cold or alerts.event is not None)
    window.update(now, summary, moving)
    fusion = fuse(occ, room.cold and thermo_ok, window.signal, thermo_ok, window.status == READY,
                  noise_signal, mic == OK)
    snooze_active = alive and m.snooze_remaining_s > 0
    result = alerts.step(now, fusion, room.drop_c if thermo_ok else 0.0, occ, snooze_active,
                         wall_iso(), now, sensitivity)
    if result.beep:
        strong = alerts.event is not None and alerts.event.beeps >= config.ALERT_STRONG_AFTER_BEEPS
        alerts.confirm_beep(mcu_call("play_sound", SOUND_ALERT_STRONG if strong else SOUND_ALERT,
                                     default=0) == 1)
    if result.finished is not None:
        if result.finished.end_reason == "closed" and config.THANKS_ON_CLOSE:
            mcu_call("play_sound", SOUND_THANKS)
        event_log.append(result.finished)
        print(event_line(result.finished), flush=True)
        print(event_log.summary_today(datetime.now()).line(), flush=True)

    setup = 2 if calibration is not None else (0 if window.status == READY else 1)
    cam_code = 1 if cam == OK else (0 if cam == MISSING else 2)
    mcu_call("set_view", view_state(fusion, result.level), fusion.signal_bits, OCC_CODES.get(occ, 0),
             cam_code, setup, parts.faults_mask())

    # log lines
    if alive and selftest_first_at is None:
        selftest_first_at = now
        print(parts.selftest_line(), flush=True)
    elif selftest_first_at is not None and not selftest_repeated and now - selftest_first_at >= config.SELFTEST_REPEAT_S:
        selftest_repeated = True
        print(parts.selftest_line(), flush=True)

    status_key = (occ, cam, fusion.state, result.level, parts.code(), window.status, room.cold, window.signal,
                  noise_signal)
    if status_key != last_status_key or now - last_status_at >= config.STATUS_EVERY_S:
        last_status_key, last_status_at = status_key, now
        print(format_status({
            "occ": occ, "last_move": last_move, "motion": sample.fraction if sample else None, "cam": cam,
            "temp": room.current_c if thermo_ok else None, "normal": room.normal_c if thermo_ok else None,
            "drop": room.drop_c if thermo_ok else None, "sens": sensitivity, "cold": room.cold,
            "win": window.signal if window.status == READY else None, "cells": window.changed_cells,
            "noise": noise_rise if mic == OK else None, "loud": noise_signal if mic == OK else None,
            "state": fusion.state, "alert": result.level,
            "snooze": m.snooze_remaining_s if alive else 0, "parts": parts.code(),
        }), flush=True)

    if now - last_summary_at >= config.SUMMARY_EVERY_S:
        last_summary_at = now
        print(event_log.summary_today(datetime.now()).line(), flush=True)


def loop() -> None:
    started = uptime()
    try:
        tick()
    except Exception:  # research R10: one bad iteration never stops monitoring
        logger.error(f"Loop error:\n{traceback.format_exc()}")
    time.sleep(max(0.0, config.LOOP_INTERVAL_S - (uptime() - started)))


Bridge.provide("mcu_state", on_mcu_state)
Bridge.provide("knob_event", on_knob_event)

camera_thread = threading.Thread(target=camera_loop, daemon=True)
camera_thread.start()
if config.MIC_ENABLED:
    threading.Thread(target=microphone_loop, daemon=True).start()

App.run(user_loop=loop)
