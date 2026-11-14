import time
import cv2
from arduino.app_utils import App, Bridge

def open_camera():
    for dev in ["/dev/video0", "/dev/video1", "/dev/video2", "/dev/video3"]:
        cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"Camera opened on {dev}")
                return cap, frame
        cap.release()
    return None, None

cap, prev_frame = open_camera()
prev_gray = None

if cap is None:
    print("ERROR: No camera found")
else:
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    prev_gray = cv2.GaussianBlur(prev_gray, (21, 21), 0)
    print("Frame differencing ready")

def classify_occupancy(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return gray.std() > 20

last_occupancy = None
last_send = 0

def loop():
    global prev_gray, last_occupancy, last_send

    if cap is None:
        time.sleep(1)
        return

    ret, frame = cap.read()
    if not ret or frame is None:
        time.sleep(0.1)
        return

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)

    diff = cv2.absdiff(prev_gray, gray)
    _, thresh = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)  # slightly more sensitive
    diff_value = cv2.countNonZero(thresh)

    Bridge.call("setDiff", int(diff_value))
    prev_gray = gray

    occupied = classify_occupancy(frame)
    now = time.time()
    if occupied != last_occupancy or (now - last_send) > 4:
        Bridge.call("setOccupancy", 1 if occupied else 0)
        last_occupancy = occupied
        last_send = now

    print("DIFF:", diff_value)
    time.sleep(0.25)   # a bit slower

App.run(user_loop=loop)


