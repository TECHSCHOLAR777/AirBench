from typing import List, Dict, Any, Tuple
import math
import cv2
import numpy as np

from .config import LINE_CONFIG


class LineDetector:
    def __init__(
        self,
        mode: str = None,
        binary_threshold: int = None,
        min_line_length: int = None,
        max_line_gap: int = None
    ):
        self.mode = mode or LINE_CONFIG.get("mode", "skeleton_walk")
        self.binary_threshold = binary_threshold or LINE_CONFIG["binary_threshold"]
        self.min_line_length = min_line_length or LINE_CONFIG["min_line_length"]
        self.max_line_gap = max_line_gap or LINE_CONFIG["max_line_gap"]
        self.connector_box_size = LINE_CONFIG["connector_box_size"]
        self.snap_tolerance = LINE_CONFIG["snap_tolerance"]

    def _extract_symbol_terminals(
        self,
        binary_img: np.ndarray,
        symbols: List[Dict[str, Any]],
        cluster_dist: float = 12.0
    ) -> List[Dict[str, Any]]:
        """
        Extracts genuine connector ports at the perimeter boundaries of detected symbols.
        Ground truth rule: 100% of connectors in P&ID diagrams are symbol terminal ports.
        """
        h, w = binary_img.shape[:2]
        raw_candidates = []

        for sym in symbols:
            s_id = sym.get("id")
            xmin, ymin, xmax, ymax = [int(round(v)) for v in sym["bbox"]]
            mid_x = (xmin + xmax) // 2
            mid_y = (ymin + ymax) // 2

            # Sample positions along each of the 4 borders
            # Left edge
            if xmin >= 15:
                for y in [mid_y, ymin + (ymax - ymin) // 4, ymin + 3 * (ymax - ymin) // 4]:
                    if 0 <= y < h:
                        strip = binary_img[max(0, y - 2):min(h, y + 3), max(0, xmin - 20):xmin]
                        if strip.size > 0 and np.mean(np.sum(strip > 0, axis=0) > 0) >= 0.60:
                            raw_candidates.append((float(xmin), float(y), s_id))
                            break

            # Right edge
            if xmax <= w - 15:
                for y in [mid_y, ymin + (ymax - ymin) // 4, ymin + 3 * (ymax - ymin) // 4]:
                    if 0 <= y < h:
                        strip = binary_img[max(0, y - 2):min(h, y + 3), xmax:min(w, xmax + 20)]
                        if strip.size > 0 and np.mean(np.sum(strip > 0, axis=0) > 0) >= 0.60:
                            raw_candidates.append((float(xmax), float(y), s_id))
                            break

            # Top edge
            if ymin >= 15:
                for x in [mid_x, xmin + (xmax - xmin) // 4, xmin + 3 * (xmax - xmin) // 4]:
                    if 0 <= x < w:
                        strip = binary_img[max(0, ymin - 20):ymin, max(0, x - 2):min(w, x + 3)]
                        if strip.size > 0 and np.mean(np.sum(strip > 0, axis=1) > 0) >= 0.60:
                            raw_candidates.append((float(x), float(ymin), s_id))
                            break

            # Bottom edge
            if ymax <= h - 15:
                for x in [mid_x, xmin + (xmax - xmin) // 4, xmin + 3 * (xmax - xmin) // 4]:
                    if 0 <= x < w:
                        strip = binary_img[ymax:min(h, ymax + 20), max(0, x - 2):min(w, x + 3)]
                        if strip.size > 0 and np.mean(np.sum(strip > 0, axis=1) > 0) >= 0.60:
                            raw_candidates.append((float(x), float(ymax), s_id))
                            break

        # Cluster candidate terminals
        clustered = []
        for cx, cy, s_id in raw_candidates:
            matched = False
            for c in clustered:
                if math.hypot(cx - c["x"], cy - c["y"]) <= cluster_dist and c["parent_sym"] == s_id:
                    matched = True
                    break
            if not matched:
                clustered.append({"x": cx, "y": cy, "parent_sym": s_id})

        half_box = self.connector_box_size // 2
        connectors = []
        for idx, c in enumerate(clustered):
            ix, iy = int(round(c["x"])), int(round(c["y"]))
            connectors.append({
                "id": f"connector_{idx + 1}",
                "label": "connector",
                "x": ix,
                "y": iy,
                "parent_sym": c["parent_sym"],
                "bbox": [ix - half_box, iy - half_box, ix + half_box, iy + half_box]
            })

        return connectors

    def _extract_crossings(
        self,
        binary_img: np.ndarray,
        symbols: List[Dict[str, Any]],
        text_boxes: List[List[float]] = None,
        cluster_dist: float = 15.0
    ) -> List[Dict[str, Any]]:
        half_box = self.connector_box_size // 2
        text_boxes = text_boxes or []

        # Mask out interior of symbols and text boxes first to prevent text merging
        masked_binary = binary_img.copy()
        for sym in symbols:
            xmin, ymin, xmax, ymax = [int(round(v)) for v in sym["bbox"]]
            cv2.rectangle(masked_binary, (xmin + 2, ymin + 2), (xmax - 2, ymax - 2), 0, -1)
        for box in text_boxes:
            xmin, ymin, xmax, ymax = [int(round(v)) for v in box]
            cv2.rectangle(masked_binary, (max(0, xmin - 2), max(0, ymin - 2)), (xmax + 2, ymax + 2), 0, -1)

        # Directional gap bridging so dotted/dashed pipelines form valid crossing junctions
        h_close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 1))
        v_close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 21))
        h_bridged = cv2.morphologyEx(masked_binary, cv2.MORPH_CLOSE, h_close_kernel)
        v_bridged = cv2.morphologyEx(masked_binary, cv2.MORPH_CLOSE, v_close_kernel)

        # Horizontal lines (>=35px)
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (35, 1))
        h_lines = cv2.morphologyEx(h_bridged, cv2.MORPH_OPEN, h_kernel)

        # Vertical lines (>=35px)
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 35))
        v_lines = cv2.morphologyEx(v_bridged, cv2.MORPH_OPEN, v_kernel)

        intersections = cv2.bitwise_and(h_lines, v_lines)

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(intersections)

        raw_crossings = []
        for i in range(1, num_labels):
            cx, cy = centroids[i]
            raw_crossings.append((float(cx), float(cy)))

        # Cluster nearby crossing centroids
        clustered = []
        for cx, cy in raw_crossings:
            matched = False
            for c in clustered:
                if math.hypot(cx - c[0], cy - c[1]) <= cluster_dist:
                    matched = True
                    break
            if not matched:
                clustered.append((cx, cy))

        crossings = []
        for idx, (cx, cy) in enumerate(clustered):
            ix, iy = int(round(cx)), int(round(cy))
            crossings.append({
                "id": f"crossing_{idx + 1}",
                "label": "crossing",
                "x": ix,
                "y": iy,
                "bbox": [ix - half_box, iy - half_box, ix + half_box, iy + half_box]
            })

        return crossings

    def _classify_corridor_ink(
        self,
        raw_strip: np.ndarray,
        bridged_strip: np.ndarray,
        axis: int
    ) -> Tuple[bool, str]:
        """
        Analyzes ink continuity and periodic gap distribution along an orthogonal corridor.
        Combines directional morphological bridging and gap run-length profiling.
        Returns:
            (is_valid: bool, edge_label: str)
            where edge_label is 'solid' or 'non-solid'.
        """
        if raw_strip.size == 0 or bridged_strip.size == 0:
            return False, "solid"

        raw_profile = np.sum(raw_strip > 0, axis=axis) > 0
        bridged_profile = np.sum(bridged_strip > 0, axis=axis) > 0

        bridged_density = float(np.mean(bridged_profile))
        raw_density = float(np.mean(raw_profile))

        # If even bridged corridor lacks substantial ink, reject
        if bridged_density < 0.55:
            return False, "solid"

        # Calculate contiguous whitespace gaps in raw profile
        gaps = []
        curr_gap = 0
        for val in raw_profile:
            if not val:
                curr_gap += 1
            else:
                if curr_gap > 0:
                    gaps.append(curr_gap)
                    curr_gap = 0
        if curr_gap > 0:
            gaps.append(curr_gap)

        # Gaps that are significant (>= 6px, typical of dotted/dashed lines in P&ID)
        sig_gaps = [g for g in gaps if g >= 6]

        # Classification rule:
        # Repeating significant gaps with raw density < 0.70 -> verified non-solid (dotted/dashed)
        if len(sig_gaps) >= 2 and raw_density < 0.70:
            return True, "non-solid"
        elif len(sig_gaps) >= 1 and 0.20 <= raw_density <= 0.60:
            return True, "non-solid"
        elif raw_density >= 0.60:
            return True, "solid"
        elif bridged_density >= 0.70 and raw_density >= 0.25:
            return True, "non-solid"

        return False, "solid"

    def _trace_skeleton_walk(
        self,
        binary_img: np.ndarray,
        symbols: List[Dict[str, Any]],
        connectors: List[Dict[str, Any]],
        crossings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Option 1: Symbol-Terminal Guided Tracing & Orthogonal Skeleton Walking
        with Directional Gap Bridging and Edge Classification (solid vs non-solid).
        """
        h, w = binary_img.shape[:2]
        edges = []

        for c in connectors:
            if c.get("parent_sym"):
                edges.append({
                    "source": c["parent_sym"],
                    "target": c["id"],
                    "edge_label": "solid"
                })

        pipe_nodes = connectors + crossings
        pipe_node_map = {n["id"]: n for n in pipe_nodes}

        # 1. Directional morphological gap bridging (25x1 horizontal, 1x25 vertical)
        h_close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
        v_close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25))
        h_bridged = cv2.morphologyEx(binary_img, cv2.MORPH_CLOSE, h_close_kernel)
        v_bridged = cv2.morphologyEx(binary_img, cv2.MORPH_CLOSE, v_close_kernel)

        # Bin nodes by horizontal coordinate (within 4px)
        h_bins = {}
        for n in pipe_nodes:
            cy = n["y"]
            bin_y = None
            for y in h_bins:
                if abs(cy - y) <= 4:
                    bin_y = y
                    break
            if bin_y is None:
                bin_y = cy
                h_bins[bin_y] = []
            h_bins[bin_y].append(n["id"])

        # Bin nodes by vertical coordinate (within 4px)
        v_bins = {}
        for n in pipe_nodes:
            cx = n["x"]
            bin_x = None
            for x in v_bins:
                if abs(cx - x) <= 4:
                    bin_x = x
                    break
            if bin_x is None:
                bin_x = cx
                v_bins[bin_x] = []
            v_bins[bin_x].append(n["id"])

        added_pipe_edges = set()

        # Check horizontal segments
        for bin_y, nids in h_bins.items():
            if len(nids) < 2:
                continue
            sorted_nids = sorted(nids, key=lambda nid: pipe_node_map[nid]["x"])
            for i in range(len(sorted_nids) - 1):
                u, v = sorted_nids[i], sorted_nids[i + 1]
                x1 = pipe_node_map[u]["x"]
                x2 = pipe_node_map[v]["x"]
                if x2 - x1 < 10:
                    continue

                has_block = False
                for sym in symbols:
                    sx1, sy1, sx2, sy2 = sym["bbox"]
                    if sx1 < x2 - 5 and sx2 > x1 + 5 and sy1 < bin_y + 4 and sy2 > bin_y - 4:
                        has_block = True
                        break
                if has_block:
                    continue

                raw_strip = binary_img[max(0, bin_y - 2):min(h, bin_y + 3), x1 + 5:x2 - 5]
                bridged_strip = h_bridged[max(0, bin_y - 2):min(h, bin_y + 3), x1 + 5:x2 - 5]
                is_valid, edge_label = self._classify_corridor_ink(raw_strip, bridged_strip, axis=0)

                if is_valid:
                    pair = (min(u, v), max(u, v))
                    if pair not in added_pipe_edges:
                        added_pipe_edges.add(pair)
                        edges.append({"source": u, "target": v, "edge_label": edge_label})

        # Check vertical segments
        for bin_x, nids in v_bins.items():
            if len(nids) < 2:
                continue
            sorted_nids = sorted(nids, key=lambda nid: pipe_node_map[nid]["y"])
            for i in range(len(sorted_nids) - 1):
                u, v = sorted_nids[i], sorted_nids[i + 1]
                y1 = pipe_node_map[u]["y"]
                y2 = pipe_node_map[v]["y"]
                if y2 - y1 < 10:
                    continue

                has_block = False
                for sym in symbols:
                    sx1, sy1, sx2, sy2 = sym["bbox"]
                    if sy1 < y2 - 5 and sy2 > y1 + 5 and sx1 < bin_x + 4 and sx2 > bin_x - 4:
                        has_block = True
                        break
                if has_block:
                    continue

                raw_strip = binary_img[y1 + 5:y2 - 5, max(0, bin_x - 2):min(w, bin_x + 3)]
                bridged_strip = v_bridged[y1 + 5:y2 - 5, max(0, bin_x - 2):min(w, bin_x + 3)]
                is_valid, edge_label = self._classify_corridor_ink(raw_strip, bridged_strip, axis=1)

                if is_valid:
                    pair = (min(u, v), max(u, v))
                    if pair not in added_pipe_edges:
                        added_pipe_edges.add(pair)
                        edges.append({"source": u, "target": v, "edge_label": edge_label})

        return edges


    def _trace_morphological_vector(
        self,
        binary_img: np.ndarray,
        symbols: List[Dict[str, Any]],
        connectors: List[Dict[str, Any]],
        crossings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Option 2: Directional Morphological Kernel Filtering & Hough Line Vectorization.
        """
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (35, 1))
        h_lines = cv2.morphologyEx(binary_img, cv2.MORPH_OPEN, h_kernel)

        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 35))
        v_lines = cv2.morphologyEx(binary_img, cv2.MORPH_OPEN, v_kernel)

        h_hough = cv2.HoughLinesP(h_lines, 1, np.pi / 180, threshold=25, minLineLength=25, maxLineGap=20)
        v_hough = cv2.HoughLinesP(v_lines, 1, np.pi / 180, threshold=25, minLineLength=25, maxLineGap=20)

        all_hough_lines = []
        if h_hough is not None:
            for l in h_hough:
                all_hough_lines.append(l.flatten().tolist())
        if v_hough is not None:
            for l in v_hough:
                all_hough_lines.append(l.flatten().tolist())

        all_nodes = connectors + crossings
        edges = []
        for c in connectors:
            if c.get("parent_sym"):
                edges.append({"source": c["parent_sym"], "target": c["id"], "edge_label": "solid"})

        added_edges = set()
        for line in all_hough_lines:
            x1, y1, x2, y2 = line[:4]
            best_c1, best_d1 = None, self.snap_tolerance
            best_c2, best_d2 = None, self.snap_tolerance
            for node in all_nodes:
                d1 = math.hypot(x1 - node["x"], y1 - node["y"])
                if d1 < best_d1:
                    best_d1 = d1
                    best_c1 = node["id"]
                d2 = math.hypot(x2 - node["x"], y2 - node["y"])
                if d2 < best_d2:
                    best_d2 = d2
                    best_c2 = node["id"]
            if best_c1 and best_c2 and best_c1 != best_c2:
                pair = (min(best_c1, best_c2), max(best_c1, best_c2))
                if pair not in added_edges:
                    added_edges.add(pair)
                    edges.append({"source": best_c1, "target": best_c2, "edge_label": "solid"})

        return edges

    def extract_lines_and_junctions(
        self,
        image_path: str,
        symbols: List[Dict[str, Any]] = None,
        symbol_boxes: List[List[float]] = None,
        text_boxes: List[List[float]] = None
    ) -> Dict[str, Any]:
        if symbols is None:
            if symbol_boxes is not None:
                symbols = [{"id": f"sym_{i+1}", "label": "general", "bbox": b} for i, b in enumerate(symbol_boxes)]
            else:
                symbols = []
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Could not load image: {image_path}")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, self.binary_threshold, 255, cv2.THRESH_BINARY_INV)

        # Directional gap bridging for terminal extraction so dotted line nozzles are detected
        h_close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
        v_close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25))
        h_bridged = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, h_close_kernel)
        v_bridged = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, v_close_kernel)
        bridged_terminals = cv2.bitwise_or(h_bridged, v_bridged)

        connectors = self._extract_symbol_terminals(bridged_terminals, symbols, cluster_dist=12.0)
        print(f"[LineDetector] Extracted {len(connectors)} symbol terminal connector ports.")

        crossings = self._extract_crossings(binary, symbols, text_boxes, cluster_dist=15.0)
        print(f"[LineDetector] Extracted {len(crossings)} orthogonal line crossings.")

        print(f"[LineDetector] Tracing topology edges via mode='{self.mode}'...")
        if self.mode == "skeleton_walk":
            edges = self._trace_skeleton_walk(binary, symbols, connectors, crossings)
        elif self.mode == "morphological_vector":
            edges = self._trace_morphological_vector(binary, symbols, connectors, crossings)
        else:
            raise ValueError(f"Unknown line detection mode: {self.mode}")

        print(f"[LineDetector] Traced {len(edges)} total edges connecting symbols, connectors, and crossings.")
        return {
            "connectors": connectors,
            "crossings": crossings,
            "edges": edges
        }
