"""Portable core primitives for the Lossless Context Handoff scripts.

This package intentionally depends only on the Python standard library.  It is a
small vendored implementation surface, not a general JSON or Markdown toolkit.
"""

from .canonicalize import (
    CanonicalizationError,
    DuplicateKeyError,
    IJSON_INTEGER_MAX,
    IJSON_INTEGER_MIN,
    UnsupportedNumberError,
    canonicalize,
    canonicalize_json,
    canonicalize_text,
    loads_strict,
    sha256_digest,
    sha256_hex,
)
from .projection import (
    ProjectionError,
    REVIEW_PROJECTION_VERSION,
    STATE_PROJECTION_VERSION,
    WARM_BOUNDARY_KEYS,
    WARM_KEYS,
    canonical_state_bytes,
    canonical_state_digest,
    canonical_state_digest_hex,
    review_projection_digest,
    review_projection_v1,
    state_projection_v1,
)

__all__ = [
    "CanonicalizationError",
    "DuplicateKeyError",
    "IJSON_INTEGER_MAX",
    "IJSON_INTEGER_MIN",
    "ProjectionError",
    "REVIEW_PROJECTION_VERSION",
    "STATE_PROJECTION_VERSION",
    "UnsupportedNumberError",
    "WARM_BOUNDARY_KEYS",
    "WARM_KEYS",
    "canonical_state_bytes",
    "canonical_state_digest",
    "canonical_state_digest_hex",
    "canonicalize",
    "canonicalize_json",
    "canonicalize_text",
    "loads_strict",
    "review_projection_digest",
    "review_projection_v1",
    "sha256_digest",
    "sha256_hex",
    "state_projection_v1",
]
