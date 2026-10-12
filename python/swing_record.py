"""Swing recorder: one summary line per motion, for picking swing thresholds.

A motion starts when gyro magnitude rises above TRIGGER and ends once it has
stayed below for QUIET_S. Do forehands, backhands and non-swings, then compare.
"""

import math
import time

from imu_test import read

TRIGGER = 100.0   # deg/s, gyro magnitude that starts a motion
QUIET_S = 0.15    # s below TRIGGER that ends it
AXES = ("gx", "gy", "gz")

count = 0
started = False


def gyro_mag(s):
    return math.hypot(*s[3:])


def record(first):
    samples = [first]
    t0 = last_active = time.monotonic()
    while time.monotonic() - last_active < QUIET_S:
        s = read()
        samples.append(s)
        if gyro_mag(s) > TRIGGER:
            last_active = time.monotonic()
    return samples, (last_active - t0) * 1000


def summarize(samples, duration_ms):
    global count
    count += 1
    gyro = max(gyro_mag(s) for s in samples)
    accel = max(math.hypot(*s[:3]) for s in samples)
    # Axis with the biggest single reading, with its sign
    i = max(range(3), key=lambda a: max(abs(s[3 + a]) for s in samples))
    peak = max((s[3 + i] for s in samples), key=abs)
    print(f"#{count:<3} peak gyro {gyro:5.0f} deg/s  peak accel {accel:4.1f} g  "
          f"duration {duration_ms:4.0f} ms  main axis {'+' if peak > 0 else '-'}{AXES[i]}",
          flush=True)


def start():
    n = 100
    t0 = time.monotonic()
    for _ in range(n):
        read()
    rate = n / (time.monotonic() - t0)
    print(f"Swing recorder: {rate:.0f} samples/s. Trigger {TRIGGER:.0f} deg/s. Go.", flush=True)


def loop():
    global started
    if not started:
        try:
            start()
            started = True
        except Exception as e:  # sketch may not be ready yet
            print(f"waiting for sketch: {e}", flush=True)
            time.sleep(1)
        return
    s = read()
    if gyro_mag(s) > TRIGGER:
        summarize(*record(s))
