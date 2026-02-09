"""Pytest configuration — ensure lambda source is on sys.path."""

import sys
from pathlib import Path

# Add lambda/ directory to sys.path so `compute_optimizer` is importable
LAMBDA_DIR = Path(__file__).resolve().parent.parent
if str(LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(LAMBDA_DIR))
