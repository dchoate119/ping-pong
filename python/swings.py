"""Swing events from the sketch. The game reads last_swing."""

import time

NAMES = {-1: "forehand", 1: "backhand"}

last_swing = None  # (time.monotonic(), direction, gy)


def on_swing(direction, gy):
    global last_swing
    last_swing = (time.monotonic(), direction, gy)
    print(f"SWING {NAMES.get(direction, direction):8}  gy {gy:5.0f}", flush=True)
    return True
