import urllib.request
from typing import List, Dict, Any
import cv2
import numpy as np
from ultralytics import YOLO

from .config import (
    SYMBOL_WEIGHTS_PATH,
    SYMBOL_WEIGHTS_URL,
    SYMBOL_CONFIG
)


def ensure_weights_exist():
    """Downloads the fine-tuned 32-class YOLOv8 weights from GitHub if missing."""
    if not SYMBOL_WEIGHTS_PATH.exists():
        print(f"[SymbolDetector] Weights not found at {SYMBOL_WEIGHTS_PATH}. Downloading from {SYMBOL_WEIGHTS_URL}...")
        SYMBOL_WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(SYMBOL_WEIGHTS_URL, str(SYMBOL_WEIGHTS_PATH))
        print(f"[SymbolDetector] Weights downloaded successfully to {SYMBOL_WEIGHTS_PATH}.")


def non_max_suppression_boxes(boxes: np.ndarray, scores: np.ndarray, classes: np.ndarray, iou_threshold: float = 0.45):
    """Simple Non-Maximum Suppression for global coordinate aggregation across patches."""
    if len(boxes) == 0:
        return []

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]

    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]

    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h

        ovr = inter / (areas[i] + areas[order[1:]] - inter)

        # Same class check to avoid suppressing different co-located symbols
        cls_match = (classes[order[1:]] == classes[i])
        suppress = np.where((ovr > iou_threshold) & cls_match)[0]

        order = np.delete(order, np.concatenate(([0], suppress + 1)))

    return keep


class SymbolDetector:
    def __init__(
        self,
        weights_path: str = None,
        confidence_threshold: float = None,
        tile_size: int = None,
        tile_overlap: int = None
    ):
        ensure_weights_exist()
        self.weights_path = weights_path or str(SYMBOL_WEIGHTS_PATH)
        self.confidence_threshold = confidence_threshold or SYMBOL_CONFIG["confidence_threshold"]
        self.tile_size = tile_size or SYMBOL_CONFIG["tile_size"]
        self.tile_overlap = tile_overlap or SYMBOL_CONFIG["tile_overlap"]
        self.iou_threshold = SYMBOL_CONFIG["iou_threshold"]

        print(f"[SymbolDetector] Loading YOLO model from {self.weights_path}...")
        self.model = YOLO(self.weights_path)

    def detect(self, image_path: str) -> List[Dict[str, Any]]:
        """
        Runs sliding-window inference on a high-resolution P&ID image and returns
        detected symbol dictionaries with full-image coordinates.
        """
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Could not load image from {image_path}")

        img_h, img_w, _ = img.shape
        stride = self.tile_size - self.tile_overlap

        # Generate slice coordinates
        x_starts = list(range(0, max(1, img_w - self.tile_overlap), stride))
        y_starts = list(range(0, max(1, img_h - self.tile_overlap), stride))

        all_boxes = []
        all_scores = []
        all_classes = []

        print(f"[SymbolDetector] Processing image {img_w}x{img_h} across {len(x_starts) * len(y_starts)} patches...")

        for y in y_starts:
            for x in x_starts:
                x_end = min(x + self.tile_size, img_w)
                y_end = min(y + self.tile_size, img_h)

                crop = img[y:y_end, x:x_end]

                # Run inference on patch
                results = self.model(crop, conf=self.confidence_threshold, verbose=False)[0]

                if results.boxes is not None and len(results.boxes) > 0:
                    boxes = results.boxes.xyxy.cpu().numpy()
                    scores = results.boxes.conf.cpu().numpy()
                    classes = results.boxes.cls.cpu().numpy()

                    # Shift local patch coordinates to global image coordinates
                    boxes[:, [0, 2]] += x
                    boxes[:, [1, 3]] += y

                    all_boxes.extend(boxes)
                    all_scores.extend(scores)
                    all_classes.extend(classes)

        if not all_boxes:
            print("[SymbolDetector] No symbols detected.")
            return []

        all_boxes = np.array(all_boxes)
        all_scores = np.array(all_scores)
        all_classes = np.array(all_classes)

        # Global NMS pass
        keep_indices = non_max_suppression_boxes(
            all_boxes, all_scores, all_classes, iou_threshold=self.iou_threshold
        )

        detections = []
        for idx in keep_indices:
            box = all_boxes[idx]
            cls_id_num = int(all_classes[idx])
            cls_id_str = str(cls_id_num)
            confidence = float(all_scores[idx])

            det_dict = {
                "class_id": cls_id_str,
                "confidence": round(confidence, 4),
                "bbox": [
                    round(float(box[0]), 2),  # xmin
                    round(float(box[1]), 2),  # ymin
                    round(float(box[2]), 2),  # xmax
                    round(float(box[3]), 2),  # ymax
                ]
            }
            detections.append(det_dict)

        print(f"[SymbolDetector] Finished detection: {len(detections)} candidate symbol regions extracted.")
        return detections
