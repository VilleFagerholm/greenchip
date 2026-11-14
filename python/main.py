"""Draft Sentinel, Linux side: camera motion + window watch, fusion, alerts, events, settings.

Frames are downscaled, compared, and dropped; only derived numbers leave the camera thread.
Setup UI (feature 003) is a DEV_BUILD-only LAN page; JPEG preview only while preview is on.
Contracts: specs/002-draft-sentinel/contracts/, specs/003-sensor-camera-ui/contracts/.
"""

import threading
import time
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
from arduino.app_utils import App, Bridge, Logger

from sentinel import config, motion
from sentinel import settings as settings_store
from sentinel.alerts import AUDIBLE, CAPPED, NONE, SNOOZED, VISUAL, AlertEngine
from sentinel.bridge_state import (
    KNOB_CALIBRATE, KNOB_SUMMARY, McuState, ResetDetector, parse_knob_event, parse_mcu_state,
)
from sentinel.events import EventLog, event_line
from sentinel.fusion import DRAFT, SUSPECT, fuse
from sentinel.occupancy import EMPTY, OCCUPIED, Occupancy
from sentinel.noise_watch import NoiseWatch, rms_dbfs
from sentinel.energy_heatmap import EnergyHeatmap, intensity_from_sample
from sentinel.activity_density import ActivityDensity
from sentinel.feedback import feedback_message
from sentinel.presence import PresenceState
from sentinel.preview import DevPreviewState
from sentinel.room_normal import RoomNormal
from sentinel.selftest import DISABLED, MISSING, NO_DETAIL, OK, STALLED, Parts, ThermoRules
from sentinel.snapshot import build_snapshot
from sentinel.status_line import format_status
from sentinel import ui_commands as cmd
from sentinel.ui_server import create_ui_server, start_ui_server_thread
from sentinel.window_watch import (
    CAPTURING, DONE, FAILED, READY, WAITING, Calibration, WindowWatch, summarize,
)
from sentinel.motion import MOTION



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
energy = EnergyHeatmap()
activity = ActivityDensity()
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

# Setup UI / Development Preview Mode (features 003–004)
preview = DevPreviewState(allowed=config.DEV_BUILD, max_fps=config.PREVIEW_MAX_FPS)
ui_snapshot: dict | None = None
_last_preview_active = False
_last_preview_push_at = -config.PREVIEW_PUSH_EVERY_S
ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
ui_commands: deque[tuple[str, dict]] = deque()
presence = PresenceState()
noise_threshold_db = stored.noise_threshold_db
last_area_map: str | None = None
preview_zoom = float(config.PREVIEW_ZOOM_DEFAULT)
_hog = None
_last_hog_at = -1e9


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


def on_preview_zoom(zoom_x10) -> None:
    """Knob rotate while preview is on → digital zoom (1.0×–3.0×)."""
    global preview_zoom
    try:
        z = int(zoom_x10) / 10.0
    except (TypeError, ValueError):
        return
    z = max(config.PREVIEW_ZOOM_MIN, min(config.PREVIEW_ZOOM_MAX, z))
    with lock:
        preview_zoom = z


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


def encode_preview_jpeg(frame_bgr, zoom: float = 1.0):
    """In-memory JPEG for Development Preview Mode. Never call imwrite / save to disk.

    zoom > 1 crops the center of the frame (knob zoom while preview is on).
    """
    import cv2

    frame = frame_bgr
    z = max(config.PREVIEW_ZOOM_MIN, min(config.PREVIEW_ZOOM_MAX, float(zoom or 1.0)))
    if z > 1.01:
        fh, fw = frame.shape[:2]
        cw = max(1, int(fw / z))
        ch = max(1, int(fh / z))
        x0 = max(0, (fw - cw) // 2)
        y0 = max(0, (fh - ch) // 2)
        frame = frame[y0:y0 + ch, x0:x0 + cw]
    w, h = config.PREVIEW_JPEG_SIZE
    small = cv2.resize(frame, (w, h))
    x0, y0, x1, y1 = config.WINDOW_AREA
    cv2.rectangle(
        small,
        (int(x0 * w), int(y0 * h)),
        (max(0, int(x1 * w) - 1), max(0, int(y1 * h) - 1)),
        (0, 200, 255),
        1,
    )
    ok, buf = cv2.imencode(
        ".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), config.PREVIEW_JPEG_QUALITY]
    )
    return buf.tobytes() if ok else None


def offer_preview_bytes(jpeg: bytes, now: float) -> None:
    """Serve JPEG only while preview is on. No boxes by default (latency). Never imwrite."""
    if not preview.active or not jpeg:
        return
    preview.offer_frame(jpeg, now)


def _get_hog():
    global _hog
    if _hog is None:
        import cv2
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        _hog = hog
    return _hog


def hog_person_present(frame_bgr) -> bool:
    """Rare, cheap HOG confirm. Call only when due — never every frame."""
    import cv2

    try:
        w, h = config.HOG_SIZE
        small = cv2.resize(frame_bgr, (w, h))
        rects, _weights = _get_hog().detectMultiScale(
            small,
            winStride=config.HOG_WIN_STRIDE,
            padding=(4, 4),
            scale=config.HOG_SCALE,
        )
        return len(rects) > 0
    except Exception:
        return False


def camera_loop() -> None:
    """Motion-first presence; HOG at most once per HOG_INTERVAL_S. Preview encode rate-capped."""
    global camera_state, last_frame_at, latest_sample, latest_summary, area_sum, area_count
    global _last_hog_at
    period = 1.0 / config.CAPTURE_FPS
    preview_period = 1.0 / max(1, config.PREVIEW_MAX_FPS)
    last_preview_encode_at = -preview_period
    while True:
        cap = None
        try:
            cap = open_camera()
            if cap is None:
                with lock:
                    camera_state = MISSING
                    presence.set_camera_ok(False)
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

                # 1) Fast path: motion + snappy presence (do this before HOG/JPEG).
                cur = motion.prepare(frame)
                found = False
                if prev is not None:
                    sample = motion.compute(prev, cur, now)
                    state = NO_DETAIL if sample.detail < config.MIN_DETAIL_STD else OK
                    summary = None
                    if now - last_summary_at >= config.WINDOW_SAMPLE_S:
                        last_summary_at = now
                        summary = summarize(cur)
                    # HOG only when due and camera healthy — standing still still counts.
                    if state == OK and now - _last_hog_at >= config.HOG_INTERVAL_S:
                        _last_hog_at = now
                        found = hog_person_present(frame)
                    with lock:
                        camera_state = state
                        last_frame_at = now
                        latest_sample = sample
                        if summary is not None:
                            latest_summary = summary
                        occupancy.update(now, sample, state == OK)
                        presence.set_camera_ok(state == OK)
                        if state == OK:
                            if found:
                                presence.note(now)
                                occupancy.note_person(now)
                            elif sample.kind == MOTION:
                                presence.note(now)
                            presence.clear_if_expired(now)
                        # Activity density grid (feature 007) — derived cells only, every frame pair.
                        if state == OK:
                            activity.set_camera_available(True)
                            activity.note_cells(
                                now,
                                motion.cell_motion_floats(prev, cur, grid=config.ACTIVITY_GRID),
                            )
                        else:
                            activity.set_camera_available(False)
                        if want_area_map:
                            cells = motion.cell_motion_map(prev, cur)
                            area_sum = cells if area_sum is None else [
                                [a + b for a, b in zip(ra, rb)] for ra, rb in zip(area_sum, cells)]
                            area_count += 1

                # 2) Preview JPEG last and rate-capped (encoding is costly).
                if preview.active and now - last_preview_encode_at >= preview_period:
                    with lock:
                        z = preview_zoom
                    jpeg = encode_preview_jpeg(frame, zoom=z)
                    if jpeg is not None:
                        offer_preview_bytes(jpeg, now)
                        last_preview_encode_at = now
                del frame
                prev = cur
                time.sleep(max(0.0, period - (uptime() - started)))
        except Exception as exc:
            logger.warning(f"Camera error: {exc}")
        finally:
            if cap is not None:
                cap.release()
        with lock:
            camera_state = STALLED if last_frame_at is not None else MISSING
            presence.set_camera_ok(False)
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
    global calibration, want_area_map, area_sum, area_count, last_area_map
    phase = calibration.update(now, summary, moving, wall_iso())
    mcu_call("show_calibration", phase, getattr(calibration, "seconds", 0))
    if phase == WAITING:
        with lock:
            grid, count = area_sum, area_count
            area_sum, area_count = None, 0
        if grid and count:
            rows = [" ".join(str(min(9, round(v / count))) for v in row) for row in grid]
            map_text = f"AREA {config.GRID[0]}x{config.GRID[1]}\n" + "\n".join(rows)
            last_area_map = map_text
            print(map_text, flush=True)
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


def get_snapshot() -> dict:
    with lock:
        if ui_snapshot is not None:
            return dict(ui_snapshot)
    return build_snapshot(
        temperature_c=None,
        humidity_pct=None,
        occupancy="unknown",
        sensitivity_c=stored.sensitivity_c,
        snooze_remaining_s=0,
        cold=False,
        window=False,
        noise=False,
        alert="idle",
        parts={p: MISSING for p in ("thermo", "knob", "buzzer", "matrix", "camera", "mic")},
        preview=preview.state_name,
        uptime_s=uptime(),
    )


def sync_preview_mark(now: float) -> None:
    global _last_preview_active, _last_preview_push_at
    active = preview.active
    if active != _last_preview_active or now - _last_preview_push_at >= config.PREVIEW_PUSH_EVERY_S:
        _last_preview_active = active
        _last_preview_push_at = now
        mcu_call("set_preview_active", 1 if active else 0)


def draft_badge(fusion, alert_name: str) -> tuple[str, str]:
    if alert_name in (AUDIBLE, VISUAL, CAPPED):
        return "DRAFT", "Heat-loss alert — check the window"
    if alert_name == SNOOZED:
        return "SNOOZED", "Alert snoozed"
    if fusion.state == SUSPECT or alert_name == "suspect":
        return "SUSPECT", "One heat-loss signal only"
    if fusion.state == DRAFT:
        return "DRAFT", "Draft conditions met"
    return "ALL GOOD", "No heat loss signal"


def handle_ui_command(name: str, data: dict, now: float, alive: bool, snooze_active: bool) -> None:
    global noise_threshold_db, calibration, want_area_map, area_sum, area_count, sens_changed_at
    if name == "sensitivity":
        value = cmd.clamp_sensitivity(data.get("value"))
        if value is None:
            return
        stored.sensitivity_c = value
        sens_changed_at = now
        if alive:
            mcu_call("set_settings", int(round(value * 10)),
                     int(round(config.SENS_MIN_C * 10)), int(round(config.SENS_MAX_C * 10)))
        settings_store.save(config.DATA_DIR, stored)
    elif name == "noise_threshold":
        value = cmd.clamp_noise_threshold(data.get("value"))
        if value is None:
            return
        noise_threshold_db = value
        stored.noise_threshold_db = value
        settings_store.save(config.DATA_DIR, stored)
    elif name == "snooze":
        want = data.get("on")
        if want is None:
            want = not snooze_active
        mcu_call("set_snooze", 1 if want else 0)
    elif name == "calibrate":
        if calibration is None:
            calibration = Calibration(now)
            with lock:
                want_area_map, area_sum, area_count = True, None, 0
            logger.info("Window calibration started (UI)")
    elif name == "summary":
        summary = event_log.summary_today(datetime.now())
        mcu_call("show_summary", summary.events, int(round(summary.degree_minutes)))
    elif name == "confidence":
        pass  # YOLOX removed; keep route as no-op for older clients


def on_http_command(name: str, body: dict) -> dict:
    """HTTP thread → queue for the main loop."""
    if name == "sensitivity":
        value = cmd.clamp_sensitivity(body.get("value"))
        if value is None:
            return {"ok": False, "error": "bad_value"}
    elif name == "noise_threshold":
        value = cmd.clamp_noise_threshold(body.get("value"))
        if value is None:
            return {"ok": False, "error": "bad_value"}
    elif name == "confidence":
        value = cmd.clamp_confidence(body.get("value"))
        if value is None:
            return {"ok": False, "error": "bad_value"}
    with lock:
        ui_commands.append((name, body))
    return {"ok": True}


def tick() -> None:
    global settings_synced, sens_changed_at, thermo_was_ok, mcu_reset
    global last_status_at, last_status_key, last_summary_at, selftest_first_at, selftest_repeated
    global ui_snapshot

    now = uptime()
    ensure_camera_thread()

    with lock:
        m, seen_at, reset = mcu, mcu_seen_at, mcu_reset
        mcu_reset = False
        events = list(knob_events)
        knob_events.clear()
        cmds = list(ui_commands)
        ui_commands.clear()
        cam = camera_state
        if last_frame_at is not None and now - last_frame_at > config.CAMERA_STALL_S and cam == OK:
            cam = STALLED
        if cam != OK:
            occupancy.update(now, None, False)
            presence.set_camera_ok(False)
        sample, summary = latest_sample, latest_summary
        occ = occupancy.state(now)
        moving = occupancy.moving_now(now)
        last_move = None if occupancy.last_movement_t is None else now - occupancy.last_movement_t
        mic = mic_state
        if mic == OK and (last_chunk_at is None or now - last_chunk_at > config.MIC_STALL_S):
            mic = STALLED
        if mic == OK:
            noise.update(now, freeze=occ == OCCUPIED or noise.signal or alerts.event is not None)
            energy.set_available(True)
            energy.update(
                now,
                noise.last_db,
                noise.rise_db,
                baseline_ready=noise.baseline_db is not None,
            )
            inten, _mode, _raw = intensity_from_sample(
                noise.last_db, noise.rise_db, noise.baseline_db is not None
            )
            activity.set_acoustic(True, inten)
        else:
            energy.set_available(False)
            activity.set_acoustic(False, 0.0)
        if cam != OK:
            activity.set_camera_available(False)
        noise_signal, noise_rise = noise.signal, noise.rise_db
        heatmap_snap = energy.to_snapshot()
        activity_snap = activity.to_snapshot()
        zoom = preview_zoom
        presence.clear_if_expired(now)
        people_present = presence.present
        area_map_text = last_area_map

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
    snooze_active = alive and m is not None and m.snooze_remaining_s > 0
    for cname, cdata in cmds:
        handle_ui_command(cname, cdata, now, alive, snooze_active)
    if calibration is not None:
        run_calibration(now, summary, moving)

    # decision chain
    if thermo_ok:
        room.update(now, m.temp_c, sensitivity, freeze=room.cold or alerts.event is not None)
    window.update(now, summary, moving)
    fusion = fuse(occ, room.cold and thermo_ok, window.signal, thermo_ok, window.status == READY,
                  noise_signal, mic == OK)
    snooze_active = alive and m is not None and m.snooze_remaining_s > 0
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
    sync_preview_mark(now)

    alert_name = result.level
    if alert_name == NONE:
        alert_name = "suspect" if fusion.state == SUSPECT else "idle"
    label, reason = draft_badge(fusion, alert_name)
    day = event_log.summary_today(datetime.now())
    noise_db = noise.last_db if mic == OK else None
    noise_med = noise.median_db(now) if mic == OK else None
    calib_info = None
    if calibration is not None:
        phase_name = {WAITING: "waiting", CAPTURING: "capturing", DONE: "done", FAILED: "failed"}.get(
            calibration.phase, "working")
        calib_info = {
            "phase": phase_name,
            "seconds": calibration.seconds,
            "area_map": area_map_text,
        }
    snap = build_snapshot(
        temperature_c=m.temp_c if alive and parts.ok("thermo") else None,
        humidity_pct=m.humidity_pct if alive and parts.ok("thermo") else None,
        occupancy=occ,
        sensitivity_c=sensitivity,
        snooze_remaining_s=m.snooze_remaining_s if alive else 0,
        cold=room.cold and thermo_ok,
        window=window.signal if window.status == READY else False,
        noise=bool(noise_signal) if mic == OK else False,
        alert=alert_name,
        parts={p: parts.state(p) for p in ("thermo", "knob", "buzzer", "matrix", "camera", "mic")},
        preview=preview.state_name,
        uptime_s=now,
        room_normal_c=room.normal_c if thermo_ok else None,
        drop_c=room.drop_c if thermo_ok else None,
        last_move_s=last_move,
        people_present=people_present,
        people_count=0,
        draft_label=label,
        draft_reason=reason,
        noise_db=noise_db,
        noise_median_db=noise_med,
        noise_rise_db=noise_rise if mic == OK else None,
        noise_noisy=(noise_db is not None and noise_db >= noise_threshold_db),
        noise_threshold_db=noise_threshold_db,
        noise_heatmap=heatmap_snap,
        activity_heatmap=activity_snap,
        calibration=calib_info,
        today={
            "events": day.events,
            "minutes": round(day.total_minutes, 1),
            "degree_minutes": round(day.degree_minutes, 1),
            "recent": event_log.recent_today(datetime.now()),
        },
        detections=[],
        feedback=feedback_message(occ, alert_name, 1 if people_present else 0),
        product_title=config.PRODUCT_TITLE,
        preview_zoom=zoom,
    )
    with lock:
        ui_snapshot = snap

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
Bridge.provide("preview_zoom", on_preview_zoom)

# Lightweight HOG + motion presence runs inside camera_loop (all builds). No YOLOX brick.
camera_thread = threading.Thread(target=camera_loop, daemon=True)
camera_thread.start()
if config.MIC_ENABLED:
    threading.Thread(target=microphone_loop, daemon=True).start()

# Setup UI only in development builds (constitution Development Preview Mode / FR-005).
_ui_server = create_ui_server(
    allowed=config.DEV_BUILD,
    port=config.UI_PORT,
    assets_dir=ASSETS_DIR,
    get_snapshot=get_snapshot,
    preview=preview,
    on_command=on_http_command,
)
if _ui_server is not None:
    start_ui_server_thread(_ui_server)
    logger.info(f"Setup UI on port {config.UI_PORT} (SENTINEL_DEV_BUILD=1)")
else:
    logger.info("Setup UI disabled (product build)")

App.run(user_loop=loop)
