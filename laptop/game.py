"""Ping-pong game on the laptop: webcam paddle tracking + swings from the UNO Q.

Runs on the LAPTOP. Paddle detection reuses vision.py. Swings arrive over MQTT
from the UNO Q (python/main.py, MODE = "game"). The game is shown in the
browser at http://localhost:8000 (webview.py serves it from laptop/web/).
Serve, then hit each return in the right lane on time. A miss ends the rally.
Show a level tag (laptop/tags/levels.pdf) between rallies to change the speed.

    python laptop/game.py                  # uses the only .pt in laptop/models/
    python laptop/game.py --device gpu     # CUDA instead of the default cpu

Press Ctrl+C to quit.
"""

import argparse
import json
import queue
import random
import time
import webbrowser
from pathlib import Path

import cv2
import paho.mqtt.client as mqtt
from ultralytics import YOLO

import webview
from vision import (DEFAULT_BROKER, ZONES, best_detection, detect_tag, find_model,
                    make_tag_detector, zone_of)

# Must match python/main.py on the UNO Q
SWING_TOPIC = "dchoate119/pingpong/swing"
HEARTBEAT_TOPIC = "dchoate119/pingpong/heartbeat"  # board sends one every 2 s
RECORD_TOPIC = "ME193/Rogers/daniel"  # class scoreboard; payload is the record as a float

WEB_PORT = 8000
JPEG_QUALITY = 80

HOLD = 0.3         # seconds a paddle zone stays valid after the paddle was last seen
SERVE_TIME = 1.0   # seconds for your serve to reach the far end
HIT_TIME = 1.0     # seconds for your hit to reach the far end
SWING_LAG = 0.1    # seconds a swing takes to arrive over MQTT; see the "delay~" printout
MISS_PAUSE = 1.5   # seconds to show a miss before waiting for the next serve
BOARD_TIMEOUT = 5.0  # seconds without a heartbeat or swing before the board shows offline

# AprilTag ID -> (name, return time, hit window). Return time: seconds for the opponent's
# return to reach you. Hit window: a swing counts within +-this many seconds of arrival.
LEVELS = {
    1: ("EASY", 3.0, 0.5),
    2: ("MEDIUM", 2.0, 0.4),
    3: ("HARD", 0.75, 0.3),
}

RECORD_FILE = Path(__file__).parent / "record.json"  # best streak, kept between runs


def load_record():
    try:
        return json.loads(RECORD_FILE.read_text())["record"]
    except (OSError, ValueError, KeyError):
        return 0


def save_record(record):
    RECORD_FILE.write_text(json.dumps({"record": record}))


class Game:
    """Game state machine.

    waiting --tag--> (level changes, still waiting)
    waiting --swing--> serve --> incoming --swing in time, right lane--> outgoing --> incoming ...
                                    |
                                    +--wrong lane, or no swing in time--> miss --> waiting

    streak counts hits since the serve; record is the best streak ever.
    """

    def __init__(self, on_record=None):
        self.on_record = on_record  # called with the new record when it's beaten
        self.phase = "waiting"
        self.phase_t0 = 0.0
        # Ball in flight: {"id", "kind", "dir", "from", "to", "duration"}. dir is "out"
        # (your end -> far end) or "in"; from/to are lanes 0..ZONES-1 at each end.
        self.ball = None
        self.ball_t0 = 0.0
        self.ball_id = 0
        self.result = None  # last {"id", "text"}; the page pops it up when id changes
        self.streak = 0
        self.record = load_record()
        self.level = 1  # key into LEVELS; a tag changes it while waiting

    def launch(self, kind, direction, lane_from, lane_to, duration, now):
        self.ball_id += 1
        self.ball = {"id": self.ball_id, "kind": kind, "dir": direction,
                     "from": lane_from, "to": lane_to, "duration": duration}
        self.ball_t0 = now

    def arrive_time(self):
        return self.ball_t0 + self.ball["duration"]

    def on_swing(self, zone, now):
        t = now - SWING_LAG  # when the swing actually happened
        if self.phase == "waiting":
            lane = zone if zone is not None else ZONES // 2  # serve from the middle if unseen
            self.streak = 0
            self.launch("serve", "out", lane, random.randrange(ZONES), SERVE_TIME, now)
            self.set_phase("serve", now)
        elif self.phase == "incoming":
            dt = t - self.arrive_time()
            target = self.ball["to"]
            print(f"    swing {dt:+.2f} s from arrival, paddle zone {zone}, target {target}")
            if dt < -self.hit_window():
                return  # too early: ignore it, there is still time to swing again
            if zone == target:
                self.streak += 1
                self.show("HIT!")
                self.launch("hit", "out", target, random.randrange(ZONES), HIT_TIME, now)
                self.set_phase("outgoing", now)
            else:
                self.miss(now)

    def update(self, now):
        if self.phase in ("serve", "outgoing") and now >= self.arrive_time():
            # The opponent returns from where the ball landed to a random lane on your side
            self.launch("return", "in", self.ball["to"], random.randrange(ZONES),
                        LEVELS[self.level][1], now)
            self.set_phase("incoming", now)
        elif self.phase == "incoming" and now > self.arrive_time() + self.hit_window():
            self.miss(now)
        elif self.phase == "miss" and now - self.phase_t0 >= MISS_PAUSE:
            self.set_phase("waiting", now)

    def hit_window(self):
        return LEVELS[self.level][2]

    def on_tag(self, tag):
        """A tag in view picks the level, but only between rallies."""
        if self.phase == "waiting" and tag in LEVELS and tag != self.level:
            self.level = tag
            print(f"    level {LEVELS[tag][0]}")
            self.show(LEVELS[tag][0])

    def miss(self, now):
        if self.streak > self.record:
            self.record = self.streak
            save_record(self.record)
            if self.on_record:
                self.on_record(self.record)
            print(f"    new record: {self.record}")
            self.show("NEW RECORD!")
        else:
            self.show("MISS")
        self.ball = None
        self.set_phase("miss", now)

    def show(self, text):
        self.result = {"id": (self.result["id"] + 1) if self.result else 1, "text": text}

    def set_phase(self, phase, now):
        print(f"--> {phase}")
        self.phase, self.phase_t0 = phase, now

    def state(self, now):
        """For the page. ball["t"] is seconds since launch, so the page can sync its animation."""
        ball = dict(self.ball, t=round(now - self.ball_t0, 3)) if self.ball else None
        return {"phase": self.phase, "ball": ball, "result": self.result,
                "streak": self.streak, "record": self.record,
                "level": LEVELS[self.level][0]}


def connect_board(host, port):
    """Subscribe to the UNO Q. Returns (client, queue of swing dicts, board).

    board["seen"] is the time.monotonic() of the last heartbeat or swing.
    """
    swings = queue.SimpleQueue()
    board = {"seen": float("-inf")}

    def on_connect(client, userdata, flags, reason_code, properties):
        print(f"MQTT connected to {host}: {reason_code}, subscribing to the board")
        # (re)subscribe on every reconnect
        client.subscribe([(SWING_TOPIC, 0), (HEARTBEAT_TOPIC, 0)])

    def on_message(client, userdata, msg):
        board["seen"] = time.monotonic()
        if msg.topic == HEARTBEAT_TOPIC:
            return
        try:
            data = json.loads(msg.payload)
        except ValueError:
            print(f"Bad payload: {msg.payload[:80]!r}")
            return
        data["rx"] = time.time()  # MQTT thread -> main loop through the queue
        swings.put(data)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pingpong-game")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port)
    client.loop_start()
    return client, swings, board


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", help="path to .pt (default: only .pt in laptop/models/)")
    ap.add_argument("--camera", type=int, default=0, help="webcam index")
    ap.add_argument("--imgsz", type=int, default=640, help="inference size; try 320 if slow")
    ap.add_argument("--conf", type=float, default=0.3, help="minimum confidence")
    ap.add_argument("--device", choices=["cpu", "gpu"], default="cpu",
                    help="run inference on cpu (default) or the first CUDA gpu")
    ap.add_argument("--broker", default=DEFAULT_BROKER, help="MQTT broker host")
    ap.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    args = ap.parse_args()
    device = "0" if args.device == "gpu" else "cpu"  # ultralytics device names

    client, swings, board = connect_board(args.broker, args.port)

    model_path = find_model(args.model)
    model = YOLO(str(model_path))
    print(f"Model: {model_path}  device: {args.device}")

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit(f"Could not open camera {args.camera}")

    hub = webview.start(WEB_PORT)
    url = f"http://localhost:{WEB_PORT}"
    print(f"Game page: {url}")
    webbrowser.open(url)

    fps = 0.0
    last = time.perf_counter()
    swing = None  # last swing as {"id", "name"}; the page flashes when id changes
    def publish_record(record):
        client.publish(RECORD_TOPIC, str(float(record)), qos=1)
        print(f"    published {float(record)} to '{RECORD_TOPIC}'")

    game = Game(on_record=publish_record)
    tag_detector = make_tag_detector()
    held_zone, held_t = None, 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera read failed")
                break
            frame = cv2.flip(frame, 1)  # mirror so moving right moves right on screen
            h, w = frame.shape[:2]

            result = model.predict(frame, imgsz=args.imgsz, conf=args.conf,
                                   device=device, verbose=False)[0]
            det = best_detection(result, w, h)
            tag, tag_corners = detect_tag(tag_detector, frame)
            now = time.perf_counter()
            if det:
                held_zone, held_t = zone_of(det["cx"]), now
            # A few missed frames keep the last zone, so a dropout mid-swing isn't a miss
            zone = held_zone if now - held_t < HOLD else None

            while not swings.empty():
                s = swings.get()
                swing = {"id": (swing["id"] + 1) if swing else 1, "name": s["swing"]}
                # Board and laptop clocks may differ, so treat the delay as a rough guide
                print(f"SWING {s['swing']:8}  gy {s['gy']:5.0f}  zone={zone}  "
                      f"delay~{s['rx'] - s['t']:+.2f} s")
                game.on_swing(zone, now)
            if tag is not None:
                game.on_tag(tag)
            game.update(now)

            inst_fps = 1.0 / max(now - last, 1e-6)
            fps = 0.9 * fps + 0.1 * inst_fps if fps else inst_fps  # smoothed
            last = now

            # Box is normalized 0..1 so the page can scale it to any size
            tag_view = {"id": tag, "corners": [[round(float(x) / w, 4), round(float(y) / h, 4)]
                                               for x, y in tag_corners]} if tag is not None else None
            box = [round(v, 4) for v in (det["xyxy"][0] / w, det["xyxy"][1] / h,
                                         det["xyxy"][2] / w, det["xyxy"][3] / h)] if det else None
            state = {"zones": ZONES, "zone": zone, "box": box, "swing": swing, "fps": round(fps, 1),
                     "tag": tag_view, "board": time.monotonic() - board["seen"] < BOARD_TIMEOUT,
                     **game.state(now)}
            ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            hub.publish(jpeg.tobytes(), state)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()
        cap.release()


if __name__ == "__main__":
    main()
