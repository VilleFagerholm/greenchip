# Greenchip – Zero-Cloud Open-Window & Draft Energy Sentinel

Local energy sentinel for homes, schools, and offices.  
Detects when heat is escaping through an open window in an empty room and gives an immediate local alert. No cloud, no surveillance.

## Hardware
- Arduino UNO Q
- Modulino Thermo
- Modulino Knob
- Modulino Buzzer
- Arduino USB Camera
- Built-in 8×13 LED Matrix

## How it works
- **Camera** – frame differencing produces a tangible `DIFF` index (pixel change between frames) and a simple occupancy proxy.
- **Thermo** – detects sudden cold-air drafts.
- **Knob** – sets the comfort/eco deadband; click to snooze alerts.
- **LED Matrix + Buzzer** – local visual and audible reminders.

## Files
- `sketch.ino` – MCU side (sensors, buzzer, matrix, Bridge)
- `main.py` – Linux side (camera, frame differencing, occupancy)

## Run
Open the App in Arduino App Lab and press Run.  
Serial Monitor shows temperature, knob position, occupancy, and the continuous `DIFF` value.
