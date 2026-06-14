import sys
from pathlib import Path
ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config.wizard import parse_natural_language_intent
import json
cases=[
    "Aggressive GOLD#m M15 H1, 2% risk, $100 max loss",
    "Conservative EURUSD 1m, 0.5% position size, max loss $50",
    "Balanced BTCUSD 5m, 1%",
    "I want to trade gold on H1 and M15, balanced",
    "Use EURUSD#, daily, 2 percent, 200 dollars max loss",
]
for c in cases:
    print('INPUT:', c)
    print(json.dumps(parse_natural_language_intent(c), indent=2))
    print('---')




