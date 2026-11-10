from datetime import datetime, timezone
from typing import Any

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

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
