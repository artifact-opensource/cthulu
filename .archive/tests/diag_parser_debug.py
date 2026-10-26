from config.wizard import parse_natural_language_intent, COMMON_SYMBOLS
import re

tests = [
    "Aggressive GOLD#m M15 H1, 2% risk, $100 max loss",
    "Conservative EURUSD 1m, 0.5% position size, max loss $50",
    "Balanced BTCUSD 5m, 1%",
    "I want to trade gold on H1 and M15, balanced",
    "Use EURUSD#, daily, 2 percent, 200 dollars max loss",
]

for t in tests:
    print('---')
    print('INPUT:', t)
    lower = t.lower()
    print('lower:', lower)
    # common symbol matches
    matches = [s for s in sorted(COMMON_SYMBOLS, key=len, reverse=True) if s.lower() in lower]
    print('common symbol matches:', matches)
    # tokens
    tokens = re.findall(r"\b[\w#]+\b", t)
    print('tokens:', tokens)
    # timeframe patterns
    m1 = re.findall(r"(\d+)\s*(m|h|d|w|mn)\b", lower)
    m2 = re.findall(r"\b(m|h|d|w|mn)\s*(\d+)\b", lower)
    m3 = re.findall(r"\b([mh]\d+)\b", lower)
    print('tf matches (num+unit):', m1)
    print('tf matches (unit+num):', m2)
    print('tf matches (compact like m15):', m3)
    pct = re.search(r"(\d+(?:\.\d+)?)\s*(%|percent|pct)", lower)
    print('pct match:', pct.group(0) if pct else None)
    money = re.search(r"\$\s*(\d+(?:\.\d+)?)", lower) or re.search(r"max\s*loss\s*(?:is|of|:)??\s*(\d+(?:\.\d+)?)", lower)
    print('money match:', money.group(0) if money else None)
    print('parse_natural_language_intent:', parse_natural_language_intent(t))




