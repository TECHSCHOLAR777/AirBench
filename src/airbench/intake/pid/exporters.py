import json
import xml.dom.minidom
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any


def export_to_graphml(topology_data: Dict[str, Any], output_path: str):
    """
    Exports the topology graph to GraphML strictly conforming to the target schema:
    - d0: label (string)
    - d1: xmin (double)
    - d2: xmax (double)
    - d3: ymin (double)
    - d4: ymax (double)
    - d5: xmin (long)
    - d6: ymin (long)
    - d7: xmax (long)
    - d8: ymax (long)
    - d9: edge_label (string)
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    root = ET.Element("graphml", {
        "xmlns": "http://graphml.graphdrawing.org/xmlns",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "http://graphml.graphdrawing.org/xmlns http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd"
    })

    # Add Keys matching GraphML schema + extensions for tags and text
    ET.SubElement(root, "key", {"id": "d11", "for": "node", "attr.name": "text", "attr.type": "string"})
    ET.SubElement(root, "key", {"id": "d10", "for": "node", "attr.name": "tag", "attr.type": "string"})
    ET.SubElement(root, "key", {"id": "d9", "for": "edge", "attr.name": "edge_label", "attr.type": "string"})
    ET.SubElement(root, "key", {"id": "d8", "for": "node", "attr.name": "ymax", "attr.type": "double"})
    ET.SubElement(root, "key", {"id": "d7", "for": "node", "attr.name": "xmax", "attr.type": "double"})
    ET.SubElement(root, "key", {"id": "d6", "for": "node", "attr.name": "ymin", "attr.type": "double"})
    ET.SubElement(root, "key", {"id": "d5", "for": "node", "attr.name": "xmin", "attr.type": "double"})
    ET.SubElement(root, "key", {"id": "d4", "for": "node", "attr.name": "ymax", "attr.type": "long"})
    ET.SubElement(root, "key", {"id": "d3", "for": "node", "attr.name": "xmax", "attr.type": "long"})
    ET.SubElement(root, "key", {"id": "d2", "for": "node", "attr.name": "ymin", "attr.type": "long"})
    ET.SubElement(root, "key", {"id": "d1", "for": "node", "attr.name": "xmin", "attr.type": "long"})
    ET.SubElement(root, "key", {"id": "d0", "for": "node", "attr.name": "label", "attr.type": "string"})

    graph_elem = ET.SubElement(root, "graph", {"edgedefault": "undirected"})

    # 1. Symbol Nodes (Keys d0, d5-d8: xmin, ymin, xmax, ymax as double, d10: tag)
    for sym in topology_data.get("symbols", []):
        node = ET.SubElement(graph_elem, "node", {"id": sym["id"]})

        d0 = ET.SubElement(node, "data", {"key": "d0"})
        d0.text = sym["label"]

        if sym.get("tag"):
            d10 = ET.SubElement(node, "data", {"key": "d10"})
            d10.text = str(sym["tag"])

        xmin, ymin, xmax, ymax = sym["bbox"]

        d5 = ET.SubElement(node, "data", {"key": "d5"})
        d5.text = str(float(xmin))

        d6 = ET.SubElement(node, "data", {"key": "d6"})
        d6.text = str(float(ymin))

        d7 = ET.SubElement(node, "data", {"key": "d7"})
        d7.text = str(float(xmax))

        d8 = ET.SubElement(node, "data", {"key": "d8"})
        d8.text = str(float(ymax))

    # 2. Connector Nodes (Keys d0, d1-d4: xmin, ymin, xmax, ymax as long)
    for conn in topology_data.get("connectors", []):
        node = ET.SubElement(graph_elem, "node", {"id": conn["id"]})

        d0 = ET.SubElement(node, "data", {"key": "d0"})
        d0.text = "connector"

        xmin, ymin, xmax, ymax = conn["bbox"]

        d1 = ET.SubElement(node, "data", {"key": "d1"})
        d1.text = str(int(round(xmin)))

        d2 = ET.SubElement(node, "data", {"key": "d2"})
        d2.text = str(int(round(ymin)))

        d3 = ET.SubElement(node, "data", {"key": "d3"})
        d3.text = str(int(round(xmax)))

        d4 = ET.SubElement(node, "data", {"key": "d4"})
        d4.text = str(int(round(ymax)))

    # 3. Crossing Nodes (Keys d0, d1-d4: xmin, ymin, xmax, ymax as long)
    for cr in topology_data.get("crossings", []):
        node = ET.SubElement(graph_elem, "node", {"id": cr["id"]})

        d0 = ET.SubElement(node, "data", {"key": "d0"})
        d0.text = "crossing"

        xmin, ymin, xmax, ymax = cr["bbox"]

        d1 = ET.SubElement(node, "data", {"key": "d1"})
        d1.text = str(int(round(xmin)))

        d2 = ET.SubElement(node, "data", {"key": "d2"})
        d2.text = str(int(round(ymin)))

        d3 = ET.SubElement(node, "data", {"key": "d3"})
        d3.text = str(int(round(xmax)))

        d4 = ET.SubElement(node, "data", {"key": "d4"})
        d4.text = str(int(round(ymax)))

    # 4. Text Nodes (Keys d0, d5-d8: xmin, ymin, xmax, ymax as double, d11: text)
    for txt in topology_data.get("texts", []):
        node = ET.SubElement(graph_elem, "node", {"id": txt["id"]})

        d0 = ET.SubElement(node, "data", {"key": "d0"})
        d0.text = "text"

        xmin, ymin, xmax, ymax = txt["bbox"]

        d5 = ET.SubElement(node, "data", {"key": "d5"})
        d5.text = str(float(xmin))

        d6 = ET.SubElement(node, "data", {"key": "d6"})
        d6.text = str(float(ymin))

        d7 = ET.SubElement(node, "data", {"key": "d7"})
        d7.text = str(float(xmax))

        d8 = ET.SubElement(node, "data", {"key": "d8"})
        d8.text = str(float(ymax))

        d11 = ET.SubElement(node, "data", {"key": "d11"})
        d11.text = str(txt.get("text", ""))

    # 5. Edges (id: line_X, d9: edge_label)
    for edge_idx, edge in enumerate(topology_data.get("edges", [])):
        edge_id = edge.get("id", f"line_{edge_idx + 1}")
        edge_elem = ET.SubElement(graph_elem, "edge", {
            "id": edge_id,
            "source": edge["source"],
            "target": edge["target"]
        })
        d9 = ET.SubElement(edge_elem, "data", {"key": "d9"})
        d9.text = edge.get("edge_label", "solid")

    # Format XML nicely
    xml_str = ET.tostring(root, encoding="utf-8")
    dom = xml.dom.minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent="  ", encoding="utf-8")

    with open(output_path, "wb") as f:
        f.write(pretty_xml)

    print(f"[Exporter] Successfully exported GraphML to {output_path}")


def export_to_json(topology_data: Dict[str, Any], output_path: str, metadata: Dict[str, Any] = None):
    """
    Exports the generated graph into an intuitive, readable JSON format.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    json_payload = {
        "metadata": metadata or {},
        "summary": {
            "total_symbols": len(topology_data.get("symbols", [])),
            "total_connectors": len(topology_data.get("connectors", [])),
            "total_crossings": len(topology_data.get("crossings", [])),
            "total_edges": len(topology_data.get("edges", [])),
            "total_texts": len(topology_data.get("texts", []))
        },
        "symbols": topology_data.get("symbols", []),
        "connectors": topology_data.get("connectors", []),
        "crossings": topology_data.get("crossings", []),
        "edges": topology_data.get("edges", []),
        "texts": topology_data.get("texts", [])
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_payload, f, indent=2)

    print(f"[Exporter] Successfully exported JSON graph to {output_path}")
