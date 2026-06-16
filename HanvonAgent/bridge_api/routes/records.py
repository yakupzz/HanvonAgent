"""BridgeApi records endpoints."""

from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter(prefix="/api/records", tags=["records"])


@router.get("/")
async def list_records(
    date: Optional[str] = Query(None),
    push_status: Optional[str] = Query(None),
):
    """Kayıtları listele."""
    return {"message": "Records endpoint"}


@router.get("/{date}")
async def get_records_by_date(date: str):
    """Tarih bazlı kayıtlar."""
    return {"date": date}
