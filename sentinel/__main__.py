"""
SENTINEL CLI Entry Point
Run with: python -m sentinel (from workspace directory)
Or: cd C:\\workspace && python -m sentinel
"""

import sys
import os

# Add sentinel parent directory to path for proper imports
sentinel_dir = os.path.dirname(os.path.abspath(__file__))
workspace_dir = os.path.dirname(sentinel_dir)
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from sentinel.core.guardian import main

if __name__ == "__main__":
    main()
