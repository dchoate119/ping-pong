"""Vision from laptop/vision.py over MQTT. The game reads paddle_zone() and current_tag()."""

import json
import threading
import time

import paho.mqtt.client as mqtt

# Must match laptop/vision.py
BROKER = "test.mosquitto.org"
PORT = 1883
TOPIC = "dchoate119/pingpong/vision"

HOLD = 0.3  # seconds a paddle or tag stays valid after it was last seen

zone = None      # last zone the paddle was seen in
zone_seen = 0.0  # time.monotonic() when it was seen
tag = None       # last tag seen
tag_seen = 0.0
msgs = 0         # messages since the last stats() call
found = 0        # ... of which saw the paddle
lock = threading.Lock()


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print(f"MQTT connect failed: {reason_code}", flush=True)
        return
    print(f"MQTT connected to {BROKER}, subscribing to {TOPIC}", flush=True)
    client.subscribe(TOPIC, qos=0)  # (re)subscribe on every reconnect


def on_message(client, userdata, msg):
    global zone, zone_seen, tag, tag_seen, msgs, found
    try:
        data = json.loads(msg.payload)
    except ValueError:
        print(f"Bad payload: {msg.payload[:80]!r}", flush=True)
        return
    now = time.monotonic()
    with lock:
        msgs += 1
        if data.get("found"):  # a missed frame keeps the old zone
            found += 1
            zone, zone_seen = data["zone"], now
        if data.get("tag") is not None:
            tag, tag_seen = data["tag"], now


def paddle_zone():
    """Zone 0-2 if the paddle was seen within HOLD seconds, else None."""
    with lock:
        return zone if time.monotonic() - zone_seen < HOLD else None


def current_tag():
    """Tag ID if one was seen within HOLD seconds, else None."""
    with lock:
        return tag if time.monotonic() - tag_seen < HOLD else None


def stats():
    """(messages, paddle found) since the last call."""
    global msgs, found
    with lock:
        counts = (msgs, found)
        msgs = found = 0
    return counts


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect_async(BROKER, PORT)  # retries in the background if the network isn't up yet
client.loop_start()
