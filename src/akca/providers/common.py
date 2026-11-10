from datetime import UTC, datetime
from typing import Any

def utc_now() -> str:
    return datetime.now(UTC).isoformat()

def source_record(
    source_id: str,
    source_name: str,
    category: str,
    access: str,
    status: str,
    url: str,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_name": source_name,
        "category": category,
        "access": access,
        "status": status,
        "url": url,
        "retrieved_at": utc_now(),
        "limitations": limitations or [],
    }
