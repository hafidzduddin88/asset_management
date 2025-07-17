# app/utils/pagination.py
from typing import List, TypeVar, Generic, Sequence
from fastapi import Query
from pydantic import BaseModel
from pydantic.generics import GenericModel
import math

T = TypeVar("T")

class PaginationParams:
    """Pagination parameters."""
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(10, ge=1, le=100, description="Items per page")
    ):
        self.page = page
        self.page_size = page_size
        self.skip = (page - 1) * page_size

class PageInfo(BaseModel):
    """Pagination information."""
    total: int
    page: int
    page_size: int
    pages: int
    has_next: bool
    has_prev: bool

class Page(GenericModel, Generic[T]):
    """Paginated response."""
    items: List[T]
    page_info: PageInfo

def paginate(
    items: Sequence[T],
    pagination: PaginationParams
) -> Page[T]:
    """Paginate items."""
    total = len(items)
    pages = math.ceil(total / pagination.page_size) if total > 0 else 0
    
    start = pagination.skip
    end = start + pagination.page_size
    
    # Get items for current page
    page_items = items[start:end]
    
    # Create page info
    page_info = PageInfo(
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=pages,
        has_next=pagination.page < pages,
        has_prev=pagination.page > 1
    )
    
    return Page(items=page_items, page_info=page_info)