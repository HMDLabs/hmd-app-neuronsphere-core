"""Offset/limit pagination envelope shared by the GUI views and the MCP tools.

Extracted from the two byte-identical inline blocks in ``views.py``
(``api_repo_class_versions_options`` and ``resource_list``). Pure -- no Django
or request state; callers pass an already-parsed ``page``/``offset``.
"""


def parse_page(raw, default: int = 1) -> int:
    """Parse a ``?page=`` value into a 1-based page number, never below 1.

    Mirrors the guard used at every call site: a missing, empty, or
    non-integer value falls back to ``default`` rather than raising.
    """
    try:
        return max(int(raw or default), 1)
    except (TypeError, ValueError):
        return default


def offset_for_page(page: int, limit: int) -> int:
    """Convert a 1-based page number into a 0-based offset."""
    return (max(page, 1) - 1) * limit


def build_pagination(total, limit: int, offset: int, page: int = None) -> dict:
    """Build the pagination context dict consumed by the list templates.

    ``page`` is derived from ``offset``/``limit`` when not supplied, so callers
    that page by offset (the MCP tools) and callers that page by page number
    (the GUI views) produce the same envelope.
    """
    total = int(total or 0)
    num_pages = max((total + limit - 1) // limit, 1) if limit else 1
    if page is None:
        page = (offset // limit + 1) if limit else 1
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "page": page,
        "num_pages": num_pages,
        "has_prev": page > 1,
        "has_next": page < num_pages,
        "start": offset + 1 if total else 0,
        "end": min(offset + limit, total),
    }
