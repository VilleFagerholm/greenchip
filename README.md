# Draft Sentinel (App Lab app)

Warns locally when heat escapes an empty room through an open window: the LED matrix first,
then a soft beep after 60 s. Built from the "SensorsCamera" / greenchip prototype. Spec, plan,
and contracts: `specs/002-draft-sentinel/`.

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

1. Open `apps/draft-sentinel/` in App Lab and run it. No bricks are needed.
2. **Choose the window area**: hold the knob 3 s. While the countdown shows, wave a hand in
   front of the window and read the `AREA 6x4` maps in the log (digits = motion per cell).
   Set `WINDOW_AREA` in `python/sentinel/config.py` to the box of those cells as fractions
   (columns / 6, rows / 4), e.g. columns 2-4 and rows 1-3 → `(2/6, 1/4, 5/6, 4/4)`. Restart.
3. **Calibrate with the window closed**: hold the knob 3 s and step back. After 5 s without
   movement it captures for 3 s and shows ✓ (✗ if it never saw stillness within 60 s).
4. Set the app as the board's startup app in App Lab so it runs after power-on without a laptop.

Re-calibrate whenever the camera is moved, or if false "suspect" marks appear at night.

## Knob

| Gesture | Effect |
|---------|--------|
| Turn | Sensitivity ±0.1 °C (0.3-2.0), shown as `d.d` for 3 s; saved |
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

No bricks, no network listeners, no network code. Frames are shrunk to 160×120, compared with
the previous one, and dropped; no image is ever saved, logged, or sent. The only camera-derived
value stored is the window reference: 24 contrast-normalised brightness numbers of the window
area, captured while nobody moves.

## Known limits

- Moving the camera invalidates the reference: re-calibrate.
- Moving sun patches inside the window area can change cells; alone this stays a silent suspect.
- Day/night contrast can shift the comparison; if false suspects appear at night, calibrate at
  night.
- The board clock has no time server; after an offline power cycle dates may be wrong
  (`clock_unsynced=1` in `SUMMARY`).

## Tests

From the repository root: `.venv/bin/pytest -q`.
