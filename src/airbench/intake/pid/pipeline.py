import argparse
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Union

from .config import PREDEFINED_LEGEND
from .symbol_detector import SymbolDetector
from .symbol_classifier import SymbolClassifier
from .text_ocr import TextOCR
from .line_detector import LineDetector
from .topology_builder import TopologyBuilder
from .exporters import export_to_graphml, export_to_json


class PIDPipeline:
    """
    End-to-End P&ID Digitization and Graph Extraction Pipeline for AirBench.
    Coordinates symbol detection, pluggable legend classification, text OCR,
    masked line tracing, and topological graph assembly.
    """

    def __init__(
        self,
        custom_legend: Optional[Union[Dict[str, str], str, Path]] = None,
        weights_path: Optional[str] = None
    ):
        self.symbol_detector = SymbolDetector(weights_path=weights_path)
        self.symbol_classifier = SymbolClassifier(legend=custom_legend)
        self.ocr = TextOCR()
        self.line_detector = LineDetector()
        self.topology_builder = TopologyBuilder()

    def process_image(
        self,
        image_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None
    ) -> Dict[str, Any]:
        """
        Executes the full 6-stage P&ID extraction on a single image.
        Returns the assembled topology dictionary and optionally saves GraphML & JSON.
        """
        img_p = Path(image_path)
        if not img_p.exists():
            raise FileNotFoundError(f"P&ID image not found at: {img_p}")

        stem = img_p.stem
        print(f"\n{'=' * 60}")
        print(f"Processing P&ID Image: {img_p.name} (ID: {stem})")
        print(f"{'=' * 60}")

        # Stage 1: Symbol & Component Detection
        print("\n--- [Stage 1] Detecting Symbols & Component Regions ---")
        raw_detections = self.symbol_detector.detect(str(img_p))

        # Stage 2: Symbol & Component Classification (with pluggable legend)
        print("\n--- [Stage 2] Classifying Component Categories & Taxonomy ---")
        symbols = self.symbol_classifier.classify_detected_symbols(raw_detections)

        # Stage 3: Text Localization & OCR
        print("\n--- [Stage 3] Running Text Localization & OCR ---")
        text_results = self.ocr.detect_text(str(img_p))

        # Stage 4: Line & Pipeline Vectorization
        print("\n--- [Stage 4] Tracing Process Lines & Intersections ---")
        text_boxes = [t["bbox"] for t in text_results]
        line_data = self.line_detector.extract_lines_and_junctions(
            str(img_p),
            symbols=symbols,
            text_boxes=text_boxes
        )

        # Stage 5: Topological Snapping & Graph Assembly
        print("\n--- [Stage 5] Assembling Topology Graph ---")
        topology = self.topology_builder.build_topology(symbols, line_data, text_results=text_results)

        # Stage 6: Export Outputs (if output_dir specified)
        if output_dir is not None:
            out_p = Path(output_dir)
            out_p.mkdir(parents=True, exist_ok=True)
            out_graphml_path = out_p / f"{stem}_generated.graphml"
            out_json_path = out_p / f"{stem}_graph.json"
            print(f"\n--- [Stage 6] Exporting Outputs to {out_p} ---")
            export_to_graphml(topology, str(out_graphml_path))
            export_to_json(topology, str(out_json_path), metadata={"image": img_p.name})
            print(f"Saved: {out_graphml_path.name} & {out_json_path.name}")

        return topology


def process_single_image(
    image_path: Path,
    symbol_detector: SymbolDetector,
    symbol_classifier: SymbolClassifier,
    ocr: TextOCR,
    line_detector: LineDetector,
    topology_builder: TopologyBuilder,
    output_dir: Path
) -> Dict[str, Any]:
    """Compatibility runner for single image processing."""
    stem = image_path.stem
    print(f"\n{'=' * 60}")
    print(f"Processing P&ID Image: {image_path.name} (ID: {stem})")
    print(f"{'=' * 60}")

    out_graphml_path = output_dir / f"{stem}_generated.graphml"
    out_json_path = output_dir / f"{stem}_graph.json"

    raw_detections = symbol_detector.detect(str(image_path))
    symbols = symbol_classifier.classify_detected_symbols(raw_detections)
    text_results = ocr.detect_text(str(image_path))
    text_boxes = [t["bbox"] for t in text_results]

    line_data = line_detector.extract_lines_and_junctions(
        str(image_path),
        symbols=symbols,
        text_boxes=text_boxes
    )
    topology = topology_builder.build_topology(symbols, line_data, text_results=text_results)

    output_dir.mkdir(parents=True, exist_ok=True)
    export_to_graphml(topology, str(out_graphml_path))
    export_to_json(topology, str(out_json_path), metadata={"image": image_path.name})
    print(f"\nCompleted {image_path.name} -> Saved: {out_graphml_path.name} & {out_json_path.name}")
    return topology


def main():
    parser = argparse.ArgumentParser(description="End-to-End P&ID Digitization and GraphML Generation Pipeline")
    parser.add_argument("--input", type=str, required=True, help="Path to input image file (e.g. input_images/0.png)")
    parser.add_argument("--output_dir", type=str, default="output", help="Directory to save generated GraphML and JSON")
    parser.add_argument("--legend", type=str, default=None, help="Optional path to custom company legend YAML/JSON file")
    args = parser.parse_args()

    pipeline = PIDPipeline(custom_legend=args.legend)
    pipeline.process_image(image_path=args.input, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
