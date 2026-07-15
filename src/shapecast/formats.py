"""String format detection for JSON Schema ``format`` annotations.

Each detector is a pure predicate ``str -> bool`` implemented with the
standard library (``ipaddress``, ``uuid``, ``datetime``) plus tight regular
expressions, so detection is deterministic and offline. shapecast only ever
*claims* a format in the emitted schema when **every** string sample of a
field matched it — a format is evidence-backed, never a guess from one value.

Detectors are ordered most-specific first in :data:`FORMAT_PRIORITY`; when a
field's samples all match several formats (a UUID is also never an email, but
a ``date`` is a prefix-shaped cousin of ``date-time`` inputs), the schema
layer picks the highest-priority one.
"""

from __future__ import annotations

import ipaddress
import re
import uuid
from datetime import date, datetime
from typing import Callable, Dict, List, Tuple

# Matches the canonical 8-4-4-4-12 hex form only; uuid.UUID() alone is far
# too permissive (it accepts braces, URNs and bare 32-hex strings).
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# RFC 3339 date-time: full date, 'T' (or space, seen constantly in logs is NOT
# accepted — RFC 3339 wants T/t), full time, mandatory offset ('Z' or +hh:mm).
_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)

_TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})?$")

# Pragmatic email shape: local part without spaces/@, dotted domain with a TLD.
_EMAIL_RE = re.compile(r"^[^@\s]+@[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$")

# URI with an explicit scheme and no whitespace. Deliberately requires "://"
# so bare words and Windows paths ("C:\x") are not misread as URIs.
_URI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://\S+$")


def is_uuid(value: str) -> bool:
    """Canonical hyphenated UUID (any version)."""
    if not _UUID_RE.match(value):
        return False
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def is_date_time(value: str) -> bool:
    """RFC 3339 date-time with a mandatory offset, validated field-by-field."""
    if not _DATETIME_RE.match(value):
        return False
    try:
        # fromisoformat on 3.9/3.10 rejects 'Z'; normalize before validating.
        datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
        return True
    except ValueError:
        return False


def is_date(value: str) -> bool:
    """Full-date ``YYYY-MM-DD`` with real calendar validation."""
    if len(value) != 10:
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def is_time(value: str) -> bool:
    """RFC 3339 partial/full time, e.g. ``14:05:00`` or ``14:05:00+09:00``."""
    match = _TIME_RE.match(value)
    if not match:
        return False
    hour = int(value[0:2])
    minute = int(value[3:5])
    second = int(value[6:8])
    if hour > 23 or minute > 59 or second > 59:
        return False
    offset = match.group(2)
    if offset and offset not in ("Z", "z"):
        offset_hour = int(offset[1:3])
        offset_minute = int(offset[4:6])
        if offset_hour > 23 or offset_minute > 59:
            return False
    return True


def is_email(value: str) -> bool:
    """Pragmatic email shape (local@dotted.domain); not full RFC 5322."""
    return bool(_EMAIL_RE.match(value)) and len(value) <= 254


def is_ipv4(value: str) -> bool:
    """Dotted-quad IPv4 address (``127.0.0.1``)."""
    try:
        ipaddress.IPv4Address(value)
        return True
    except ValueError:
        return False


def is_ipv6(value: str) -> bool:
    """IPv6 address; requires a colon so IPv4 strings never match."""
    if ":" not in value:
        return False
    try:
        ipaddress.IPv6Address(value)
        return True
    except ValueError:
        return False


def is_uri(value: str) -> bool:
    """URI with an explicit ``scheme://`` and no whitespace."""
    return bool(_URI_RE.match(value)) and len(value) <= 2048


#: Detection order, most specific first. The schema layer reports the first
#: format in this list that matched 100% of a field's string samples.
FORMAT_PRIORITY: List[str] = [
    "uuid",
    "date-time",
    "date",
    "time",
    "ipv4",
    "ipv6",
    "email",
    "uri",
]

_DETECTORS: Dict[str, Callable[[str], bool]] = {
    "uuid": is_uuid,
    "date-time": is_date_time,
    "date": is_date,
    "time": is_time,
    "ipv4": is_ipv4,
    "ipv6": is_ipv6,
    "email": is_email,
    "uri": is_uri,
}


def detect_formats(value: str) -> Tuple[str, ...]:
    """Return every format name the string matches, in priority order.

    The empty string matches nothing by definition — an empty value is not
    evidence for any format, and treating it as a wildcard would let a field
    of mostly-empty strings claim a format from a single real sample.
    """
    if not value:
        return ()
    return tuple(name for name in FORMAT_PRIORITY if _DETECTORS[name](value))
