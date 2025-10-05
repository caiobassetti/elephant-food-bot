import re

_COMMON_TYPO_FIXES = {
    "avocato": "avocado",
    "humus": "hummus",
    "bolonese": "bolognese",
    "omlette": "omelette",
    "margharita": "margherita",
}

_MULTI_SPACE = re.compile(r"\s+")
_NON_WORD_EDGES = re.compile(r"^[^a-z0-9]+|[^a-z0-9]+$", re.IGNORECASE)

# Normalize with lowercase, strip, collapse spaces, typo fixes.
def normalize_food_name(name):
    original = name or ""
    s = original.strip().lower()
    s = _NON_WORD_EDGES.sub("", s)
    s = _MULTI_SPACE.sub(" ", s)

    # Typo fixes on word tokens
    tokens = [ _COMMON_TYPO_FIXES.get(tok, tok) for tok in s.split(" ") if tok ]
    fixed = " ".join(tokens)

    return fixed
