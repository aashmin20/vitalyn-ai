"""
Identify which OpenCV camera index is which physical camera.

Opens camera indices 0..3, grabs a frame from each and saves it as a JPEG so you
can see which index is the Mac webcam and which is the iPhone (Continuity Camera).
Run it from the same app you start the backend from (it needs camera permission):

    python3 scripts/list_cameras.py [output_dir]
"""
import os
import sys
import time

import cv2

out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
os.makedirs(out_dir, exist_ok=True)

for index in range(4):
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap.release()
        print(f"index {index}: not available")
        continue
    frame = None
    deadline = time.time() + 6          # cameras can take a few seconds to deliver the first frame
    while time.time() < deadline:
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
    cap.release()
    if frame is None:
        print(f"index {index}: opened but no frames")
        continue
    path = os.path.join(out_dir, f"camera_{index}.jpg")
    cv2.imwrite(path, frame)
    h, w = frame.shape[:2]
    print(f"index {index}: {w}x{h} -> {path}")
