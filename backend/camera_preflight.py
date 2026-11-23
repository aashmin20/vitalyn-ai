"""
Camera permission preflight (macOS).

macOS shows the Camera permission prompt only when the request comes from a
process's *main thread*. Live sessions open the camera from a worker thread, so
if the app that launched the backend (Terminal, the Claude app, VS Code, ...) has
never been asked, every live session fails with "Cannot open camera source 0"
and no prompt ever appears.

This runs once at backend startup, on the main thread, and opens the camera
briefly. That triggers the prompt for whichever app launched the backend (click
Allow once), or confirms access is already granted. The camera is released before
the server starts accepting requests. Nothing is recorded or stored.

Turn off with VITALYN_CAMERA_PREFLIGHT=off (tests do this).
"""
import os
import sys
import time


def preflight_camera(index: int = 0, wait_s: float = 30.0) -> bool:
    if sys.platform != "darwin" or os.getenv("VITALYN_CAMERA_PREFLIGHT", "on").lower() in ("off", "0", "false"):
        return True
    try:
        import cv2
    except Exception as exc:
        print(f"Camera preflight skipped: OpenCV unavailable ({exc})")
        return False

    deadline = time.monotonic() + wait_s
    announced = False
    while True:
        cap = cv2.VideoCapture(index)
        opened = cap.isOpened()
        cap.release()
        if opened:
            print(f"VITALYN camera {index}: access OK")
            return True
        if time.monotonic() >= deadline:
            break
        if not announced:
            print("VITALYN camera: waiting for Camera permission... "
                  "if macOS shows a prompt, click Allow.")
            announced = True
        time.sleep(2)

    print(f"VITALYN camera {index}: NOT available. Open System Settings > Privacy & Security > "
          "Camera, enable the app you started the backend from, quit and reopen that app, "
          "then start the backend again. Uploaded-video analysis still works.")
    return False
