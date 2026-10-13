"""UNO Q side: forward swings to the laptop game, or a hardware tool picked by MODE."""

import json
import time

import paho.mqtt.client as mqtt
from arduino.app_utils import App, Bridge

from swings import NAMES, on_swing

MODE = "game"  # "imu_test", "swing_record", "swing_test", "vision_test" or "game"

# Must match laptop/game.py
BROKER = "test.mosquitto.org"
PORT = 1883
SWING_TOPIC = "dchoate119/pingpong/swing"

# The sketch sends swings in every mode, so always answer them
swing_handler = on_swing

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
elif MODE == "game":
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = lambda c, u, f, rc, p: print(f"MQTT connected to {BROKER}: {rc}", flush=True)
    client.connect_async(BROKER, PORT)  # retries in the background if the network isn't up yet
    client.loop_start()

    def swing_handler(direction, gy):
        on_swing(direction, gy)
        msg = {"t": time.time(), "swing": NAMES.get(direction, direction), "gy": gy}
        client.publish(SWING_TOPIC, json.dumps(msg), qos=0)
        return True

    def loop():
        time.sleep(1)  # swings are published from swing_handler
else:
    def loop():
        time.sleep(1)  # swing_test: swings print from on_swing

Bridge.provide("swing", swing_handler)

App.run(user_loop=loop)
