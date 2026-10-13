"""Track the paddle and AprilTags on the laptop webcam and publish them over MQTT.

Runs on the LAPTOP, not the UNO Q. Each frame: YOLO finds the paddle, its
center picks one of 3 vertical zones (0 = left, 1 = center, 2 = right),
and OpenCV looks for an AprilTag (36h11). Every frame is published as JSON
over MQTT (--no-mqtt to skip). The laptop keeps no game state; the UNO Q decides what
the tag and zone mean.

    python laptop/vision.py                    # uses the only .pt in laptop/models/
    python laptop/vision.py --device gpu       # CUDA instead of the default cpu
    python laptop/vision.py --no-mqtt          # preview only, no network
    python laptop/vision.py --broker localhost # once a local broker runs

Press q (or Esc) in the preview window to quit.
"""

import argparse
import json
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

MODELS_DIR = Path(__file__).parent / "models"
DEFAULT_BROKER = "test.mosquitto.org"
TOPIC = "dchoate119/pingpong/vision"
ZONES = 3  # equal-width vertical strips, numbered left to right


def find_model(path):
    if path:
        return Path(path)
    candidates = sorted(MODELS_DIR.glob("*.pt"))
    if len(candidates) != 1:
        raise SystemExit(
            f"Expected exactly one .pt in {MODELS_DIR}, found {len(candidates)}. "
            "Pass --model explicitly."
        )
    return candidates[0]


def best_detection(result, frame_w, frame_h):
    """Return the highest-confidence box as a normalized dict, or None."""
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return None
    i = int(boxes.conf.argmax())
    x1, y1, x2, y2 = boxes.xyxy[i].tolist()
    return {
        "cx": (x1 + x2) / 2 / frame_w,
        "cy": (y1 + y2) / 2 / frame_h,
        "conf": float(boxes.conf[i]),
        "xyxy": (int(x1), int(y1), int(x2), int(y2)),
    }


def zone_of(cx):
    """Zone for a normalized x: 0..ZONES-1, left to right."""
    return min(int(cx * ZONES), ZONES - 1)


def make_tag_detector():
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    return cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())


def detect_tag(detector, frame):
    """Return (id, corners) of the first tag found, or (None, None).

    frame is the mirrored view shown on screen. A mirrored tag decodes wrong, so
    detect on the un-mirrored image and mirror the corners back to match frame.
    """
    gray = cv2.flip(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 1)
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None or len(ids) == 0:
        return None, None
    c = corners[0].reshape(-1, 2).copy()  # shapes differ across OpenCV versions
    c[:, 0] = frame.shape[1] - 1 - c[:, 0]
    return int(ids.flatten()[0]), c


def connect_mqtt(host, port):
    import paho.mqtt.client as mqtt  # not needed with --no-mqtt

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pingpong-laptop")
    client.connect(host, port)
    client.loop_start()
    print(f"MQTT: publishing to {host}:{port} topic '{TOPIC}'")
    return client


def to_message(det, zone, tag):
    """JSON payload for the UNO Q. Coordinates are normalized 0..1."""
    msg = {"t": time.time(), "found": det is not None, "cx": None, "cy": None,
           "zone": zone, "tag": tag}
    if det:
        msg["cx"] = round(det["cx"], 4)
        msg["cy"] = round(det["cy"], 4)
    return json.dumps(msg)


def draw(frame, det, zone, tag, tag_corners, fps, yolo_ms, tag_ms):
    h, w = frame.shape[:2]
    if zone is not None:
        overlay = frame.copy()
        cv2.rectangle(overlay, (zone * w // ZONES, 0),
                      ((zone + 1) * w // ZONES, h), (0, 255, 0), -1)
        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
    for k in range(1, ZONES):
        cv2.line(frame, (k * w // ZONES, 0), (k * w // ZONES, h), (255, 255, 0), 1)
    if det:
        x1, y1, x2, y2 = det["xyxy"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, f"paddle {det['conf']:.2f}  zone {zone}", (x1, max(y1 - 8, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    if tag is not None:
        cv2.polylines(frame, [tag_corners.astype(int)], True, (255, 0, 255), 2)
        cv2.putText(frame, f"tag {tag}", (10, 75),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
    cv2.putText(frame, f"{fps:.1f} fps  yolo {yolo_ms:.1f} ms  tag {tag_ms:.1f} ms", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", help="path to .pt (default: only .pt in laptop/models/)")
    ap.add_argument("--camera", type=int, default=0, help="webcam index")
    ap.add_argument("--imgsz", type=int, default=640, help="inference size; try 320 if slow")
    ap.add_argument("--conf", type=float, default=0.3, help="minimum confidence")
    ap.add_argument("--device", choices=["cpu", "gpu"], default="cpu",
                    help="run inference on cpu (default) or the first CUDA gpu")
    ap.add_argument("--mqtt", action=argparse.BooleanOptionalAction, default=True,
                    help="publish each frame over MQTT (default on; --no-mqtt to test offline)")
    ap.add_argument("--broker", default=DEFAULT_BROKER, help="MQTT broker host")
    ap.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    args = ap.parse_args()
    device = "0" if args.device == "gpu" else "cpu"  # ultralytics device names

    mqtt_client = connect_mqtt(args.broker, args.port) if args.mqtt else None

    model_path = find_model(args.model)
    model = YOLO(str(model_path))
    print(f"Model: {model_path}  classes: {model.names}  device: {args.device}")
    tag_detector = make_tag_detector()

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit(f"Could not open camera {args.camera}")

    fps = 0.0
    yolo_ms = tag_ms = 0.0
    last = time.perf_counter()
    last_print = 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera read failed")
                break
            frame = cv2.flip(frame, 1)  # mirror so moving right moves right on screen
            h, w = frame.shape[:2]

            t0 = time.perf_counter()
            result = model.predict(frame, imgsz=args.imgsz, conf=args.conf,
                                   device=device, verbose=False)[0]
            t1 = time.perf_counter()
            tag, tag_corners = detect_tag(tag_detector, frame)
            t2 = time.perf_counter()

            det = best_detection(result, w, h)
            zone = zone_of(det["cx"]) if det else None
            if mqtt_client:
                mqtt_client.publish(TOPIC, to_message(det, zone, tag), qos=0)

            now = time.perf_counter()
            inst_fps = 1.0 / max(now - last, 1e-6)
            fps = 0.9 * fps + 0.1 * inst_fps if fps else inst_fps  # smoothed
            yolo_ms = 0.9 * yolo_ms + 0.1 * (t1 - t0) * 1000 if yolo_ms else (t1 - t0) * 1000
            tag_ms = 0.9 * tag_ms + 0.1 * (t2 - t1) * 1000 if tag_ms else (t2 - t1) * 1000
            last = now

            if now - last_print > 0.5:
                last_print = now
                where = f"zone={zone}  cx={det['cx']:.3f}  cy={det['cy']:.3f}" if det else "no paddle"
                print(f"{fps:5.1f} fps  yolo {yolo_ms:5.1f} ms  tag {tag_ms:4.1f} ms  "
                      f"{where}  tag={tag}")

            draw(frame, det, zone, tag, tag_corners, fps, yolo_ms, tag_ms)
            cv2.imshow("ping-pong vision", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    finally:
        if mqtt_client:
            mqtt_client.publish(TOPIC, to_message(None, None, None), qos=0)
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
