// Draft Sentinel, microcontroller side: Modulinos, knob gestures, sounds, LED matrix views.
// The loop never blocks: missing parts are re-probed, nothing waits for Python.
// Contracts: specs/002-draft-sentinel/contracts/ (bridge-rpc, knob-gestures, led-matrix-views).

#include <Arduino_RouterBridge.h>
#include <Arduino_Modulino.h>
#include <Arduino_LED_Matrix.h>

#include "ui_config.h"
#include "views.h"

Arduino_LED_Matrix matrix;
ModulinoThermo thermo;
ModulinoKnob knob;
ModulinoBuzzer buzzer;

uint8_t frame[COLS * ROWS];

bool thermoOk = false, knobOk = false, buzzerOk = false;
float tempC = NAN, humPct = NAN;

int16_t sensX10 = SENS_DEFAULT_X10, sensMinX10 = 3, sensMaxX10 = 20;
unsigned long snoozeUntilMs = 0;

// latest state pushed by Python
uint8_t lvState = LS_IDLE, lvSignals = 0, lvOcc = OCC_UNKNOWN, lvCamera = 0, lvSetup = SETUP_NEEDED, lvFaults = 0;
unsigned long lvLastMs = 0;
bool lvSeen = false;

// overlays
unsigned long selftestUntilMs = 0, sensViewUntilMs = 0, snoozeViewUntilMs = 0, summaryUntilMs = 0;
int summaryEvents = 0, summaryDm = 0;
uint8_t calibPhase = CAL_FAILED, calibSeconds = 0;
unsigned long calibUpdatedMs = 0, calibPhaseSinceMs = 0;
bool calibActive = false;

// knob gestures
int16_t lastKnobPos = 0;
bool knobWasPressed = false, holdFired = false, pendingShort = false;
uint8_t holdTicks = 0;
unsigned long pressStartMs = 0, pendingSinceMs = 0;

unsigned long lastNotifyMs = 0, lastReprobeMs = 0, lastThermoMs = 0, lastKnobMs = 0, lastFrameMs = 0;
bool notifyNow = false;

// --- buzzer sequencer (non-blocking) ---
Note seqBuf[MAX_NOTES];
uint8_t seqLen = 0, seqIdx = 0;
unsigned long seqNextMs = 0, seqGapMs = NOTE_GAP_MS, lastTickMs = 0;
bool seqActive = false, seqIsTick = false;

#define SOUND(notes) playNotes(notes, sizeof(notes) / sizeof(notes[0]))
#define MELODY(notes) playNotes(notes, sizeof(notes) / sizeof(notes[0]), MELODY_GAP_MS)

bool playNotes(const Note* notes, uint8_t len, unsigned long gapMs = NOTE_GAP_MS, bool tick = false) {
  if (!buzzerOk) return false;
  seqLen = min(len, MAX_NOTES);
  memcpy(seqBuf, notes, seqLen * sizeof(Note));
  seqIdx = 0;
  seqNextMs = 0;
  seqGapMs = gapMs;
  seqActive = true;
  seqIsTick = tick;
  return true;
}

// Short interaction tick; never interrupts an alert or a melody.
void tick(uint16_t freq, unsigned long now) {
  if (!KNOB_TICKS || (seqActive && !seqIsTick) || now - lastTickMs < TICK_MIN_GAP_MS) return;
  lastTickMs = now;
  Note n = {freq, TICK_MS};
  playNotes(&n, 1, 0, true);
}

void blips(uint8_t count) {
  Note notes[MAX_NOTES];
  uint8_t n = min(count, min(SUMMARY_MAX_BLIPS, MAX_NOTES));
  for (uint8_t i = 0; i < n; i++) notes[i] = {SUMMARY_BLIP_HZ, 50};
  playNotes(notes, n, 120);
}

void serviceBuzzer(unsigned long now) {
  if (!seqActive || now < seqNextMs) return;
  if (seqIdx >= seqLen) {
    seqActive = false;
    return;
  }
  buzzer.tone(seqBuf[seqIdx].freq, seqBuf[seqIdx].ms);
  seqNextMs = now + seqBuf[seqIdx].ms + seqGapMs;
  seqIdx++;
}

bool snoozed(unsigned long now) { return snoozeUntilMs != 0 && now < snoozeUntilMs; }

// --- presence checks (never block; Module::begin() discovers the address only once) ---
bool i2cPresent(uint8_t addr) {
  Wire1.beginTransmission(addr);
  return Wire1.endTransmission() == 0;
}

void probeThermo() {
  bool present = i2cPresent(THERMO_I2C_ADDR) || i2cPresent(THERMO_I2C_ADDR_ALT);
  if (present && !thermoOk) present = thermo.begin();
  thermoOk = present;
  if (!present) tempC = humPct = NAN;
}

void probeKnob() {
  bool present;
  if (knob.getAddress() < 0x7F) {
    present = i2cPresent(knob.getAddress());
    if (present && !knobOk) knob.begin();
  } else {
    present = knob.begin();
  }
  if (present && !knobOk) lastKnobPos = knob.get();  // absolute position is ignored; only deltas count
  knobOk = present;
}

void probeBuzzer() {
  buzzerOk = buzzer.getAddress() < 0x7F ? i2cPresent(buzzer.getAddress()) : buzzer.begin();
}

void probeAll() {
  probeThermo();
  probeKnob();
  probeBuzzer();
}

// --- Bridge-provided functions (called from Python) ---
void set_settings(int sens, int minX10, int maxX10) {
  if (minX10 < 1 || maxX10 < minX10) return;
  sensMinX10 = minX10;
  sensMaxX10 = maxX10;
  sensX10 = constrain(sens, sensMinX10, sensMaxX10);
}

void set_view(int state, int signals, int occupancy, int camera, int setup, int faults) {
  lvState = (uint8_t)constrain(state, 0, 3);
  lvSignals = (uint8_t)(signals & 7);
  lvOcc = (uint8_t)constrain(occupancy, 0, 2);
  lvCamera = (uint8_t)constrain(camera, 0, 2);
  lvSetup = (uint8_t)constrain(setup, 0, 2);
  lvFaults = (uint8_t)(faults & 31);
  lvLastMs = millis();
  lvSeen = true;
}

int play_sound(int kind) {
  bool quiet = snoozed(millis());
  switch (kind) {
    case 1: return (!quiet && SOUND(SOUND_ALERT)) ? 1 : 0;
    case 2: return SOUND(SOUND_CONFIRM) ? 1 : 0;
    case 3: return SOUND(SOUND_FAIL) ? 1 : 0;
    case 4: return (!quiet && SOUND(SOUND_ALERT_STRONG)) ? 1 : 0;
    case 5: return MELODY(SOUND_THANKS) ? 1 : 0;
    default: return 0;
  }
}

void show_calibration(int phase, int seconds) {
  unsigned long now = millis();
  uint8_t p = (uint8_t)constrain(phase, 0, 3);
  uint8_t s = (uint8_t)constrain(seconds, 0, 99);
  bool phaseChanged = p != calibPhase || !calibActive;
  if (phaseChanged) {
    calibPhaseSinceMs = now;
    if (p == CAL_CAPTURING) MELODY(SOUND_CAPTURE);
    else if (p == CAL_DONE) MELODY(SOUND_CALIB_OK);
    else if (p == CAL_FAILED) SOUND(SOUND_CALIB_FAIL);
  }
  if (p == CAL_WAITING && (phaseChanged || s != calibSeconds)) tick(COUNTDOWN_TICK_HZ, now);
  calibPhase = p;
  calibSeconds = s;
  calibUpdatedMs = now;
  calibActive = true;
}

void show_summary(int events, int degreeMinutes) {
  summaryEvents = events;
  summaryDm = degreeMinutes;
  summaryUntilMs = millis() + SUMMARY_VIEW_MS;
  if (events > 0) blips((uint8_t)constrain(events, 0, 255));
  else SOUND(SOUND_NO_EVENTS);
}

// --- knob ---
void toggleSnooze(unsigned long now) {
  if (snoozed(now)) {
    snoozeUntilMs = 0;
    Bridge.notify("knob_event", 2);
    MELODY(SOUND_SNOOZE_OFF);
  } else {
    snoozeUntilMs = now + SNOOZE_MS;
    if (snoozeUntilMs == 0) snoozeUntilMs = 1;
    snoozeViewUntilMs = now + SNOOZE_VIEW_MS;
    Bridge.notify("knob_event", 1);
    MELODY(SOUND_SNOOZE_ON);
  }
  notifyNow = true;
}

void readKnob(unsigned long now) {
  if (pendingShort && now - pendingSinceMs >= DOUBLE_PRESS_MS) {
    pendingShort = false;
    toggleSnooze(now);
  }
  if (!knobOk) return;

  int16_t pos = knob.get();
  int16_t delta = pos - lastKnobPos;
  if (delta != 0 && abs(delta) <= KNOB_MAX_STEP) {
    int16_t before = sensX10;
    sensX10 = constrain(sensX10 + delta, sensMinX10, sensMaxX10);
    sensViewUntilMs = now + SENS_VIEW_MS;
    notifyNow = true;
    tick(sensX10 == before ? BONK_HZ : TICK_BASE_HZ + sensX10 * TICK_STEP_HZ, now);
  }
  lastKnobPos = pos;

  bool pressed = knob.isPressed();
  if (pressed && !knobWasPressed) {
    pressStartMs = now;
    holdFired = false;
    holdTicks = 0;
  } else if (pressed && !holdFired && now - pressStartMs >= HOLD_MS) {
    holdFired = true;
    pendingShort = false;
    MELODY(SOUND_HOLD_DONE);
    Bridge.notify("knob_event", 3);
  } else if (pressed && !holdFired && now - pressStartMs >= (holdTicks + 1) * 1000UL) {
    holdTicks++;
    tick(HOLD_TICK_HZ, now);
  } else if (!pressed && knobWasPressed && !holdFired && now - pressStartMs < SHORT_PRESS_MS) {
    if (pendingShort) {
      pendingShort = false;
      Bridge.notify("knob_event", 4);
    } else {
      pendingShort = true;
      pendingSinceMs = now;
    }
  }
  knobWasPressed = pressed;
}

// --- state to Python ---
void notifyState(unsigned long now) {
  long tempX100 = thermoOk && !isnan(tempC) ? lroundf(tempC * 100) : 0;
  long humX10 = thermoOk && !isnan(humPct) ? lroundf(humPct * 10) : 0;
  long snoozeLeft = snoozed(now) ? (long)((snoozeUntilMs - now) / 1000) : 0;
  Bridge.notify("mcu_state", (int)thermoOk, (int)tempX100, (int)humX10, (int)knobOk, (int)buzzerOk,
                (int)sensX10, (int)snoozeLeft, 1, (int)(now / 1000));
}

// --- drawing ---
uint8_t localFaults() {
  return (thermoOk ? 0 : FAULT_THERMO) | (knobOk ? 0 : FAULT_KNOB) | (buzzerOk ? 0 : FAULT_BUZZER);
}

void drawFrame(unsigned long now) {
  memset(frame, 0, sizeof(frame));

  bool linuxAlive = lvSeen && now - lvLastMs < LINUX_SILENT_MS;
  View v;
  v.tempC = thermoOk ? tempC : NAN;
  v.state = linuxAlive ? lvState : LS_IDLE;
  v.signals = linuxAlive ? lvSignals : 0;
  v.occupancy = linuxAlive ? lvOcc : OCC_UNKNOWN;
  v.camera = linuxAlive ? lvCamera : 0;
  v.setup = linuxAlive ? lvSetup : SETUP_READY;
  v.faults = localFaults() | (linuxAlive ? lvFaults : FAULT_CAMERA);
  v.snoozed = snoozed(now);

  if (now < selftestUntilMs) {
    bool ok[SELFTEST_PARTS] = {thermoOk, knobOk, buzzerOk, linuxAlive && lvCamera == 1,
                                linuxAlive && !(lvFaults & FAULT_MIC)};
    drawSelftest(frame, ok);
    matrix.draw(frame);
    return;
  }

  if (calibActive) {
    unsigned long age = now - calibUpdatedMs;
    bool result = calibPhase == CAL_DONE || calibPhase == CAL_FAILED;
    if ((result && age > CALIB_RESULT_MS) || (!result && age > CALIB_STALE_MS)) calibActive = false;
  }

  if (calibActive) {
    drawCalibration(frame, calibPhase, calibSeconds, now - calibPhaseSinceMs);
  } else if (now < sensViewUntilMs) {
    drawSensitivity(frame, sensX10);
  } else if (now < summaryUntilMs) {
    drawSummary(frame, summaryEvents, summaryDm);
  } else if (now < snoozeViewUntilMs && v.snoozed) {
    drawGlyph(frame, 5, 1, GLYPH_Z);
  } else if (v.state >= LS_DRAFT) {
    drawDraft(frame, v, now);
  } else {
    drawIdle(frame, v, now);
  }
  drawPermanentMarks(frame, v, now);

  // Press acknowledge within 200 ms; during a hold row 0 fills toward calibration.
  if (knobOk && knobWasPressed) {
    unsigned long held = now - pressStartMs;
    int lit = held >= HOLD_MS ? COLS - 1 : 1 + (int)(held * (COLS - 2) / HOLD_MS);
    for (int x = 0; x < lit; x++) setPx(frame, x, 0);
  }
  matrix.draw(frame);
}

void setup() {
  matrix.begin();
  matrix.setGrayscaleBits(3);
  matrix.clear();

  Modulino.begin(Wire1);
  probeAll();
  if (thermoOk) {
    tempC = thermo.getTemperature();
    humPct = thermo.getHumidity();
  }

  Bridge.begin();
  Bridge.provide_safe("set_settings", set_settings);
  Bridge.provide_safe("set_view", set_view);
  Bridge.provide_safe("play_sound", play_sound);
  Bridge.provide_safe("show_calibration", show_calibration);
  Bridge.provide_safe("show_summary", show_summary);

  selftestUntilMs = millis() + SELFTEST_VIEW_MS;
  SOUND(SOUND_STARTUP);
}

void loop() {
  unsigned long now = millis();

  serviceBuzzer(now);

  if (now - lastReprobeMs >= REPROBE_MS) {
    lastReprobeMs = now;
    probeAll();
  }
  if (thermoOk && now - lastThermoMs >= THERMO_READ_MS) {
    lastThermoMs = now;
    tempC = thermo.getTemperature();
    humPct = thermo.getHumidity();
  }
  if (now - lastKnobMs >= KNOB_READ_MS) {
    lastKnobMs = now;
    readKnob(now);
  }
  if (snoozeUntilMs != 0 && now >= snoozeUntilMs) {
    snoozeUntilMs = 0;
    MELODY(SOUND_SNOOZE_END);
    Bridge.notify("knob_event", 2);
    notifyNow = true;
  }
  if (now - lastFrameMs >= FRAME_MS) {
    lastFrameMs = now;
    drawFrame(now);
  }
  if (notifyNow || now - lastNotifyMs >= STATE_NOTIFY_MS) {
    notifyNow = false;
    lastNotifyMs = now;
    notifyState(now);
  }
}
