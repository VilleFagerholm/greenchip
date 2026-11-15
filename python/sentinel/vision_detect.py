"""YOLO / Edge Impulse object detection helpers for the Room HUD preview.

Uses Arduino App Lab bricks when available. Falls back gracefully for unit tests.
"""

from __future__ import annotations

import io
import json
from typing import Any

from sentinel import config


def flatten_detections(detections: dict | None, *, max_items: int | None = None) -> list[dict]:
    """Normalize brick detections → [{label, confidence, box}, ...] for snapshot + draw."""
    out: list[dict] = []
    if not detections:
        return out
    limit = config.DETECTIONS_MAX if max_items is None else int(max_items)
    for label, items in detections.items():
        if label.startswith("__"):
            continue
        for det in items or []:
            conf = det.get("confidence", 0.0)
            try:
                conf_f = float(conf)
            except (TypeError, ValueError):
                continue
            # ObjectDetection brick reports percent strings; VideoObjectDetection uses 0–1.
            if conf_f > 1.5:
                conf_f = conf_f / 100.0
            if conf_f < config.DEFAULT_CONFIDENCE:
                continue
            box = det.get("bounding_box_xyxy") or (0, 0, 0, 0)
            out.append({
                "label": str(label),
                "confidence": round(conf_f, 3),
                "box": [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
            })
            if len(out) >= limit:
                return out
    return out


def person_count(flat: list[dict]) -> int:
    return sum(1 for d in flat if d.get("label") == config.PERSON_LABEL)


def draw_boxes_jpeg(jpeg: bytes, flat: list[dict], *, zoom: float = 1.0) -> bytes | None:
    """Decode JPEG, optional center zoom, draw boxes + window cue, re-encode. Never imwrite."""
    import cv2
    import numpy as np

    arr = np.frombuffer(jpeg, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return None
    return encode_preview_with_boxes(frame, flat, zoom=zoom)


def encode_preview_with_boxes(frame_bgr, flat: list[dict], *, zoom: float = 1.0) -> bytes | None:
    import cv2

    frame = frame_bgr
    z = max(config.PREVIEW_ZOOM_MIN, min(config.PREVIEW_ZOOM_MAX, float(zoom or 1.0)))
    fh, fw = frame.shape[:2]
    x_off = y_off = 0
    if z > 1.01:
        cw = max(1, int(fw / z))
        ch = max(1, int(fh / z))
        x_off = max(0, (fw - cw) // 2)
        y_off = max(0, (fh - ch) // 2)
        frame = frame[y_off:y_off + ch, x_off:x_off + cw]
        fh, fw = frame.shape[:2]

    w, h = config.PREVIEW_JPEG_SIZE
    sx = w / float(fw)
    sy = h / float(fh)
    small = cv2.resize(frame, (w, h))

    # Window aim rectangle (thin cyan).
    x0, y0, x1, y1 = config.WINDOW_AREA
    cv2.rectangle(
        small,
        (int(x0 * w), int(y0 * h)),
        (max(0, int(x1 * w) - 1), max(0, int(y1 * h) - 1)),
        (0, 200, 255),
        1,
    )

    for det in flat:
        box = det.get("box") or [0, 0, 0, 0]
        x1b, y1b, x2b, y2b = box
        # Boxes from the model are in full-frame coords; adjust if zoomed.
        if z > 1.01:
            x1b -= x_off
            x2b -= x_off
            y1b -= y_off
            y2b -= y_off
        p1 = (max(0, int(x1b * sx)), max(0, int(y1b * sy)))
        p2 = (min(w - 1, int(x2b * sx)), min(h - 1, int(y2b * sy)))
        color = (94, 224, 181) if det.get("label") == config.PERSON_LABEL else (224, 176, 106)
        cv2.rectangle(small, p1, p2, color, 2)
        label = f"{det.get('label', '?')} {float(det.get('confidence', 0)):.0%}"
        cv2.putText(
            small, label, (p1[0], max(14, p1[1] - 6)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA,
        )

    ok, buf = cv2.imencode(
        ".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), config.PREVIEW_JPEG_QUALITY]
    )
    return buf.tobytes() if ok else None


def try_draw_bounding_boxes_pil(jpeg: bytes, detections: dict) -> bytes | None:
    """Prefer Arduino's draw_bounding_boxes when the brick helpers are present."""
    try:
        from arduino.app_utils.image import draw_bounding_boxes
        from PIL import Image
    except Exception:
        return None
    try:
        annotated = draw_bounding_boxes(jpeg, detections)
        if annotated is None:
            return None
        if isinstance(annotated, Image.Image):
            buf = io.BytesIO()
            annotated.save(buf, format="JPEG", quality=config.PREVIEW_JPEG_QUALITY)
            return buf.getvalue()
    except Exception:
        return None
    return None


def create_video_detector(confidence: float, camera_preview: bool):
    """Return (detector, kind) or (None, None). kind is 'video' | 'still'."""
    try:
        from arduino.app_bricks.video_objectdetection import VideoObjectDetection

        class _SentinelVOD(VideoObjectDetection):
            """Fire on_detect_all even when the frame has no boxes (keeps motion/camera alive)."""

            def _process_message(self, ws, message: str) -> None:  # type: ignore[override]
                try:
                    jmsg = json.loads(message)
                except Exception:
                    return super()._process_message(ws, message)  # type: ignore[misc]

                if jmsg.get("type") != "classification":
                    return super()._process_message(ws, message)  # type: ignore[misc]

                result = jmsg.get("result", {})
                if not isinstance(result, dict):
                    return
                bounding_boxes = result.get("bounding_boxes", []) or []
                frame = self._decode_preview_frame() if self._camera_preview else None
                detections: dict[str, list[dict[str, Any]]] = {}
                for box in bounding_boxes:
                    label = box.get("label")
                    if label is None:
                        continue
                    conf = float(box.get("value", 0.0))
                    if conf < self._confidence:
                        continue
                    xyxy = (
                        box.get("x", 0),
                        box.get("y", 0),
                        box.get("x", 0) + box.get("width", 0),
                        box.get("y", 0) + box.get("height", 0),
                    )
                    details = {"confidence": conf, "bounding_box_xyxy": xyxy}
                    detections.setdefault(label, []).append(details)
                    self._execute_handler(key=label, payload=details, frame=frame)
                # Always notify all-handler (possibly empty) so camera/motion stay fresh.
                self._execute_handler(key=self.ALL_HANDLERS_KEY, payload=detections, frame=frame)

        det = _SentinelVOD(confidence=confidence, debounce_sec=0.0, camera_preview=camera_preview)
        return det, "video"
    except Exception:
        pass
    try:
        from arduino.app_bricks.object_detection import ObjectDetection
        return ObjectDetection(confidence=confidence), "still"
    except Exception:
        return None, None
