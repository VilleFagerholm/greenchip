#pragma once

#include "ui_config.h"

// LED matrix views; layout per specs/002-draft-sentinel/contracts/led-matrix-views.md.

const uint8_t COLS = 13;
const uint8_t ROWS = 8;

enum LinuxState : uint8_t { LS_IDLE = 0, LS_SUSPECT = 1, LS_DRAFT = 2, LS_DRAFT_AUDIBLE = 3 };
enum Occ : uint8_t { OCC_UNKNOWN = 0, OCC_EMPTY = 1, OCC_OCCUPIED = 2 };
enum Setup : uint8_t { SETUP_READY = 0, SETUP_NEEDED = 1, SETUP_CALIBRATING = 2 };
enum CalibPhase : uint8_t { CAL_WAITING = 0, CAL_CAPTURING = 1, CAL_DONE = 2, CAL_FAILED = 3 };

const uint8_t SIG_COLD = 1;
const uint8_t SIG_WINDOW = 2;
const uint8_t SIG_NOISE = 4;
const uint8_t FAULT_THERMO = 1, FAULT_KNOB = 2, FAULT_BUZZER = 4, FAULT_CAMERA = 8, FAULT_MIC = 16;

// 3x5 glyphs, one byte per row, bit 2 = left column.
const uint8_t DIGITS[10][5] = {
  {7, 5, 5, 5, 7}, {2, 6, 2, 2, 7}, {7, 1, 7, 4, 7}, {7, 1, 7, 1, 7}, {5, 5, 7, 1, 1},
  {7, 4, 7, 1, 7}, {7, 4, 7, 5, 7}, {7, 1, 1, 1, 1}, {7, 5, 7, 5, 7}, {7, 5, 7, 1, 7},
};
const uint8_t GLYPH_PERSON[5] = {2, 7, 2, 5, 5};
const uint8_t GLYPH_EMPTY[5] = {7, 5, 5, 5, 7};
const uint8_t GLYPH_UNKNOWN[5] = {0, 0, 7, 0, 0};
const uint8_t GLYPH_QUESTION[5] = {7, 1, 2, 0, 2};
const uint8_t GLYPH_COLD[5] = {2, 2, 2, 7, 2};
const uint8_t GLYPH_WINDOW[5] = {7, 5, 5, 5, 7};
const uint8_t GLYPH_Z[5] = {7, 1, 2, 4, 7};
const uint8_t GLYPH_DELTA[5] = {0, 2, 5, 7, 0};

// 5x6 icons, bit 4 = left column.
const uint8_t ICON_OPEN_WINDOW[6] = {0b11111, 0b10011, 0b10101, 0b11001, 0b10011, 0b11111};
const uint8_t ICON_CHECK[6] = {0b00000, 0b00001, 0b00010, 0b10100, 0b01000, 0b00000};
const uint8_t ICON_CROSS[6] = {0b00000, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001};

struct View {
  float tempC;            // NAN when the Thermo is missing
  uint8_t state;          // LinuxState
  uint8_t signals;        // SIG_* bits
  uint8_t occupancy;      // Occ
  uint8_t camera;         // 0 missing, 1 ok, 2 stalled / no detail
  uint8_t setup;          // Setup
  uint8_t faults;         // FAULT_* bits
  bool snoozed;
};

inline void setPx(uint8_t* fb, int x, int y, uint8_t v = LED_ON) {
  if (x >= 0 && x < COLS && y >= 0 && y < ROWS) fb[y * COLS + x] = v;
}

inline bool blinkOn(unsigned long now, unsigned long halfPeriodMs) {
  return (now / halfPeriodMs) % 2 == 0;
}

inline void drawGlyph(uint8_t* fb, int x0, int y0, const uint8_t* rows, uint8_t v = LED_ON) {
  for (int row = 0; row < 5; row++)
    for (int col = 0; col < 3; col++)
      if (rows[row] & (4 >> col)) setPx(fb, x0 + col, y0 + row, v);
}

inline void drawIcon(uint8_t* fb, int x0, int y0, const uint8_t* rows, uint8_t v = LED_ON) {
  for (int row = 0; row < 6; row++)
    for (int col = 0; col < 5; col++)
      if (rows[row] & (16 >> col)) setPx(fb, x0 + col, y0 + row, v);
}

// Two digits at columns x0..x0+6 (0-99); dashes when not a number.
inline void drawTwoDigits(uint8_t* fb, int x0, int y0, float value) {
  if (isnan(value)) {
    for (int x = x0; x <= x0 + 6; x++) setPx(fb, x, y0 + 2);
    return;
  }
  int v = constrain((int)lroundf(value), 0, 99);
  if (v >= 10) drawGlyph(fb, x0, y0, DIGITS[v / 10]);
  drawGlyph(fb, x0 + 4, y0, DIGITS[v % 10]);
}

const uint8_t SELFTEST_PARTS = 5;

inline void drawSelftest(uint8_t* fb, const bool ok[SELFTEST_PARTS]) {
  // Five bars, left to right: Thermo, Knob, Buzzer, Camera, Microphone.
  // Full bar = ok, single dot = missing.
  for (int i = 0; i < SELFTEST_PARTS; i++) {
    int x = 2 + 2 * i;
    if (ok[i]) {
      for (int y = 1; y <= 6; y++) setPx(fb, x, y);
    } else {
      setPx(fb, x, 6);
    }
  }
}

inline void drawCalibration(uint8_t* fb, uint8_t phase, uint8_t seconds, unsigned long sincePhaseMs) {
  switch (phase) {
    case CAL_WAITING: drawTwoDigits(fb, 3, 1, seconds); break;
    case CAL_CAPTURING: {
      int lit = min((int)COLS - 2, (int)(sincePhaseMs * (COLS - 2) / CALIB_CAPTURE_MS) + 1);
      for (int x = 1; x <= lit; x++) {
        setPx(fb, x, 3);
        setPx(fb, x, 4);
      }
      break;
    }
    case CAL_DONE: drawIcon(fb, 4, 1, ICON_CHECK); break;
    default: drawIcon(fb, 4, 1, ICON_CROSS); break;
  }
}

inline void drawSensitivity(uint8_t* fb, int sensX10) {
  drawGlyph(fb, 0, 1, DIGITS[constrain(sensX10 / 10, 0, 9)]);
  setPx(fb, 4, 5);  // decimal point
  drawGlyph(fb, 5, 1, DIGITS[sensX10 % 10]);
  drawGlyph(fb, 10, 1, GLYPH_DELTA);
}

inline void drawSummary(uint8_t* fb, int events, int degreeMinutes) {
  drawTwoDigits(fb, 0, 1, events);
  int cols = constrain((degreeMinutes + 9) / 10, 0, 5);
  for (int i = 0; i < cols; i++)
    for (int y = 2; y <= 5; y++) setPx(fb, 8 + i, y);
}

inline void drawSignalMarks(uint8_t* fb, uint8_t signals, uint8_t v) {
  if (signals & SIG_COLD) drawGlyph(fb, 6, 1, GLYPH_COLD, v);
  if (signals & SIG_WINDOW) drawGlyph(fb, 10, 1, GLYPH_WINDOW, v);
  if (signals & SIG_NOISE)  // sound wave along the bottom
    for (int x = 6; x <= 11; x++) setPx(fb, x, (x % 2) ? 6 : 7, v);
}

inline void drawDraft(uint8_t* fb, const View& s, unsigned long now) {
  if (s.snoozed) {
    drawIcon(fb, 0, 1, ICON_OPEN_WINDOW, LED_DIM);
    drawGlyph(fb, 7, 1, GLYPH_Z);
    return;
  }
  if (s.state == LS_DRAFT_AUDIBLE && !blinkOn(now, BLINK_ALERT_MS)) return;
  drawIcon(fb, 0, 1, ICON_OPEN_WINDOW);
  drawSignalMarks(fb, s.signals, LED_ON);
}

inline void drawIdle(uint8_t* fb, const View& s, unsigned long now) {
  drawTwoDigits(fb, 0, 1, s.tempC);
  const uint8_t* occ = s.occupancy == OCC_OCCUPIED ? GLYPH_PERSON
                       : s.occupancy == OCC_EMPTY  ? GLYPH_EMPTY
                                                   : GLYPH_UNKNOWN;
  // Setup needed: "?" alternates with the occupancy mark every second.
  if (s.setup == SETUP_NEEDED && blinkOn(now, 1000)) occ = GLYPH_QUESTION;
  drawGlyph(fb, 9, 1, occ);
  if (s.state == LS_SUSPECT) {
    if (s.signals & SIG_COLD) for (int x = 2; x <= 4; x++) setPx(fb, x, 7, LED_DIM);
    if (s.signals & SIG_WINDOW) for (int x = 5; x <= 7; x++) setPx(fb, x, 7, LED_DIM);
    if (s.signals & SIG_NOISE) for (int x = 8; x <= 10; x++) setPx(fb, x, 7, LED_DIM);
  }
}

// Marks shown on every view except the self-test.
// previewActive: Development Preview Mode bar on column 12 rows 1–6
// (specs/003-sensor-camera-ui/contracts/preview-and-matrix.md).
inline void drawPermanentMarks(uint8_t* fb, const View& s, unsigned long now, bool previewActive = false) {
  if (s.camera == 1) setPx(fb, 12, 0);  // camera active (constitution I)
  if (previewActive) {
    for (int y = 1; y <= 6; y++) setPx(fb, 12, y);
  }
  if (s.snoozed && blinkOn(now, BLINK_SNOOZE_MS)) setPx(fb, 12, 7);
  if (s.faults) setPx(fb, 0, 7);
}
