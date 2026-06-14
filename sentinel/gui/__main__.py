"""
SENTINEL GUI Entry Point
Run with: python -m gui (from sentinel directory)
Or: python -m sentinel.gui (from workspace)
"""

import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.dashboard import main

if __name__ == "__main__":
    main()
