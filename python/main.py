"""UNO Q side: ping-pong game. With IMU_TEST on, runs the MPU-6050 check instead."""

import time

from arduino.app_utils import App

IMU_TEST = True

if IMU_TEST:
    from imu_test import loop
else:
    def loop():
        time.sleep(1)  # game goes here


App.run(user_loop=loop)
