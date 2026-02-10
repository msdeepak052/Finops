"""Pytest configuration — ensure part2 source is on sys.path."""

import sys
from pathlib import Path

# Add part2/ directory to sys.path so `bedrock_validator` is importable
PART2_DIR = Path(__file__).resolve().parent.parent
if str(PART2_DIR) not in sys.path:
    sys.path.insert(0, str(PART2_DIR))
