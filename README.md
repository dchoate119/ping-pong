# 😀 ping-pong

### Description

Virtual ping pong with an Arduino UNO Q and a 3D-printed paddle. A laptop webcam tracks the paddle with a custom YOLOv8n model and reads AprilTags to pick the level. MediaPipe tracks the player's body: the skeleton is drawn on the game page, and the paddle-hand wrist takes over the lane when YOLO loses the paddle. An MPU-6050 on the paddle detects swings on the UNO Q, which sends them to the laptop over MQTT. The laptop runs the game and shows it in the browser: the camera feed next to a bird's-eye table with the ball. A ball counts as a hit when the paddle is in the target lane and a swing lands in the timing window. The record streak is published over MQTT.

### System layout

- **UNO Q MCU** (`sketch/sketch.ino`): MPU-6050 over I2C → swing detection → Bridge
- **UNO Q MPU** (`python/main.py`): swings (Bridge) → MQTT
- **Laptop** (`laptop/game.py`): webcam → YOLO paddle lane (MediaPipe wrist as backup) + AprilTag level + pose skeleton, swings (MQTT) → game loop → record (MQTT) + game page
- **Browser**: game page served by the laptop at `http://localhost:8000`

| Link | Details |
|---|---|
| MQTT (swings) | Broker `test.mosquitto.org`. Topic `dchoate119/pingpong/swing`. Payload `{t, swing, gy}`, swing is `forehand` or `backhand` |
| MQTT (heartbeat) | Topic `dchoate119/pingpong/heartbeat`. Payload `{t}` every 2 s, so the game page can show whether the board is up |
| MQTT (score) | Topic `ME193/Rogers/daniel`. Payload: record streak as a float, e.g. `7.0`. Sent only when the record is beaten |
| Bridge | MCU → Python swing events |
| Game page | `laptop/webview.py` serves `laptop/web/`, the camera as MJPEG on `/video`, and game state as Server-Sent Events on `/events`. The page sends the paddle hand to `POST /hand` |

### Game

1. While "SWING TO SERVE" shows, hold up a level tag (`laptop/tags/levels.pdf`) to pick the level, and click LEFT or RIGHT for your paddle hand. The page remembers the hand.
2. Swing to serve. The ball goes to the far end.
3. The opponent returns it to a random lane on your side. The lane pulses and a dotted line shows the path.
4. Hit = paddle in that lane and a swing within the timing window around arrival. Each hit adds 1 to the streak and the rally continues. If YOLO loses the paddle for more than 0.3 s, the paddle-hand wrist gives the lane; the footer shows `lane: paddle`, `lane: wrist` or `lane: none`.
5. A wrong lane or no swing in time is a miss and ends the rally. If the streak beat the record, the new record is saved and published.

| Tag | Level | Return time | Timing window | Lane lines | Aiming hints |
|---|---|---|---|---|---|
| ID 1 | EASY | 3.0 s | ±0.5 s | yes | yes |
| ID 2 | MEDIUM | 2.0 s | ±0.4 s | no | yes |
| ID 3 | HARD | 1.5 s | ±0.3 s | no | no |

Aiming hints are the green glow on your paddle's lane, the orange glow on the incoming ball's lane, and the ball's dotted path. Levels and timing are set at the top of `laptop/game.py`. Tags are AprilTag 36h11.

### Project structure

```
app.yaml                 UNO Q app manifest
python/main.py           UNO Q: swings → MQTT; MODE picks game or a test tool
python/swings.py         UNO Q: swing handler for the sketch
python/imu_test.py       UNO Q test tool: MPU-6050 hardware check
python/swing_record.py   UNO Q test tool: one line per motion, for picking swing thresholds
python/vision.py         UNO Q test tool: receive laptop/vision.py over MQTT
sketch/sketch.ino        UNO Q MCU: MPU-6050 swing detection
laptop/game.py           Laptop: camera, YOLO, tags, pose, game loop, MQTT
laptop/pose.py           Laptop: MediaPipe pose (shoulders, elbows, wrists, hips)
laptop/webview.py        Laptop: web server for the game page
laptop/web/              Game page (HTML, JS, CSS)
laptop/vision.py         Laptop: detection helpers, and a standalone camera test
laptop/tags/levels.pdf   Printable level tags
laptop/models/           Trained YOLOv8n weights
laptop/training.ipynb    Paddle model training
laptop/requirements.txt  Laptop Python deps
```

### Progress

- [x] MCU: read raw MPU-6050 data
- [x] MCU: swing detection, sent to Python over Bridge
- [x] Collect and label paddle images
- [x] Train YOLOv8n paddle model
- [x] Laptop: paddle lane + AprilTag detection
- [x] UNO Q: send swings to the laptop over MQTT
- [x] Laptop: game loop (serve, return, hit/miss, streak, record)
- [x] Game page: camera feed + bird's-eye table
- [x] AprilTag levels
- [x] Publish record to `ME193/Rogers/daniel`
- [x] Ball overlaid on the camera view
- [x] Pose skeleton on the game page, LEFT/RIGHT paddle hand
- [x] Paddle-hand wrist as a backup lane



### Commands

```bash
# Laptop setup. Install MediaPipe with --no-deps: its opencv-contrib-python
# clashes with the opencv-python that ultralytics uses.
pip install -r laptop/requirements.txt
pip install mediapipe --no-deps

# Deploy the UNO Q side (from unoq-workspace)
python3 tools/deploy.py ping-pong

# Run the game on the laptop (from ping-pong), then open http://localhost:8000
python3 laptop/game.py --device gpu

# Camera test without the game: preview window with lanes and tags
python3 laptop/vision.py --device gpu --no-mqtt

# Stop the app on the board
python3 tools/deploy.py --cmd "arduino-app-cli app stop /home/arduino/ArduinoApps/ping-pong"
```

The record is kept in `laptop/record.json` (not committed). Delete it to reset.
