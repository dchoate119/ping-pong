"""MPU-6050 hardware check. Keep the paddle still at startup.

Checks the sensor is found, reads ~1 g at rest with near-zero gyro, and that
data is changing. Then streams live readings so you can watch the axes.
"""

import math
import statistics
import time

from arduino.app_utils import Bridge

REST_SAMPLES = 100
ACCEL_TOL = 0.1   # g, allowed error from 1 g at rest
GYRO_MAX = 5.0    # deg/s, max mean |gyro| at rest

tested = False


def read():
    return [float(x) for x in Bridge.call("imu_read").split(",")]


def check(name, ok, detail):
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)
    return ok


def run():
    print("MPU-6050 test: keep the paddle still", flush=True)
    info = Bridge.call("imu_check")
    if not check("sensor found", info.startswith("found"), info):
        return
    samples = [read() for _ in range(REST_SAMPLES)]
    acc = statistics.mean(math.hypot(*s[:3]) for s in samples)
    gyro = statistics.mean(max(abs(g) for g in s[3:]) for s in samples)
    check("accel at rest ~1 g", abs(acc - 1) < ACCEL_TOL, f"{acc:.3f} g")
    check("gyro at rest ~0", gyro < GYRO_MAX, f"{gyro:.2f} deg/s")
    check("data changing", len({tuple(s) for s in samples}) > 1, f"{REST_SAMPLES} samples")
    print("Live: ax ay az (g) | gx gy gz (deg/s). Move the paddle.", flush=True)


def loop():
    global tested
    if not tested:
        try:
            run()
            tested = True
        except Exception as e:  # sketch may not be ready yet
            print(f"waiting for sketch: {e}", flush=True)
            time.sleep(1)
        return
    ax, ay, az, gx, gy, gz = read()
    print(f"{ax:6.2f} {ay:6.2f} {az:6.2f} | {gx:7.1f} {gy:7.1f} {gz:7.1f}", flush=True)
    time.sleep(0.5)
