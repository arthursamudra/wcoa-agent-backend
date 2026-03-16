from fastapi import APIRouter
from app.db.session import db_ping

router = APIRouter()

@router.get("/health")
async def health():
    ok = await db_ping()
    return {"status": "ok", "db": ok}
