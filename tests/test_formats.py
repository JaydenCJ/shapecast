"""Format detectors: strict, stdlib-validated, and empty-string-proof.

Every detector doubles as a schema keyword claim, so false positives here
become lies in emitted schemas — the negative cases matter most.
"""

from __future__ import annotations

from shapecast.formats import (
    FORMAT_PRIORITY,
    detect_formats,
    is_date,
    is_date_time,
    is_email,
    is_ipv4,
    is_ipv6,
    is_time,
    is_uri,
    is_uuid,
)


def test_uuid_accepts_canonical_hyphenated_form_any_case():
    assert is_uuid("5f2c1a8e-8d1b-4d6a-9c3e-2b7f0a1d4e90")
    assert is_uuid("5F2C1A8E-8D1B-4D6A-9C3E-2B7F0A1D4E90")


def test_uuid_rejects_braces_urn_and_bare_hex():
    # uuid.UUID() accepts all three of these; the detector must not, because
    # a schema claiming format uuid promises the canonical wire form.
    assert not is_uuid("{5f2c1a8e-8d1b-4d6a-9c3e-2b7f0a1d4e90}")
    assert not is_uuid("urn:uuid:5f2c1a8e-8d1b-4d6a-9c3e-2b7f0a1d4e90")
    assert not is_uuid("5f2c1a8e8d1b4d6a9c3e2b7f0a1d4e90")


def test_date_time_accepts_rfc3339_with_z_or_numeric_offset():
    assert is_date_time("2026-06-01T09:12:33Z")
    assert is_date_time("2026-06-01T09:12:33.250+09:00")
    assert is_date_time("2026-06-01t09:12:33z")  # RFC 3339 allows lowercase


def test_date_time_rejects_missing_offset_and_space_separator():
    assert not is_date_time("2026-06-01T09:12:33")  # no offset: ambiguous
    assert not is_date_time("2026-06-01 09:12:33Z")  # space is not RFC 3339


def test_date_time_rejects_impossible_calendar_dates():
    assert not is_date_time("2026-02-30T00:00:00Z")
    assert not is_date_time("2026-13-01T00:00:00Z")


def test_date_accepts_iso_full_date_and_validates_the_calendar():
    assert is_date("2026-06-01")
    assert not is_date("2026-02-30")
    assert not is_date("2026-6-01")  # must be zero-padded, length 10


def test_time_accepts_partial_time_with_optional_fraction_and_offset():
    assert is_time("09:12:33")
    assert is_time("09:12:33.5+09:00")
    assert not is_time("24:00:00")
    assert not is_time("09:12")


def test_email_requires_dotted_domain_and_no_whitespace():
    assert is_email("ana@example.test")
    assert is_email("a.b+tag@mail.example.test")
    assert not is_email("ana@localhost")  # no TLD
    assert not is_email("ana bo@example.test")
    assert not is_email("@example.test")


def test_ipv4_and_ipv6_do_not_overlap():
    assert is_ipv4("127.0.0.1")
    assert not is_ipv4("256.1.1.1")
    assert is_ipv6("::1")
    assert is_ipv6("2001:db8::8a2e:370:7334")
    # ipaddress.IPv6Address never parses dotted quads, but the explicit colon
    # guard documents the invariant the schema layer relies on.
    assert not is_ipv6("127.0.0.1")


def test_uri_requires_explicit_scheme_and_rejects_paths_and_spaces():
    assert is_uri("https://example.test/v1/orders?page=2")
    assert is_uri("ftp://127.0.0.1/file.bin")
    assert not is_uri("example.test/orders")
    assert not is_uri("/var/lib/data.json")
    assert not is_uri("https://example.test/a b")


def test_detect_formats_returns_matches_in_priority_order():
    assert detect_formats("5f2c1a8e-8d1b-4d6a-9c3e-2b7f0a1d4e90") == ("uuid",)
    assert detect_formats("2026-06-01") == ("date",)
    assert detect_formats("not a format") == ()
    # Priority list and detector table must stay in sync.
    assert list(FORMAT_PRIORITY)[:2] == ["uuid", "date-time"]
    # An empty string is not evidence for any format; if it matched, a field
    # of mostly-empty strings could claim a format from one real sample.
    assert detect_formats("") == ()
