"""Deterministic normalization for the fields present in the source datasets.

The source schema currently contains only ``business_name``,
``business_address``, and ``country``. Phone, email, website, city, state, and
postal-code normalizers are intentionally not defined because those are not
separate dataset fields.

Scalar functions are convenient for individual records. The corresponding
``*_series`` functions use pandas string operations and are intended for
large dataframe columns.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any


_REPEATED_WHITESPACE = re.compile(r"\s+")
_NAME_PUNCTUATION = re.compile(r"[^\w\s&]+", flags=re.UNICODE)
_FIELD_PUNCTUATION = re.compile(r"[^\w\s]+", flags=re.UNICODE)
_APOSTROPHES = re.compile(r"['’ʼ`]")


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        result = value != value  # NaN and pandas.NA are handled below.
        return bool(result)
    except (TypeError, ValueError):
        return False


def _base_text(value: Any) -> str:
    if _is_missing(value):
        return ""
    return unicodedata.normalize("NFKC", str(value)).casefold()


def _finish(value: str) -> str:
    return _REPEATED_WHITESPACE.sub(" ", value).strip()


def normalize_business_name(value: Any) -> str:
    """Normalize a business name without removing meaningful word content.

    Apostrophes are joined (``O'Reilly`` becomes ``oreilly``), while other
    punctuation becomes a separator. Ampersands are retained because they can
    be part of a company name.
    """
    text = _base_text(value)
    if not text:
        return ""
    text = _APOSTROPHES.sub("", text)
    return _finish(_NAME_PUNCTUATION.sub(" ", text))


def normalize_business_address(value: Any) -> str:
    """Normalize an address while retaining all alphanumeric tokens.

    Separators such as commas, slashes, periods, and hyphens become spaces;
    numeric unit, street, and postal tokens are never discarded.
    """
    text = _base_text(value)
    if not text:
        return ""
    return _finish(_FIELD_PUNCTUATION.sub(" ", text))


def normalize_country(value: Any) -> str:
    """Normalize the country field as case-folded Unicode words."""
    text = _base_text(value)
    if not text:
        return ""
    return _finish(_FIELD_PUNCTUATION.sub(" ", text))


def _normalize_series(series: Any, punctuation_pattern: str, join_apostrophes: bool = False) -> Any:
    """Apply normalization with pandas' vectorized string operations."""
    normalized = series.astype("string").fillna("").str.normalize("NFKC").str.casefold()
    if join_apostrophes:
        normalized = normalized.str.replace(_APOSTROPHES, "", regex=True)
    normalized = normalized.str.replace(punctuation_pattern, " ", regex=True)
    return normalized.str.replace(_REPEATED_WHITESPACE, " ", regex=True).str.strip()


def normalize_business_names(series: Any) -> Any:
    """Vectorized :func:`normalize_business_name` for a pandas Series."""
    return _normalize_series(series, _NAME_PUNCTUATION, join_apostrophes=True)


def normalize_business_addresses(series: Any) -> Any:
    """Vectorized :func:`normalize_business_address` for a pandas Series."""
    return _normalize_series(series, _FIELD_PUNCTUATION)


def normalize_countries(series: Any) -> Any:
    """Vectorized :func:`normalize_country` for a pandas Series."""
    return _normalize_series(series, _FIELD_PUNCTUATION)


__all__ = [
    "normalize_business_name",
    "normalize_business_address",
    "normalize_country",
    "normalize_business_names",
    "normalize_business_addresses",
    "normalize_countries",
]
