import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from .config import PREDEFINED_LEGEND, CLASS_TO_LABEL_MAP


class SymbolClassifier:
    """
    P&ID Symbol Classification Engine with Pluggable Legend Support.

    Maps detected symbol bounding boxes and predicted class IDs into standard
    engineering taxonomy categories (valve, instrumentation, arrow, general).

    Supports:
    1. Predefined default engineering legend (PREDEFINED_LEGEND)
    2. Company or client-specific custom legend passed via dictionary, YAML, or JSON file.
    """

    def __init__(
        self,
        legend: Optional[Union[Dict[str, str], str, Path]] = None,
        class_to_label_map: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize SymbolClassifier with either default predefined legend or company legend.

        Args:
            legend: Custom company legend as a Dict[str, str], or Path to a YAML/JSON legend file.
            class_to_label_map: Legacy alias for legend dictionary.
        """
        resolved_legend = legend if legend is not None else class_to_label_map

        if resolved_legend is None:
            # Use standard predefined engineering legend
            self.class_to_label_map: Dict[str, str] = dict(PREDEFINED_LEGEND)
            self.legend_source: str = "predefined"
        elif isinstance(resolved_legend, (str, Path)):
            # Load company-specific legend from YAML or JSON file
            self.class_to_label_map = self.load_legend_from_file(resolved_legend)
            self.legend_source = f"file:{Path(resolved_legend).name}"
        elif isinstance(resolved_legend, dict):
            # Company passed an in-memory custom dictionary
            self.class_to_label_map = {str(k): str(v) for k, v in resolved_legend.items()}
            self.legend_source = "company_custom_dict"
        else:
            raise TypeError(f"Unsupported legend type: {type(resolved_legend)}. Expected Dict, str, or Path.")

    @staticmethod
    def load_legend_from_file(file_path: Union[str, Path]) -> Dict[str, str]:
        """
        Loads a company legend from a YAML or JSON file.
        Accepts files with either a direct class mapping or a top-level 'classes'/'legend' block.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Company legend file not found at: {path}")

        content_text = path.read_text(encoding="utf-8")

        if path.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(content_text) or {}
        elif path.suffix.lower() == ".json":
            data = json.loads(content_text) or {}
        else:
            raise ValueError(f"Unsupported legend format '{path.suffix}'. Use .yaml, .yml, or .json")

        # Support nested structure like `classes: {"0": "gate_valve"}` or direct map `{"0": "gate_valve"}`
        raw_classes = data.get("classes") or data.get("legend") or data
        if not isinstance(raw_classes, dict):
            raise ValueError(f"Legend file {path} must contain a mapping of class IDs to labels.")

        return {str(k): str(v) for k, v in raw_classes.items()}

    def classify_detected_symbols(
        self,
        raw_detections: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Takes raw symbol detections from SymbolDetector and assigns classified
        labels, engineering types, and unique node IDs using the active legend.
        """
        symbols = []
        label_counters: Dict[str, int] = {}

        for det in raw_detections:
            cls_id_str = str(det.get("class_id", ""))
            confidence = float(det.get("confidence", 0.0))
            bbox = det.get("bbox", [])

            # Map class ID using active legend (company or predefined)
            if cls_id_str in self.class_to_label_map:
                label = self.class_to_label_map[cls_id_str]
                is_ambiguous = False
            else:
                # Fallback for unmapped classes
                label = "general"
                is_ambiguous = True

            label_counters[label] = label_counters.get(label, 0) + 1
            node_id = f"{label}{label_counters[label]}"

            sym_dict = {
                "id": node_id,
                "label": label,
                "class_id": cls_id_str,
                "confidence": round(confidence, 4),
                "is_ambiguous": is_ambiguous,
                "legend_source": self.legend_source,
                "bbox": [
                    round(float(bbox[0]), 2),
                    round(float(bbox[1]), 2),
                    round(float(bbox[2]), 2),
                    round(float(bbox[3]), 2),
                ]
            }
            symbols.append(sym_dict)

        print(
            f"[SymbolClassifier] Finished classification: {len(symbols)} components categorized "
            f"(active legend: {self.legend_source})."
        )
        return symbols
