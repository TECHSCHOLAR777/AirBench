import os
from pathlib import Path

# AirBench Repository Root and Subsystem Paths
PID_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[4]

# Model Weights Configuration
DEFAULT_WEIGHTS_DIR = REPO_ROOT / "models" / "weights" / "pid"
SYMBOL_WEIGHTS_PATH = Path(
    os.environ.get("PID_WEIGHTS_PATH", DEFAULT_WEIGHTS_DIR / "best.pt")
)
# The intake layer is offline-only.  Operators may provide an already
# verified local artifact; it must never download model weights during intake.
SYMBOL_WEIGHTS_URL = os.environ.get("PID_WEIGHTS_URL", "").strip() or None

# Symbol Detector Hyperparameters
SYMBOL_CONFIG = {
    "confidence_threshold": 0.25,
    "iou_threshold": 0.45,
    "tile_size": 1024,
    "tile_overlap": 128,
}

# Standard Predefined Engineering Taxonomy (mgupta70 32-class baseline)
PREDEFINED_LEGEND = {
    "0": "valve",
    "1": "valve",
    "2": "valve",
    "3": "valve",
    "4": "valve",
    "5": "valve",
    "6": "valve",
    "7": "general",
    "8": "valve",
    "9": "valve",
    "10": "valve",
    "11": "valve",
    "12": "valve",
    "13": "valve",
    "14": "valve",
    "15": "valve",
    "16": "general",
    "17": "general",
    "18": "general",
    "19": "general",
    "20": "general",
    "21": "general",
    "22": "general",
    "23": "arrow",
    "24": "valve",
    "25": "instrumentation",
    "26": "instrumentation",
    "27": "instrumentation",
    "28": "instrumentation",
    "29": "instrumentation",
    "30": "instrumentation",
    "31": "instrumentation",
}

# Backward compatibility alias
CLASS_TO_LABEL_MAP = PREDEFINED_LEGEND

# Line Detector Hyperparameters
LINE_CONFIG = {
    "mode": "skeleton_walk",       # Option 1: Symbol-Terminal Guided Tracing & Skeleton Walking
    "binary_threshold": 140,
    "min_line_length": 15,
    "max_line_gap": 10,
    "snap_tolerance": 25.0,        # Max pixel distance between line endpoint and symbol bbox
    "connector_box_size": 8,       # 8x8 pixel bounding box for connector/crossing nodes
}

# OCR Configuration
OCR_CONFIG = {
    "lang": "en",
    "use_angle_cls": True,
    "min_confidence": 0.5,
}
