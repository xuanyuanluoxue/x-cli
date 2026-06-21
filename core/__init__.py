"""x-cli core: data models and file storage primitives.

This package is intentionally stdlib-only (no PyYAML, no third-party deps).
The frontmatter parser in :mod:`core.parser` is hand-written to keep the
dependency surface small and to guarantee that unknown fields round-trip
without being silently dropped.
"""

from __future__ import annotations
