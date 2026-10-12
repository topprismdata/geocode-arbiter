"""geocode-arbiter: WP04 地理编码仲裁层。"""
from geocode_arbiter.arbiter import (
    Decision,
    POI_HIGH_CONFIDENCE,
    Record,
    Verdict,
    arbitrate,
)
from geocode_arbiter.providers.base import AbstainResult, Candidate, Provider, ReverseResult

__version__ = "0.1.0"

__all__ = [
    "AbstainResult", "Candidate", "Decision", "POI_HIGH_CONFIDENCE",
    "Provider", "Record", "ReverseResult", "Verdict", "arbitrate",
    "__version__",
]
