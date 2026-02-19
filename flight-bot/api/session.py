"""
Session Manager – Supabase REST API.

Table schema (run in Supabase SQL Editor):

  create table sessions (
    id          uuid default gen_random_uuid() primary key,
    user_id     bigint not null,
    chat_id     bigint not null,
    files       jsonb  default '[]'::jsonb,
    status      text   default 'collecting',
    created_at  timestamptz default now(),
    updated_at  timestamptz default now()
  );

  create index on sessions(user_id, status);
"""
import json, logging
from datetime import datetime
import httpx
from api.config import settings

logger = logging.getLogger(__name__)

URL   = f"{settings.SUPABASE_URL}/rest/v1/sessions"
HDR   = {
    "apikey":        settings.SUPABASE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=representation",
}


def _parse(session: dict) -> dict:
    if isinstance(session.get("files"), str):
        session["files"] = json.loads(session["files"])
    return session


async def get_active(user_id: int) -> dict | None:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(URL, headers=HDR, params={
            "user_id": f"eq.{user_id}",
            "status":  "eq.collecting",
            "order":   "created_at.desc",
            "limit":   "1",
        })
        data = r.json()
        return _parse(data[0]) if isinstance(data, list) and data else None


async def create(user_id: int, chat_id: int) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(URL, headers=HDR, json={
            "user_id": user_id, "chat_id": chat_id, "files": [], "status": "collecting"
        })
        data = r.json()
        return _parse(data[0] if isinstance(data, list) else data)


async def add_file(session_id: str, file_info: dict) -> dict:
    """Append a file dict to the session's files array."""
    async with httpx.AsyncClient(timeout=10) as c:
        # Fetch current files
        r = await c.get(f"{URL}?id=eq.{session_id}", headers=HDR)
        current = r.json()[0]
        files = current["files"] if isinstance(current["files"], list) else json.loads(current["files"])
        files.append(file_info)
        # Patch
        r2 = await c.patch(f"{URL}?id=eq.{session_id}", headers=HDR, json={
            "files": files, "updated_at": datetime.utcnow().isoformat()
        })
        data = r2.json()
        return _parse(data[0] if isinstance(data, list) else data)


async def set_status(session_id: str, status: str):
    async with httpx.AsyncClient(timeout=10) as c:
        await c.patch(f"{URL}?id=eq.{session_id}", headers=HDR, json={
            "status": status, "updated_at": datetime.utcnow().isoformat()
        })


async def get_or_create(user_id: int, chat_id: int) -> dict:
    s = await get_active(user_id)
    return s if s else await create(user_id, chat_id)


async def abandon_all(user_id: int):
    """Mark all collecting sessions as abandoned (fresh start)."""
    async with httpx.AsyncClient(timeout=10) as c:
        await c.patch(URL, headers={**HDR, "Prefer": ""}, params={
            "user_id": f"eq.{user_id}", "status": "eq.collecting"
        }, json={"status": "abandoned"})
