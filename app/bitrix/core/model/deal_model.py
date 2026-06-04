from enum import Enum

from pydantic import BaseModel, Field


class DealCategory(int, Enum):

    DEFAULT = 0


class BxUserFields(str, Enum):
    deal_link_to_lms = "UF_CRM_"
    deal_source_creation = "UF_CRM_"
    deal_courses = "UF_CRM_"


class DealFields(BaseModel):
    """Модель сделки"""

    title: str = Field(..., alias="TITLE", description="Название сделки")
    contact_id: int = Field(..., alias="CONTACT_ID", description="ID контакта")
    assigned_by_id: int = Field(..., alias="ASSIGNED_BY_ID", description="ID ответственного")
    category_id: DealCategory = Field(default=DealCategory.DEFAULT, alias="CATEGORY_ID")
    source_id: str = Field(default="", alias="SOURCE_ID", description="Источник")
    courses: str = Field(..., alias=BxUserFields.deal_courses.value)
    link_to_lms: str = Field(..., alias=BxUserFields.deal_link_to_lms.value)

    class Config:
        populate_by_name = True
        use_enum_values = True


class DealData(BaseModel):
    """Модель данных для создания сделки"""

    fields: DealFields

    @classmethod
    def from_customer_data(cls, lms_customer: dict, customer: int, course: str, lms_link: str, manager_id: int):
        return cls(
            fields=DealFields(
                title=lms_customer["raw_name"],
                contact_id=lms_customer.get("bitrix_contact_id", customer),
                assigned_by_id=manager_id,
                courses=course,
                link_to_lms=lms_link,
            )
        )

    def to_bitrix_format(self) -> dict:
        return dict(fields=self.fields.model_dump(by_alias=True, exclude_none=True))
