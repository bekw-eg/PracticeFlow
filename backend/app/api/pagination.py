from typing import Annotated

from fastapi import Query, Response


PAGINATION_RESPONSE_HEADERS = (
    "X-Total-Count",
    "X-Has-More",
    "X-Offset",
    "X-Limit",
)


class PaginationParams:
    """Bounded offset pagination while preserving existing list response shapes."""

    def __init__(
        self,
        offset: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
        limit: Annotated[int, Query(ge=1, le=200, description="Maximum records to return")] = 50,
    ) -> None:
        self.offset = offset
        self.limit = limit


def set_pagination_headers(response: Response, page: PaginationParams, *, total: int, returned: int) -> None:
    """Attach page metadata without changing established array responses.

    The public API has historically returned a JSON array for every collection.
    Keeping that body intact lets existing clients upgrade incrementally while new
    clients can use these headers to render a bounded, accessible paginator.
    """
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Has-More"] = "true" if page.offset + returned < total else "false"
    response.headers["X-Offset"] = str(page.offset)
    response.headers["X-Limit"] = str(page.limit)
