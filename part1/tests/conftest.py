"""Pytest configuration — ensure part1 source is on sys.path."""

import sys
from pathlib import Path

# Add part1/ directory to sys.path so `compute_optimizer` is importable
PART1_DIR = Path(__file__).resolve().parent.parent
if str(PART1_DIR) not in sys.path:
    sys.path.insert(0, str(PART1_DIR))
