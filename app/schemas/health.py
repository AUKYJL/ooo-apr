"""Response schemas for health endpoints."""

from pydantic import BaseModel


class LiveResponse(BaseModel):
    """Process liveness result."""

    status: str


class ReadyResponse(BaseModel):
    """Dependency readiness result."""

    status: str
    components: dict[str, str]
