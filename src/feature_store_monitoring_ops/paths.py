"""Project paths used by the local CLI."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SYNTHETIC_EVENTS_PATH = PROJECT_ROOT / "data" / "processed" / "synthetic_events.csv"
DEFAULT_SYNTHETIC_REPORT_PATH = PROJECT_ROOT / "reports" / "synthetic_events_summary.md"

__all__ = [
    "DEFAULT_SYNTHETIC_EVENTS_PATH",
    "DEFAULT_SYNTHETIC_REPORT_PATH",
    "PROJECT_ROOT",
]
