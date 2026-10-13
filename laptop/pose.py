"""Body pose from the webcam with MediaPipe's Pose Landmarker.

Only the upper-body points the game uses are kept: shoulders, elbows, wrists,
hips. Points are normalized 0..1 in the mirrored view shown on screen, and
"left"/"right" are the player's own left and right.

Install note: plain `pip install mediapipe` also pulls in opencv-contrib-python,
which clashes with ultralytics' opencv-python (both provide cv2). Install it as
    pip install --no-deps mediapipe absl-py flatbuffers sounddevice
"""

import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

MODEL = Path(__file__).parent / "models" / "pose_landmarker_lite.task"
MIN_VISIBILITY = 0.5  # points MediaPipe is less sure of than this are dropped

# MediaPipe landmark index -> our name
POINTS = {
    11: "left_shoulder", 12: "right_shoulder",
    13: "left_elbow", 14: "right_elbow",
    15: "left_wrist", 16: "right_wrist",
    23: "left_hip", 24: "right_hip",
}

# Lines to draw between points
SKELETON = [
    ("left_shoulder", "right_shoulder"), ("left_hip", "right_hip"),
    ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
    ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
]


class PoseTracker:
    def __init__(self, model=MODEL):
        if not Path(model).is_file():
            raise SystemExit(f"Pose model not found: {model}")
        options = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.VIDEO,  # tracks between frames, smoother
            num_poses=1,
        )
        self.landmarker = vision.PoseLandmarker.create_from_options(options)
        self.last_ms = -1

    def detect(self, frame):
        """Pose in a mirrored BGR frame, as {name: (x, y)}, or None if nobody is seen.

        MediaPipe's left/right assume an un-mirrored image, so detect on the
        un-mirrored frame and mirror x back to match what is shown.
        """
        rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
        ms = max(int(time.monotonic() * 1000), self.last_ms + 1)  # must keep increasing
        self.last_ms = ms
        result = self.landmarker.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ms)
        if not result.pose_landmarks:
            return None
        landmarks = result.pose_landmarks[0]
        return {name: (1.0 - landmarks[i].x, landmarks[i].y)
                for i, name in POINTS.items()
                if (landmarks[i].visibility or 0) >= MIN_VISIBILITY}

    def close(self):
        self.landmarker.close()
