"""Format customer address parts for quote output."""
import re

_STREET_ABBREVS = {
    "rd": "Rd",
    "road": "Road",
    "st": "St",
    "street": "Street",
    "ave": "Ave",
    "avenue": "Avenue",
    "blvd": "Blvd",
    "dr": "Dr",
    "drive": "Drive",
    "ln": "Ln",
    "lane": "Lane",
    "ct": "Ct",
    "court": "Court",
    "hwy": "Hwy",
    "pkwy": "Pkwy",
    "pl": "Pl",
    "way": "Way",
    "cir": "Cir",
    "trl": "Trl",
    "loop": "Loop",
}
_DIRECTIONS = {"n", "s", "e", "w", "ne", "nw", "se", "sw"}


def _cap_word(word):
    if not word:
        return word
    return word[0].upper() + word[1:].lower()


def _format_word(word, street=False):
    base = word
    punct = ""
    while base and not base[-1].isalnum():
        punct = base[-1] + punct
        base = base[:-1]
    if not base:
        return word
    low = base.lower()
    if re.match(r"^\d", base):
        return word
    if street and low in _DIRECTIONS:
        return low.upper() + punct
    if street and low in _STREET_ABBREVS:
        return _STREET_ABBREVS[low] + punct
    if "-" in base:
        return "-".join(_cap_word(part) for part in base.split("-")) + punct
    return _cap_word(base) + punct


def format_street(text):
    text = (text or "").strip()
    if not text:
        return ""
    return " ".join(_format_word(word, street=True) for word in text.split())


def format_city(text):
    text = (text or "").strip()
    if not text:
        return ""
    return " ".join(_format_word(word) for word in text.split())


def format_state(text):
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) == 2 and text.isalpha():
        return text.upper()
    return format_city(text)


def format_zip(text):
    return (text or "").strip()


def format_country(text):
    text = (text or "").strip()
    if not text:
        return ""
    return format_city(text)


def format_legacy_address(text):
    """Best-effort formatting for older single-line address values."""
    text = (text or "").strip()
    if not text:
        return text
    if "," not in text:
        return format_street(text)
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) >= 3:
        state_zip = parts[-1].split()
        state = state_zip[0] if state_zip else ""
        zip_code = state_zip[1] if len(state_zip) > 1 else ""
        segments = [
            format_street(parts[0]),
            format_city(parts[1]),
            " ".join(part for part in (format_state(state), format_zip(zip_code)) if part),
        ]
        return ", ".join(segment for segment in segments if segment)
    return ", ".join(format_city(part) for part in parts)
