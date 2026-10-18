"""Normalize assistant text for TTS without changing the on-screen response."""
import html
import re

_EMOJI_RE = re.compile("[" "\U0001F1E0-\U0001F1FF" "\U0001F300-\U0001FAFF" "\U00002600-\U000027BF" "\uFE0F\u200d" "]+", re.UNICODE)
_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_TEENS = ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty"]

def _words(n: int) -> str:
    if n < 10: return _ONES[n]
    if n < 20: return _TEENS[n - 10]
    if n < 60: return _TENS[n // 10] + (f" {_ONES[n % 10]}" if n % 10 else "")
    return str(n)

def _say_time(match: re.Match) -> str:
    hour, minute = int(match.group("hour")), int(match.group("minute"))
    suffix = (match.group("suffix") or "").replace(".", "").upper()
    if suffix:
        if minute == 0 and hour == 12 and suffix == "PM":
            return "noon"
        if minute == 0 and hour == 12 and suffix == "AM":
            return "midnight"
        spoken_hour = hour % 12 or 12
        period = suffix
    else:
        if hour > 23 or minute > 59: return match.group(0)
        if hour == 0 and minute == 0: return "midnight"
        if hour == 12 and minute == 0: return "noon"
        spoken_hour = hour % 12 or 12
        period = "PM" if hour >= 12 else "AM"
    if minute == 0:
        spoken = _words(spoken_hour) + (" o'clock" if not suffix else "")
    elif minute < 10:
        spoken = f"{_words(spoken_hour)} oh {_words(minute)}"
    else:
        spoken = f"{_words(spoken_hour)} {_words(minute)}"
    return f"{spoken} {period}".strip()

_TIME_RE = re.compile(r"(?<!\d)(?P<hour>\d{1,2}):(?P<minute>\d{2})(?:\s*(?P<suffix>a\.?m\.?|p\.?m\.?))?(?!\d)", re.I)

def clean_for_speech(text: str) -> str:
    """Strip formatting and normalize common times for speech synthesis."""
    if not text: return ""
    value = html.unescape(str(text))
    value = re.sub(r"```.*?```", " ", value, flags=re.S)
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", value)
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"^\s{0,3}#{1,6}\s*", "", value, flags=re.M)
    value = re.sub(r"^\s*>\s?", "", value, flags=re.M)
    value = re.sub(r"^\s*[-*+]\s+|^\s*\d+[.)]\s+", "", value, flags=re.M)
    value = re.sub(r"(\*\*|__)(.*?)\1", r"\2", value)
    value = re.sub(r"(?<!\w)([*_~])([^*_~]+)\1(?!\w)", r"\2", value)
    value = re.sub(r"(?m)^\s*[-*_]{3,}\s*$", " ", value)
    value = _EMOJI_RE.sub(" ", value)
    value = _TIME_RE.sub(_say_time, value)
    value = value.replace("&", " and ")
    value = re.sub(r"[|*`#<>{}\[\]\\]+", " ", value)
    value = re.sub(r"\s*[:;]\s*", ", ", value)
    value = re.sub(r"\s+[—–-]\s+", ". ", value)
    value = re.sub(r"([!?.,])\1+", r"\1", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{2,}", ". ", value)
    value = re.sub(r"\s*\n\s*", ". ", value)
    value = re.sub(r"\.\s*\.", ".", value)
    return value.strip(" .\n\t")
