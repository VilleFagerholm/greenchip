#include <Arduino_Modulino.h>
#include <ArduinoGraphics.h>
#include <Arduino_LED_Matrix.h>
#include <Arduino_RouterBridge.h>

ModulinoThermo thermo;
ModulinoKnob knob;
ModulinoBuzzer buzzer;
Arduino_LED_Matrix matrix;

float lastTemp = 0;
float deadband = 1.0;
bool snooze = false;
unsigned long snoozeUntil = 0;
bool roomOccupied = false;
int diffValue = 0;

const float DRAFT_DROP = 0.25;      // more sensitive
const int DIFF_BEEP = 1500;         // lower threshold → more frequent beeps

void setOccupancy(int occupied) {
  roomOccupied = (occupied == 1);
}

void setDiff(int value) {
  diffValue = value;
  Serial.print("DIFF: ");
  Serial.println(diffValue);
}

void alertBuzzer(int freq, int durationMs) {
  if (snooze && millis() < snoozeUntil) return;
  buzzer.tone(freq, durationMs);
}

void showOnMatrix(String msg) {
  matrix.beginText(0, 0, 255, 255, 255);
  matrix.print(msg);
  matrix.endText(SCROLL_LEFT);
}

void snoozeAlert(int seconds) {
  snooze = true;
  snoozeUntil = millis() + (seconds * 1000UL);
}

void setup() {
  Serial.begin(115200);
  delay(1500);

  Bridge.begin();
  Bridge.provide("setOccupancy", setOccupancy);
  Bridge.provide("setDiff", setDiff);
  Bridge.provide("alertBuzzer", alertBuzzer);
  Bridge.provide("showOnMatrix", showOnMatrix);
  Bridge.provide("snoozeAlert", snoozeAlert);

  Modulino.begin();

  if (!thermo.begin()) { Serial.println("Thermo not found!"); while (1); }
  if (!knob.begin())   { Serial.println("Knob not found!");   while (1); }
  if (!buzzer.begin()) { Serial.println("Buzzer not found!"); while (1); }

  knob.set(0);
  matrix.begin();
  matrix.textFont(Font_4x6);
  matrix.textScrollSpeed(80);
  matrix.clear();

  Serial.println("Ready");
  buzzer.tone(1000, 70);
  delay(80);
  buzzer.tone(800, 70);
}

void loop() {
  float temp = thermo.getTemperature();
  int knobPos = knob.get();
  bool pressed = knob.isPressed();

  Serial.print("Knob: ");
  Serial.println(knobPos);

  deadband = 0.3 + (constrain(knobPos, 0, 100) / 100.0) * 1.5;

  if (pressed) {
    snoozeAlert(90);
    buzzer.tone(500, 50);
  }

  Serial.print("Temp: ");
  Serial.print(temp, 1);
  Serial.print("  Occupied: ");
  Serial.print(roomOccupied ? "YES" : "NO");
  Serial.print("  DIFF: ");
  Serial.println(diffValue);

  // Draft alert
  if (!roomOccupied && (lastTemp - temp) >= DRAFT_DROP) {
    if (!(snooze && millis() < snoozeUntil)) {
      alertBuzzer(900, 100);
      showOnMatrix("DRAFT");
    }
  }

  // More sensitive camera-change beep
  if (diffValue > DIFF_BEEP) {
    if (!(snooze && millis() < snoozeUntil)) {
      alertBuzzer(1600, 30);   // short, frequent tick
    }
  }

  lastTemp = temp;

  matrix.beginText(0, 0, 255, 255, 255);
  matrix.print(String(diffValue));
  matrix.endText(SCROLL_LEFT);

  delay(1200);   // a bit slower
}

