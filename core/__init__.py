"""x-cli core: data models and file storage primitives.

This package is intentionally **stdlib-only** (no PyYAML, no pypinyin,
no third-party deps). The frontmatter parser in :mod:`core.parser` and
the slug generator in :mod:`core.slug` are both hand-written to keep
the dependency surface small and to guarantee that unknown fields
round-trip without being silently dropped.
"""

from __future__ import annotations
