from pydantic import BaseModel


class Rate(BaseModel):
    bank: str
    type: str
    product: str
    rate: str
    details: str | None = None
    scraped_at: str
