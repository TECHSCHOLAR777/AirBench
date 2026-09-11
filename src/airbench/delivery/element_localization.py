#!/usr/bin/env python3
"""
P&ID Element Localization Engine
================================
Localizes, crops, and badges cited engineering components from P&ID drawings
for direct embedding into Word (.docx) inspection notes, Excel (.xlsx) schedules,
and PDF reports.

Features:
- Locates components by unique Node ID (e.g. "valve1"), Tag query (e.g. "4086"), or Bounding Box.
- Extracts high-resolution contextual crops with configurable padding.
- Draws crisp engineering badges and high-contrast bounding boxes.
- Outputs PNG image bytes directly for python-docx (document.add_picture) or saves to disk.
- Extracts tabular coordinate metadata for Excel (openpyxl) equipment registers.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
import io
import json
import xml.etree.ElementTree as ET
import cv2
import numpy as np


# Engineering Badge Color Palette (BGR for OpenCV)
BADGE_PALETTE = {
    "valve": {"border": (0, 140, 255), "badge_bg": (0, 140, 255), "text": (255, 255, 255)},           # Safety Orange
    "instrumentation": {"border": (255, 115, 20), "badge_bg": (255, 115, 20), "text": (255, 255, 255)}, # Cobalt Blue
    "general": {"border": (180, 0, 180), "badge_bg": (180, 0, 180), "text": (255, 255, 255)},          # Magenta
    "connector": {"border": (0, 210, 255), "badge_bg": (0, 210, 255), "text": (0, 0, 0)},             # Amber Yellow
    "crossing": {"border": (40, 40, 230), "badge_bg": (40, 40, 230), "text": (255, 255, 255)},         # Ruby Red
    "default": {"border": (0, 200, 70), "badge_bg": (0, 200, 70), "text": (255, 255, 255)},            # Emerald Green
}


def load_elements_from_json(json_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Loads extracted symbols and components from an AirBench/PID JSON output."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    symbols = data.get("symbols", [])
    connectors = data.get("connectors", [])
    crossings = data.get("crossings", [])
    return symbols + connectors + crossings


def load_elements_from_graphml(graphml_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Lightweight self-contained parser for P&ID GraphML (no evaluator.py dependency)."""
    tree = ET.parse(graphml_path)
    root = tree.getroot()
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}

    # Dynamic key mapping
    key_by_attr = {}
    for key in root.findall("g:key", ns):
        k_id = key.get("id")
        attr_name = key.get("attr.name")
        attr_type = key.get("attr.type")
        key_by_attr[(attr_name, attr_type)] = k_id

    label_k = key_by_attr.get(("label", "string"), "d0")
    tag_k = key_by_attr.get(("tag", "string"), "d10")
    d_xmin = key_by_attr.get(("xmin", "double"), "d5")
    d_ymin = key_by_attr.get(("ymin", "double"), "d6")
    d_xmax = key_by_attr.get(("xmax", "double"), "d7")
    d_ymax = key_by_attr.get(("ymax", "double"), "d8")
    l_xmin = key_by_attr.get(("xmin", "long"), "d1")
    l_ymin = key_by_attr.get(("ymin", "long"), "d2")
    l_xmax = key_by_attr.get(("xmax", "long"), "d3")
    l_ymax = key_by_attr.get(("ymax", "long"), "d4")

    elements = []
    graph = root.find("g:graph", ns)
    if graph is None:
        return elements

    for node in graph.findall("g:node", ns):
        node_id = node.get("id", "")
        data_dict = {d.get("key"): d.text for d in node.findall("g:data", ns)}
        label = data_dict.get(label_k, "general")
        if label == "text" or node_id.startswith("text"):
            continue

        tag = data_dict.get(tag_k, None)

        if d_xmin in data_dict and data_dict[d_xmin] is not None:
            xmin = float(data_dict[d_xmin])
            ymin = float(data_dict[d_ymin])
            xmax = float(data_dict[d_xmax])
            ymax = float(data_dict[d_ymax])
        elif l_xmin in data_dict and data_dict[l_xmin] is not None:
            xmin = float(data_dict[l_xmin])
            ymin = float(data_dict[l_ymin])
            xmax = float(data_dict[l_xmax])
            ymax = float(data_dict[l_ymax])
        else:
            continue

        bbox = [min(xmin, xmax), min(ymin, ymax), max(xmin, xmax), max(ymin, ymax)]
        elements.append({
            "id": node_id,
            "label": label,
            "tag": tag,
            "bbox": bbox
        })
    return elements


class ElementLocalizer:
    """
    Localizes and crops visual elements from high-resolution P&ID drawings
    for inclusion into Word reports (.docx) and Excel spreadsheets (.xlsx).
    """

    def __init__(self, image_input: Union[str, Path, np.ndarray]):
        if isinstance(image_input, (str, Path)):
            self.image_path = Path(image_input)
            self.image = cv2.imread(str(self.image_path))
            if self.image is None:
                raise FileNotFoundError(f"Could not load P&ID drawing at: {image_input}")
        elif isinstance(image_input, np.ndarray):
            self.image_path = None
            self.image = image_input
        else:
            raise TypeError("image_input must be a file path or numpy array.")

        self.height, self.width = self.image.shape[:2]

    def find_element(
        self,
        elements: List[Dict[str, Any]],
        query: str
    ) -> Optional[Dict[str, Any]]:
        """
        Finds an element by matching:
        1. Exact ID (e.g. "valve1", "instrumentation5")
        2. Tag text match (e.g. "4086", "FCV-102")
        3. Case-insensitive substring match
        """
        q = query.strip().lower()

        # 1. Exact ID match
        for el in elements:
            if el.get("id", "").lower() == q:
                return el

        # 2. Exact Tag match
        for el in elements:
            if str(el.get("tag") or "").lower() == q:
                return el

        # 3. Substring match on ID or Tag
        for el in elements:
            if q in el.get("id", "").lower() or q in str(el.get("tag") or "").lower():
                return el

        return None

    def crop_and_badge_element(
        self,
        bbox: List[float],
        label: str = "Component",
        tag: Optional[str] = None,
        padding: int = 60,
        draw_badge: bool = True
    ) -> np.ndarray:
        """
        Crops a contextual region around the element bounding box and applies
        a professional engineering bounding box and label badge.
        """
        xmin, ymin, xmax, ymax = [int(round(c)) for c in bbox]

        # Apply padding with image bounds clipping
        crop_x1 = max(0, xmin - padding)
        crop_y1 = max(0, ymin - padding)
        crop_x2 = min(self.width, xmax + padding)
        crop_y2 = min(self.height, ymax + padding)

        crop = self.image[crop_y1:crop_y2, crop_x1:crop_x2].copy()

        if draw_badge:
            # Map coordinates relative to crop
            bx1 = xmin - crop_x1
            by1 = ymin - crop_y1
            bx2 = xmax - crop_x1
            by2 = ymax - crop_y1

            palette = BADGE_PALETTE.get(label.lower(), BADGE_PALETTE["default"])
            color_border = palette["border"]
            color_bg = palette["badge_bg"]
            color_text = palette["text"]

            # Draw high-contrast bounding box
            cv2.rectangle(crop, (bx1, by1), (bx2, by2), color_border, 3, cv2.LINE_AA)

            # Format badge text
            badge_text = f"{label.upper()}"
            if tag:
                badge_text += f": {tag}"

            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.55
            thickness = 2
            (tw, th), baseline = cv2.getTextSize(badge_text, font, font_scale, thickness)

            # Badge pill coordinates
            pill_y2 = max(0, by1 - 4)
            pill_y1 = max(0, pill_y2 - th - 8)
            pill_x1 = bx1
            pill_x2 = min(crop.shape[1], bx1 + tw + 12)

            # Draw filled badge pill
            cv2.rectangle(crop, (pill_x1, pill_y1), (pill_x2, pill_y2), color_bg, -1)
            cv2.rectangle(crop, (pill_x1, pill_y1), (pill_x2, pill_y2), color_border, 1)

            # Draw text inside badge
            text_x = pill_x1 + 6
            text_y = pill_y2 - 5
            cv2.putText(crop, badge_text, (text_x, text_y), font, font_scale, color_text, thickness, cv2.LINE_AA)

        return crop

    def localize_element(
        self,
        element_or_query: Union[str, Dict[str, Any]],
        elements: Optional[List[Dict[str, Any]]] = None,
        padding: int = 60,
        output_path: Optional[Union[str, Path]] = None,
        as_png_bytes: bool = False
    ) -> Union[bytes, Path, np.ndarray]:
        """
        Localizes an element, generates the visual badge crop, and returns
        either PNG bytes (for Word/Excel embedding) or writes to output_path.
        """
        if isinstance(element_or_query, dict):
            target = element_or_query
        elif isinstance(element_or_query, str):
            if elements is None:
                raise ValueError("elements list must be provided when querying by ID or string.")
            target = self.find_element(elements, element_or_query)
            if target is None:
                raise KeyError(f"Element '{element_or_query}' not found in P&ID elements.")
        else:
            raise TypeError("element_or_query must be a dict or a string query.")

        bbox = target["bbox"]
        label = target.get("label", target.get("id", "component"))
        tag = target.get("tag")

        cropped = self.crop_and_badge_element(bbox=bbox, label=label, tag=tag, padding=padding)

        if as_png_bytes:
            success, buffer = cv2.imencode(".png", cropped)
            if not success:
                raise RuntimeError("Failed to encode cropped element to PNG.")
            return buffer.tobytes()

        if output_path is not None:
            out_p = Path(output_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out_p), cropped)
            return out_p

        return cropped

    @staticmethod
    def extract_tabular_data(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Formats localized elements into tabular records ready for Excel (openpyxl)
        equipment schedules and line lists.
        """
        table_rows = []
        for el in elements:
            bbox = el.get("bbox", [0, 0, 0, 0])
            cx = round((bbox[0] + bbox[2]) / 2.0, 1)
            cy = round((bbox[1] + bbox[3]) / 2.0, 1)
            table_rows.append({
                "ID": el.get("id", ""),
                "Category": el.get("label", ""),
                "Tag": el.get("tag") or "N/A",
                "Coordinates_X": cx,
                "Coordinates_Y": cy,
                "BoundingBox": f"[{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]"
            })
        return table_rows


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Localize and crop visual elements from P&ID drawings.")
    parser.add_argument("--image", required=True, help="Path to input P&ID image (e.g. input_images/0.png)")
    parser.add_argument("--graphml", default=None, help="Path to GraphML file (e.g. output/0_generated.graphml)")
    parser.add_argument("--json-graph", default=None, help="Path to JSON graph file")
    parser.add_argument("--query", required=True, help="Component ID (e.g. 'valve1') or tag number (e.g. '4086')")
    parser.add_argument("--padding", type=int, default=60, help="Pixel padding around element")
    parser.add_argument("--output", default="output/localized_crop.png", help="Path to save output cropped image")

    args = parser.parse_args()

    localizer = ElementLocalizer(args.image)

    # Load elements
    elements = []
    if args.graphml:
        elements = load_elements_from_graphml(args.graphml)
    elif args.json_graph:
        elements = load_elements_from_json(args.json_graph)
    else:
        # Fallback to auto-detecting graphml next to image
        in_stem = Path(args.image).stem
        candidate = Path("output") / f"{in_stem}_generated.graphml"
        if candidate.exists():
            elements = load_elements_from_graphml(candidate)

    out = localizer.localize_element(
        element_or_query=args.query,
        elements=elements,
        padding=args.padding,
        output_path=args.output
    )
    print(f"[ElementLocalizer] Successfully localized '{args.query}' -> Saved to {out}")
