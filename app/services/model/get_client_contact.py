from typing import List, Optional, Union

from pydantic import BaseModel


class GetClientContactDto(BaseModel):
    """Get client contact DTO."""

    max_id: Optional[int] = None
    phone: Optional[str] = None

    def dict(self, **kwargs):
        base_dict = super().dict(**kwargs)
        return {k: v for k, v in base_dict.items() if v is not None}


class ContactUpdate(BaseModel):
    id: Optional[str | int] = None
    holder_id: Optional[str | int] = None
    holder: Optional[str | int] = None
    max_id: Optional[Union[int, str]] = None
    is_max: Optional[bool] = None


class CategoryInfo(BaseModel):
    id: int
    title: str
    is_for_parents: bool
    is_for_kids: bool


class ContactInfo(BaseModel):
    id: int
    title: str
    telegram_id: Optional[str | int]
    max_id: Optional[str | int]
    phone: str | int
    is_main: bool
    holder: str
    holder_id: int
    is_telegram: bool
    is_whatsapp: bool
    is_max: bool
    is_child: bool
    active_categories: List[CategoryInfo]
