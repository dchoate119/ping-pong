"""UNO Q side: ping-pong game, or a hardware tool picked by MODE."""

import time

from arduino.app_utils import App, Bridge

from swings import on_swing

MODE = "vision_test"  # "imu_test", "swing_record", "swing_test", "vision_test" or "game"

# The sketch sends swings in every mode, so always answer them
Bridge.provide("swing", on_swing)

if MODE == "imu_test":
    from imu_test import loop
elif MODE == "swing_record":
    from swing_record import loop
elif MODE == "vision_test":
    import vision

    def loop():
        time.sleep(1)
        msgs, found = vision.stats()
        print(f"zone={vision.paddle_zone()}  tag={vision.current_tag()}  "
              f"heard {msgs} msgs, {found} saw the paddle", flush=True)
else:
    def loop():
        time.sleep(1)  # swing_test: swings print from on_swing. Game goes here.


App.run(user_loop=loop)
