"""P&ID Extraction and Digitization Subsystem for AirBench Intake Layer."""

from .adapter import PidAdapterError, PidIntakeAdapter
from .records import PIDRecord, PidComponent, PidRelation

__all__ = [
    "PIDRecord", "PidAdapterError", "PidComponent", "PidIntakeAdapter", "PidRelation",
]

try:
    from .config import PREDEFINED_LEGEND
    from .pipeline import PIDPipeline
    from .symbol_classifier import SymbolClassifier

    __all__ += ["PREDEFINED_LEGEND", "PIDPipeline", "SymbolClassifier"]
except ImportError:  # local vision dependencies are optional
    pass
