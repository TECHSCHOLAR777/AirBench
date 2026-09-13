from typing import List, Dict, Any
import math
import networkx as nx

from .config import LINE_CONFIG


def point_to_box_dist(px: float, py: float, box: List[float]) -> float:
    """Computes shortest Euclidean distance from a point to an axis-aligned bounding box."""
    xmin, ymin, xmax, ymax = box
    dx = max(xmin - px, 0, px - xmax)
    dy = max(ymin - py, 0, py - ymax)
    return math.hypot(dx, dy)


def box_to_box_dist(box1: List[float], box2: List[float]) -> float:
    """Computes shortest Euclidean distance between two bounding boxes (0 if overlapping)."""
    x1_min, y1_min, x1_max, y1_max = box1
    x2_min, y2_min, x2_max, y2_max = box2
    dx = max(x1_min - x2_max, 0, x2_min - x1_max)
    dy = max(y1_min - y2_max, 0, y2_min - y1_max)
    return math.hypot(dx, dy)


class TopologyBuilder:
    def __init__(self, snap_tolerance: float = None, text_association_dist: float = 60.0):
        self.snap_tolerance = snap_tolerance or LINE_CONFIG["snap_tolerance"]
        self.text_association_dist = text_association_dist

    def build_topology(
        self,
        symbols: List[Dict[str, Any]],
        line_data: Dict[str, Any],
        text_results: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Constructs the unified topological graph:
        1. Sequentially indexes Symbol nodes, Connector nodes, and Crossing nodes.
        2. Associates text entities with nearest symbols (tags) and registers Text nodes.
        3. Preserves and maps direct topology edges with unique line IDs.
        4. Falls back to snapping and segment chaining if raw vector lines are provided.
        5. Produces node lists, edge lists, and text entities strictly matching target formats.
        """
        G = nx.Graph()
        old_to_new_id = {}

        # 1. Register Symbol Nodes
        node_counter = 1
        symbol_nodes = []
        symbol_map = {}

        for sym in symbols:
            node_id = f"{sym['label']}{node_counter}"
            node_counter += 1

            old_id = sym.get("id", node_id)
            old_to_new_id[old_id] = node_id

            sym_dict = {
                "id": node_id,
                "label": sym["label"],
                "class_id": sym.get("class_id", 0),
                "confidence": sym.get("confidence", 1.0),
                "bbox": sym["bbox"],
                "tag": sym.get("tag", None)
            }
            symbol_nodes.append(sym_dict)
            symbol_map[node_id] = sym_dict
            G.add_node(node_id, **sym_dict, type="symbol")

        # 2. Process and Register Text Nodes & Associate Tags to Symbols
        text_nodes = []
        if text_results:
            for t_idx, txt in enumerate(text_results):
                t_id = f"text_{t_idx + 1}"
                t_box = txt["bbox"]
                t_str = txt.get("text", "").strip()
                conf = float(txt.get("confidence", 1.0))

                # Find closest symbol within association distance
                best_sym_id = None
                min_dist = float("inf")
                for sym in symbol_nodes:
                    dist = box_to_box_dist(t_box, sym["bbox"])
                    if dist < min_dist and dist <= self.text_association_dist:
                        min_dist = dist
                        best_sym_id = sym["id"]

                text_dict = {
                    "id": t_id,
                    "label": "text",
                    "text": t_str,
                    "confidence": round(conf, 4),
                    "bbox": [round(float(c), 2) for c in t_box],
                    "associated_to": best_sym_id
                }
                text_nodes.append(text_dict)
                G.add_node(t_id, **text_dict, type="text")

                # If associated, attach tag to symbol
                if best_sym_id:
                    curr_tag = symbol_map[best_sym_id].get("tag")
                    if not curr_tag:
                        symbol_map[best_sym_id]["tag"] = t_str
                    else:
                        symbol_map[best_sym_id]["tag"] = f"{curr_tag} {t_str}"

        # 3. Register Connector Nodes
        connectors_in = line_data.get("connectors", [])
        connector_nodes = []

        for c in connectors_in:
            c_new_id = f"connector{node_counter}"
            node_counter += 1

            old_to_new_id[c["id"]] = c_new_id

            c_dict = {
                "id": c_new_id,
                "label": "connector",
                "x": c["x"],
                "y": c["y"],
                "parent_sym": c.get("parent_sym"),
                "bbox": [int(c["bbox"][0]), int(c["bbox"][1]), int(c["bbox"][2]), int(c["bbox"][3])]
            }
            connector_nodes.append(c_dict)
            G.add_node(c_new_id, **c_dict, type="connector")

        # 4. Register Crossing Nodes
        crossings_in = line_data.get("crossings", [])
        crossing_nodes = []

        for cr in crossings_in:
            cr_new_id = f"crossing{node_counter}"
            node_counter += 1

            old_to_new_id[cr["id"]] = cr_new_id

            cr_dict = {
                "id": cr_new_id,
                "label": "crossing",
                "x": cr["x"],
                "y": cr["y"],
                "bbox": [int(cr["bbox"][0]), int(cr["bbox"][1]), int(cr["bbox"][2]), int(cr["bbox"][3])]
            }
            crossing_nodes.append(cr_dict)
            G.add_node(cr_new_id, **cr_dict, type="crossing")

        edges = []
        added_edges = set()

        # 4. If direct edges are provided by LineDetector
        direct_edges = line_data.get("edges", [])
        if direct_edges:
            for de in direct_edges:
                u_old = de["source"]
                v_old = de["target"]
                u_new = old_to_new_id.get(u_old, u_old)
                v_new = old_to_new_id.get(v_old, v_old)

                if u_new in G and v_new in G and u_new != v_new:
                    pair = (min(u_new, v_new), max(u_new, v_new))
                    if pair not in added_edges:
                        added_edges.add(pair)
                        G.add_edge(u_new, v_new, edge_label=de.get("edge_label", "solid"))
                        edges.append({
                            "source": u_new,
                            "target": v_new,
                            "edge_label": de.get("edge_label", "solid")
                        })
        else:
            # Fallback 4a: Snap Connector Terminals to Parent Symbols
            for c in connector_nodes:
                cx, cy = c["x"], c["y"]
                min_dist = float("inf")
                closest_sym_id = None

                for sym in symbol_nodes:
                    d = point_to_box_dist(cx, cy, sym["bbox"])
                    if d < min_dist and d <= self.snap_tolerance:
                        min_dist = d
                        closest_sym_id = sym["id"]

                if closest_sym_id:
                    pair = (min(closest_sym_id, c["id"]), max(closest_sym_id, c["id"]))
                    if pair not in added_edges:
                        added_edges.add(pair)
                        G.add_edge(closest_sym_id, c["id"], edge_label="solid")
                        edges.append({
                            "source": closest_sym_id,
                            "target": c["id"],
                            "edge_label": "solid"
                        })

            # Fallback 4b: Connect Line Endpoints & Crossings
            lines = line_data.get("lines", [])
            for line in lines:
                c1 = old_to_new_id.get(line["start_connector"])
                c2 = old_to_new_id.get(line["end_connector"])

                if not c1 or not c2 or c1 == c2:
                    continue

                x1, y1 = line["start"]
                x2, y2 = line["end"]
                min_x, max_x = min(x1, x2), max(x1, x2)
                min_y, max_y = min(y1, y2), max(y1, y2)

                on_segment_crossings = []
                for cr in crossing_nodes:
                    cr_x, cr_y = cr["x"], cr["y"]
                    if min_x <= cr_x <= max_x and min_y <= cr_y <= max_y:
                        if abs(y1 - y2) <= 5 and abs(cr_y - y1) <= 5:
                            on_segment_crossings.append((cr["id"], cr_x))
                        elif abs(x1 - x2) <= 5 and abs(cr_x - x1) <= 5:
                            on_segment_crossings.append((cr["id"], cr_y))

                if on_segment_crossings:
                    on_segment_crossings.sort(key=lambda item: item[1])
                    chain = [c1] + [cr_id for cr_id, _ in on_segment_crossings] + [c2]
                    for u, v in zip(chain[:-1], chain[1:]):
                        pair = (min(u, v), max(u, v))
                        if pair not in added_edges:
                            added_edges.add(pair)
                            G.add_edge(u, v, edge_label="solid")
                            edges.append({"source": u, "target": v, "edge_label": "solid"})
                else:
                    pair = (min(c1, c2), max(c1, c2))
                    if pair not in added_edges:
                        added_edges.add(pair)
                        G.add_edge(c1, c2, edge_label="solid")
                        edges.append({"source": c1, "target": c2, "edge_label": "solid"})

        # Assign unique IDs to each edge
        for idx, e in enumerate(edges):
            line_id = f"line_{idx + 1}"
            e["id"] = line_id
            if G.has_edge(e["source"], e["target"]):
                G[e["source"]][e["target"]]["id"] = line_id

        print(f"[TopologyBuilder] Built topology with {len(symbol_nodes)} symbols, {len(connector_nodes)} connectors, {len(crossing_nodes)} crossings, {len(edges)} edges, and {len(text_nodes)} text entities.")

        return {
            "graph": G,
            "symbols": symbol_nodes,
            "connectors": connector_nodes,
            "crossings": crossing_nodes,
            "edges": edges,
            "texts": text_nodes
        }
