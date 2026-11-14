#pragma once

// UI-only timings and sounds for the microcontroller. Every detection threshold lives in
// python/sentinel/config.py; the sensitivity range arrives from Python via set_settings.

const unsigned long KNOB_READ_MS = 20;
const unsigned long FRAME_MS = 20;
const unsigned long STATE_NOTIFY_MS = 500;
const unsigned long THERMO_READ_MS = 500;
const unsigned long REPROBE_MS = 2000;
const unsigned long LINUX_SILENT_MS = 5000;

const unsigned long SHORT_PRESS_MS = 1000;
const unsigned long DOUBLE_PRESS_MS = 500;
const unsigned long HOLD_MS = 3000;
const unsigned long SNOOZE_MS = 900000UL;  // 15 min, bounded (constitution III)

const unsigned long SELFTEST_VIEW_MS = 5000;
const unsigned long SENS_VIEW_MS = 3000;
const unsigned long SNOOZE_VIEW_MS = 2000;
const unsigned long SUMMARY_VIEW_MS = 5000;
const unsigned long CALIB_RESULT_MS = 3000;
const unsigned long CALIB_STALE_MS = 3000;
const unsigned long CALIB_CAPTURE_MS = 3000;

const unsigned long BLINK_ALERT_MS = 500;    // 1 Hz
const unsigned long BLINK_SNOOZE_MS = 1000;  // once per 2 s

// Ignore implausible knob jumps (a failed read returns 0).
const int16_t KNOB_MAX_STEP = 5;

const int16_t SENS_DEFAULT_X10 = 10;

// HS3003 (Thermo); SHT31 variant answers on 0x45.
const uint8_t THERMO_I2C_ADDR = 0x44;
const uint8_t THERMO_I2C_ADDR_ALT = 0x45;

const uint8_t LED_ON = 7;  // 3-bit grayscale
const uint8_t LED_DIM = 2;

struct Note {
  uint16_t freq;
  uint16_t ms;
};
const uint8_t MAX_NOTES = 12;
const unsigned long NOTE_GAP_MS = 120;
const unsigned long MELODY_GAP_MS = 30;

// Sounds requested by Python (play_sound kind 1..5).
const Note SOUND_ALERT[] = {{880, 120}, {880, 120}};                     // 1: first beeps
const Note SOUND_CONFIRM[] = {{1200, 60}};                               // 2
const Note SOUND_FAIL[] = {{400, 200}};                                  // 3
const Note SOUND_ALERT_STRONG[] = {{880, 120}, {1100, 120}, {880, 160}};  // 4: after a few minutes
const Note SOUND_THANKS[] = {{1047, 90}, {1319, 90}, {1568, 160}};        // 5: window closed, C-E-G

// Local interaction sounds (played by the sketch itself, never for motion).
const bool KNOB_TICKS = true;  // set false for a silent knob
const Note SOUND_STARTUP[] = {{880, 120}, {1320, 160}};
const Note SOUND_SNOOZE_ON[] = {{1200, 80}, {800, 140}};
const Note SOUND_SNOOZE_OFF[] = {{800, 80}, {1200, 140}};
const Note SOUND_SNOOZE_END[] = {{800, 60}, {1000, 60}, {1200, 100}};
const Note SOUND_HOLD_DONE[] = {{1500, 40}, {1900, 60}};
const Note SOUND_CAPTURE[] = {{900, 40}, {1100, 40}, {1300, 40}, {1500, 40}};
const Note SOUND_CALIB_OK[] = {{1047, 90}, {1319, 90}, {1568, 90}, {2093, 200}};
const Note SOUND_CALIB_FAIL[] = {{500, 150}, {350, 300}};
const Note SOUND_NO_EVENTS[] = {{600, 200}};

const uint16_t TICK_MS = 15;
const uint16_t TICK_BASE_HZ = 600;     // tick pitch = base + sensitivity_x10 * step
const uint16_t TICK_STEP_HZ = 60;
const uint16_t BONK_HZ = 250;          // turned against the end of the range
const uint16_t HOLD_TICK_HZ = 1000;
const uint16_t COUNTDOWN_TICK_HZ = 1400;
const uint16_t SUMMARY_BLIP_HZ = 1600;
const uint8_t SUMMARY_MAX_BLIPS = 9;
const unsigned long TICK_MIN_GAP_MS = 50;  // fast spins do not machine-gun the buzzer
