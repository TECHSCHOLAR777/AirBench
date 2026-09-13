from typing import List, Dict, Any
import cv2
import numpy as np

from .config import OCR_CONFIG


class TextOCR:
    def __init__(self, lang: str = None, use_angle_cls: bool = None):
        self.lang = lang or OCR_CONFIG["lang"]
        self.use_angle_cls = use_angle_cls if use_angle_cls is not None else OCR_CONFIG["use_angle_cls"]
        self.min_confidence = OCR_CONFIG["min_confidence"]
        self.ocr_engine = None
        self._init_ocr()

    def _init_ocr(self):
        """Initializes EasyOCR directly."""
        try:
            import easyocr
            print("[TextOCR] Initializing EasyOCR...")
            self.ocr_engine = easyocr.Reader([self.lang], gpu=False)
            self.engine_type = "easyocr"
            print("[TextOCR] EasyOCR initialized successfully.")
        except (ImportError, Exception) as e:
            print(f"[TextOCR] EasyOCR not available ({e}). OCR module running in mock/pass-through mode.")
            self.ocr_engine = None
            self.engine_type = "none"

    def detect_text(self, image_input) -> List[Dict[str, Any]]:
        """
        Runs text detection and recognition on the image using EasyOCR.
        Returns a list of dicts: {"text": str, "confidence": float, "bbox": [xmin, ymin, xmax, ymax]}
        """
        if isinstance(image_input, str):
            img = cv2.imread(image_input)
        else:
            img = image_input

        if img is None:
            return []

        results = []

        if self.engine_type == "easyocr":
            try:
                easy_out = self.ocr_engine.readtext(img)
                for bbox, text, conf in easy_out:
                    if conf >= self.min_confidence:
                        poly = np.array(bbox, dtype=np.float32)
                        xmin = float(np.min(poly[:, 0]))
                        ymin = float(np.min(poly[:, 1]))
                        xmax = float(np.max(poly[:, 0]))
                        ymax = float(np.max(poly[:, 1]))
                        results.append({
                            "text": text.strip(),
                            "confidence": float(conf),
                            "bbox": [round(xmin, 2), round(ymin, 2), round(xmax, 2), round(ymax, 2)]
                        })
            except Exception as e:
                print(f"[TextOCR] Error during EasyOCR execution: {e}")

        print(f"[TextOCR] Extracted {len(results)} text entities.")
        return results

    def mask_text(self, img: np.ndarray, text_boxes: List[Dict[str, Any]], padding: int = 4) -> np.ndarray:
        """
        Paints white over all detected text bounding boxes so character strokes
        are not erroneously detected as pipe lines.
        """
        masked = img.copy()
        h, w = masked.shape[:2]

        for item in text_boxes:
            xmin, ymin, xmax, ymax = item["bbox"]
            x1 = max(0, int(xmin) - padding)
            y1 = max(0, int(ymin) - padding)
            x2 = min(w, int(xmax) + padding)
            y2 = min(h, int(ymax) + padding)

            cv2.rectangle(masked, (x1, y1), (x2, y2), (255, 255, 255), -1)

        return masked
