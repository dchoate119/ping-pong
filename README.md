# 😀 ping-pong

### Description

Virtual ping pong with an Arduino UNO Q and a 3D-printed paddle. A laptop webcam tracks the paddle with a custom YOLOv8n model and reads AprilTags to pick the level and start the game. An MPU-6050 on the paddle detects swings. A ball counts as a hit when the paddle is in the target zone and a swing lands in the timing window. The record streak is published over MQTT, and the game is shown on a web page served by the UNO Q.

### System layout

- **Laptop** (`laptop/vision.py`): webcam → YOLO paddle zone + AprilTag → MQTT
- **UNO Q MCU** (`sketch/sketch.ino`): MPU-6050 over I2C → swing detection → Bridge
- **UNO Q MPU** (`python/main.py`): vision (MQTT) + swings (Bridge) → game loop → score (MQTT) + game state (WebUI)
- **Browser**: game page served by the UNO Q on port 7000

| Link | Details |
|---|---|
| MQTT (vision) | Broker `test.mosquitto.org`. Topic `dchoate119/pingpong/vision`. Payload `{t, found, cx, cy, zone, tag}`, coordinates normalized 0–1 |
| MQTT (score) | Topic `ME193/Rogers/<name>`. Payload: record streak as a float, e.g. `7.0` |
| Bridge | MCU → Python swing events |
| WebUI | `http://<board-ip>:7000`. Python pushes game state to the page |

### Game

1. Show an AprilTag to the webcam. The tag ID sets the level (ball speed), and the game starts.
2. Each ball is served toward a random zone.
3. Hit = paddle in that zone and a swing within the timing window. Each hit adds 1 to the streak.
4. A miss ends the game. If the streak beat the record, the new record is published.

### Project structure

```
app.yaml                 UNO Q app manifest
python/main.py           UNO Q: game loop, MQTT, WebUI
sketch/sketch.ino        UNO Q MCU: MPU-6050 swing detection
assets/                  Web page
laptop/vision.py         Laptop: webcam YOLO + AprilTag → MQTT
laptop/models/           Trained YOLOv8n weights
laptop/requirements.txt  Laptop Python deps
```

### Progress

- [x] MCU: read raw MPU-6050 data
- [x] MCU: swing detection, sent to Python over Bridge
- [x] Collect and label paddle images
- [x] Train YOLOv8n paddle model
- [ ] Laptop: paddle zone + AprilTag → MQTT
- [ ] UNO Q: subscribe to vision, log it
- [ ] UNO Q: game loop (serve, hit/miss, streak, levels)
- [ ] Publish record to `ME193/Rogers/<name>`
- [ ] WebUI page
- [ ] Tune thresholds, timing window, ball speeds

### Commands

```bash
# Stop the app on the board
python3 tools/deploy.py --cmd "arduino-app-cli app stop /home/arduino/ArduinoApps/ping-pong"
```
