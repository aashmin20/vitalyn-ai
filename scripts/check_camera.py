"""
One-time camera permission check for VITALYN live detection.

macOS only lets a *main thread* trigger the Camera permission prompt, and the
permission belongs to the app that launches the process (Terminal, iTerm, the
Claude app, ...). Run this from the SAME app you will start the backend from:

    python3 scripts/check_camera.py [camera_index]

If macOS shows a permission prompt, click Allow. The script waits up to 60 s for
your answer, then reports whether the camera delivers frames. Afterwards restart
the backend from that same app.
"""
import sys
import time

import cv2

index = int(sys.argv[1]) if len(sys.argv) > 1 else 0
WAIT_S = 60

cap = None
deadline = time.time() + WAIT_S
announced = False
while time.time() < deadline:
    cap = cv2.VideoCapture(index)
    if cap.isOpened():
        break
    cap.release()
    cap = None
    if not announced:
        print("Waiting for camera access... if macOS shows a prompt, click Allow.")
        announced = True
    time.sleep(2)

if cap is None:
    print(f"FAILED: could not open camera {index} within {WAIT_S} s.")
    print("1. Open System Settings > Privacy & Security > Camera.")
    print("2. Enable the app you ran this from (Terminal, iTerm, Claude, ...).")
    print("   If it is missing from the list, run `tccutil reset Camera` and try again.")
    print("3. Quit and reopen that app, then run this script again.")
    sys.exit(1)

t0, frames, shape = time.time(), 0, None
while time.time() - t0 < 3:
    ok, frame = cap.read()
    if ok:
        frames += 1
        shape = frame.shape
cap.release()
if frames == 0:
    print(f"FAILED: camera {index} opened but delivered no frames (is another app using it?).")
    sys.exit(1)
print(f"OK: camera {index} delivered {frames} frames in 3 s "
      f"({frames / 3:.1f} fps, {shape[1]}x{shape[0]}).")
