from dataclasses import dataclass
from typing import ClassVar


TIER_LIMITS: dict[str, int | None] = {
    "basic": 500,    # requests per day
    "pro": 5000,
    "unlimited": None,
}


@dataclass
class APIKey:
    id: int
    email: str
    key_hash: str
    tier: str
    active: bool
    created_at: str

    @property
    def daily_limit(self) -> int | None:
        return TIER_LIMITS.get(self.tier)
