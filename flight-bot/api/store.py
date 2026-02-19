"""
Session Store - Vercel KV (Upstash Redis)
Stores collected file_ids per chat_id until user sends /done.

Environment Variables (auto-provided by Vercel KV):
  KV_REST_API_URL
  KV_REST_API_TOKEN
"""

import os
import json
import logging
import httpx

logger = logging.getLogger(__name__)

SESSION_TTL = 3600  # 1 hour — auto-expire sessions


class SessionStore:
    def __init__(self):
        self.kv_url = os.environ.get("KV_REST_API_URL", "")
        self.kv_token = os.environ.get("KV_REST_API_TOKEN", "")
        self.enabled = bool(self.kv_url and self.kv_token)

        if not self.enabled:
            logger.warning("KV store not configured — using in-memory fallback (single instance only)")
            self._memory: dict = {}

    def _headers(self):
        return {"Authorization": f"Bearer {self.kv_token}"}

    def _key(self, chat_id: int) -> str:
        return f"session:{chat_id}:files"

    # ── KV Operations ─────────────────────────────────────────────────────────

    async def get_files(self, chat_id: int) -> list:
        if not self.enabled:
            return self._memory.get(str(chat_id), [])

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{self.kv_url}/get/{self._key(chat_id)}",
                    headers=self._headers()
                )
                data = r.json()
                result = data.get("result")
                if result:
                    return json.loads(result)
        except Exception as e:
            logger.error(f"KV get error: {e}")
        return []

    async def add_file(self, chat_id: int, file_info: dict):
        files = await self.get_files(chat_id)
        files.append(file_info)
        await self._save(chat_id, files)

    async def clear_session(self, chat_id: int):
        if not self.enabled:
            self._memory.pop(str(chat_id), None)
            return

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.get(
                    f"{self.kv_url}/del/{self._key(chat_id)}",
                    headers=self._headers()
                )
        except Exception as e:
            logger.error(f"KV delete error: {e}")

    async def _save(self, chat_id: int, files: list):
        if not self.enabled:
            self._memory[str(chat_id)] = files
            return

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.get(
                    f"{self.kv_url}/set/{self._key(chat_id)}/{json.dumps(files)}",
                    headers=self._headers(),
                    params={"ex": SESSION_TTL}
                )
        except Exception as e:
            logger.error(f"KV set error: {e}")
