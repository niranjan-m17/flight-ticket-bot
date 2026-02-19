"""All Telegram Bot API communication."""
import httpx
import logging
from api.config import settings

logger = logging.getLogger(__name__)
BASE = settings.BOT_BASE


async def send_message(chat_id: int, text: str, parse_mode: str = "HTML") -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{BASE}/sendMessage", json={
            "chat_id": chat_id, "text": text, "parse_mode": parse_mode
        })
        return r.json()


async def send_document(chat_id: int, pdf_bytes: bytes, filename: str, caption: str = "") -> dict:
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(
            f"{BASE}/sendDocument",
            data={"chat_id": str(chat_id), "caption": caption, "parse_mode": "HTML"},
            files={"document": (filename, pdf_bytes, "application/pdf")},
        )
        return r.json()


async def send_action(chat_id: int, action: str = "typing"):
    async with httpx.AsyncClient(timeout=10) as c:
        await c.post(f"{BASE}/sendChatAction", json={"chat_id": chat_id, "action": action})


async def download_file(file_id: str) -> bytes:
    """Resolve file_id → download URL → raw bytes."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{BASE}/getFile", params={"file_id": file_id})
        r.raise_for_status()
        fp = r.json()["result"]["file_path"]
        file_url = f"{settings.TELEGRAM_API}/file/bot{settings.TELEGRAM_TOKEN}/{fp}"

    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(file_url)
        r.raise_for_status()
        return r.content


async def set_webhook(url: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{BASE}/setWebhook", json={
            "url": url,
            "allowed_updates": ["message"],
            "drop_pending_updates": True,
        })
        return r.json()
