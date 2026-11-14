# Draft Sentinel

**Zero-Cloud Open-Window & Draft Energy Sentinel** — cuts winter district-heating waste in
homes, schools, and offices **without cloud surveillance**.

Warns locally when heat escapes an **empty** room through an open window or balcony door:
LED matrix first, then a soft beep after 60 s. Development builds expose a **Room HUD** on
the LAN (climate, occupancy, acoustic energy strip, **12×8 activity density** overlay,
gated camera preview with knob zoom). Specs: `specs/002-draft-sentinel/` …
`specs/007-activity-density-heatmap/`.

### Hardware roles

| Part | Role |
|------|------|
| **Camera** | Room occupancy / presence; open-window geometry vs closed calibration |
| **Thermo** | Sudden cold-air draft drop near the sill |
| **Mic** | Outdoor wind/traffic rush or HVAC hum (loudness only — nothing recorded) |
| **Knob** | Comfort/eco deadband (sensitivity); snooze; calibrate; zoom while preview on |
| **LED matrix + Buzzer** | Instant local reminders when heat escapes an empty room |

## Demo script (~2 min)

1. **Pitch (15 s)** — Zero-cloud sentinel for open windows & drafts; all inference stays on
   the UNO Q; Room HUD is opt-in for setup only.
2. **Closed & calm** — HUD shows ALL GOOD; Cold / Window / Noise off; room occupied or empty
   as appropriate; matrix idle.
3. **Open the window** — after ~30 s Window → on (and often Cold / Noise). One signal =
   SUSPECT (silent). Two+ with room empty = DRAFT → matrix then beep.
4. **People matter** — walk in view: occupancy occupied / presence present; alerts stay quiet
   while the room is used. Leave ~10 min (or demo with a shorter idle if configured) for empty.
5. **Knob** — short press = snooze 15 min; hold 3 s = calibrate closed window; with **Preview
   on**, rotate = digital zoom 1.0×–3.0×. Activity map shows where movement is (not °C).
6. **Close** — Nothing leaves the device: no cloud, no saved video/audio.

## How it decides

An alert needs the **room empty** (no camera movement for 10 minutes, camera healthy) **and any
two** of:

- **Cold draft**: the sill temperature is below the room's normal (10-minute median) by at
  least the sensitivity (default 1.0 °C).
- **Window changed**: the window area looks different from its saved "closed" reference for at
  least 30 s.
- **Outdoor noise**: the room's background loudness is at least 6 dB above its usual level for
  at least 30 s, as when wind or traffic comes in. The camera microphone measures loudness only;
  nothing is recorded and speech is never analysed.

One signal alone only shows a silent "suspect" mark. Movement never beeps. Without a window
calibration, cold plus noise can still raise an alert.

## Wiring

USB-C hub with the power supply on the UNO Q; USB camera on the hub. Thermo, Knob, and Buzzer
daisy-chained on Qwiic. Put the Thermo near the window sill; point the camera so it sees the
room and the window. Every part is optional: the app keeps running with what it finds.

## Setup (once)

1. Open `apps/draft-sentinel/` in App Lab and run it. **No** YOLOX / `video_object_detection`
   brick and **no** `web_ui` — presence uses lightweight OpenCV HOG + motion on the board.
2. **Room HUD** (development builds): on a laptop on the same LAN, open
   `http://<board-ip>:7000/` (override with `SENTINEL_UI_PORT`). Title:
   **Draft Sentinel**. Panels poll `GET /api/snapshot` about once a second.
  Presence is **present/absent** (not a headcount). Vision panel shows a larger rectangular
  preview with a **12×8 activity density** overlay (movement, not °C); loudness applies a
  **room-wide** acoustic boost (not per-cell sound location). The noise panel keeps an
  **energy-over-time** strip. Density and strip bins stay in RAM only. Controls: snooze,
  calibrate, show-on-board. Turn **Preview on** only when aiming the camera (matrix column
  12 rows 1–6); with preview on, **rotate the knob to zoom** the live JPEG (1.0×–3.0×).
  Live JPEG only while preview is on (`/api/preview/frame` → 204 when off). Frames and
  audio are never saved. Bounding boxes are not required.
3. **Choose the window area**: hold the knob 3 s. While the countdown shows, wave a hand in
   front of the window and read the `AREA 6x4` maps in the log (digits = motion per cell), or
   use the HUD preview. Set `WINDOW_AREA` in `python/sentinel/config.py` to the box of
   those cells as fractions (columns / 6, rows / 4), e.g. columns 2-4 and rows 1-3 →
   `(2/6, 1/4, 5/6, 4/4)`. Restart.
4. **Calibrate with the window closed**: hold the knob 3 s and step back, or use **Calibrate**
   on the HUD. After 5 s without movement it captures for 3 s and shows ✓ (✗ if it never
   saw stillness within 60 s).
5. Set the app as the board's startup app in App Lab so it runs after power-on without a laptop.

### Development vs product build

| Env | Effect |
|-----|--------|
| `SENTINEL_DEV_BUILD=1` (default) | Room HUD on `SENTINEL_UI_PORT` (7000); gated preview; presence badge |
| `SENTINEL_DEV_BUILD=0` | **Product**: no UI listener / no stream; local HOG+motion presence still assists occupancy |

Re-calibrate whenever the camera is moved, or if false "suspect" marks appear at night.

## Knob

| Gesture | Effect |
|---------|--------|
| Turn (preview **off**) | Sensitivity ±0.1 °C (0.3–2.0), shown as `d.d` for 3 s; saved |
| Turn (preview **on**) | Digital camera zoom 1.0×–3.0× |
| Short press | Snooze on/off (15 min); confirm tone; blinking corner pixel while snoozed |
| Double press | Today's summary for 5 s: event count + bar (1 column per 10 °C·min) |
| Hold 3 s | Window calibration (top row fills while holding) |

## Sounds

The buzzer only reacts to the user and to real alerts, never to motion.

| Sound | When |
|-------|------|
| Two-tone rising | App started |
| Tick, pitch rising with sensitivity / low bonk | Knob turned / turned past the end of the range |
| Falling two-tone / rising two-tone | Snooze on / off (rising three-tone when it runs out) |
| Ticks at 1 s and 2 s, chirp at 3 s | Holding for calibration |
| Countdown ticks, rising sweep, tune / two low tones | Calibration waiting, capturing, saved / failed |
| N blips (low tone = none) | Double press: today's event count |
| Double beep every 30 s, then a firmer three-note beep from the 5th | Draft alert (after the 60 s grace period) |
| Short C-E-G chime | Window closed after an alert: thank you |

Turn the knob ticks off with `KNOB_TICKS` in `sketch/ui_config.h`. The firmer beep and the chime
are set by `ALERT_STRONG_AFTER_BEEPS` and `THANKS_ON_CLOSE` in `python/sentinel/config.py`.

## Matrix legend

| Shown | Meaning |
|-------|---------|
| Five bars (5 s after boot) | Self-test, left to right: Thermo, Knob, Buzzer, Camera, Microphone. Full bar = ok, dot = missing |
| Two digits + person shape | Temperature; room occupied |
| Two digits + empty box | Temperature; room empty |
| Two digits + `–` | Occupancy unknown (camera missing/covered, or the first 10 min after start) |
| `?` alternating with the occupancy mark | Window not calibrated yet: never beeps |
| Dim pixels on the bottom row | Suspect: one heat-loss signal only (left = cold, middle = window, right = noise) |
| Window icon + `↓` / box / bottom zig-zag | Draft alert with the signals that fired: cold / window / noise; blinking = beeping |
| Dim window icon + `z` | Draft while snoozed |
| Top-right pixel | Camera active |
| Column 12, rows 1–6 (dev) | Development Preview Mode on |
| Bottom-right pixel blinking | Snoozed |
| Bottom-left pixel | A part is missing or faulty |

## Log lines

`SELFTEST`, `SENTINEL` (every 5 s), `AREA` (setup only), `EVENT`, `SUMMARY`. Format:
`specs/002-draft-sentinel/contracts/logs-and-files.md`.

Status-line fields: `noise` = background rise in dB, `loud` = outdoor-noise signal, and `A` in
`parts` = microphone. To switch the microphone off, set `MIC_ENABLED = False` in
`python/sentinel/config.py`.

## Files on the board

`data/settings.json` (sensitivity and the 24-number window reference) and `data/events.jsonl`
(one line per heat-loss event, rotated at 2000 lines), under the app folder. Override the
location with the `SENTINEL_DATA_DIR` environment variable if the app folder does not persist.

## Privacy

Frames are shrunk for motion / HOG, compared, and dropped; no image is ever saved or logged
(`imwrite` is never used). The only camera-derived value stored is the window reference:
24 contrast-normalised brightness numbers of the window area, captured while nobody moves.
Presence is a non-identifying present/absent flag (no faces, no required headcount).

In **development builds** only, the Room HUD may stream an opt-in live preview
(Development Preview Mode: off after every reboot, matrix mark while on, latest JPEG in RAM
only). **Product builds** (`SENTINEL_DEV_BUILD=0`) start no HTTP server and cannot enable a
camera stream; local presence may still assist occupancy on-device. No Socket.IO / `web_ui`.

## Known limits

- Moving the camera invalidates the reference: re-calibrate.
- Moving sun patches inside the window area can change cells; alone this stays a silent suspect.
- Day/night contrast can shift the comparison; if false suspects appear at night, calibrate at
  night.
- The board clock has no time server; after an offline power cycle dates may be wrong
  (`clock_unsynced=1` in `SUMMARY`).

## Tests

From the repository root: `.venv/bin/pytest -q`.
