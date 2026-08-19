"""TrustOffice UTM / Referral Tracking package.

Exports:
    utm_tracker  – Core attribution logic
"""
from .utm_tracker import (
    clean_utm,
    resolve_signup_source,
    resolve_signup_source_from_payload,
    extract_utm_params,
    record_signup_attribution,
    build_checkout_metadata,
    get_attribution_summary,
)

__all__ = [
    "clean_utm",
    "resolve_signup_source",
    "resolve_signup_source_from_payload",
    "extract_utm_params",
    "record_signup_attribution",
    "build_checkout_metadata",
    "get_attribution_summary",
]
