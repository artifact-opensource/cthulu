import os
import sys

# Ensure project root is on sys.path so imports like `from cthulu...` work
# even when pytest sets the test directory as the first entry.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)




