import os

class Settings:
    TELEGRAM_TOKEN: str   = os.environ["TELEGRAM_TOKEN"]
    TELEGRAM_API: str     = "https://api.telegram.org"
    OPENAI_API_KEY: str   = os.environ["OPENAI_API_KEY"]
    OPENAI_MODEL: str     = os.getenv("OPENAI_MODEL", "gpt-4o")
    SUPABASE_URL: str     = os.environ["SUPABASE_URL"]
    SUPABASE_KEY: str     = os.environ["SUPABASE_SERVICE_KEY"]
    AGENCY_NAME: str      = os.getenv("AGENCY_NAME", "Exile Automate")
    VERCEL_URL: str       = os.getenv("VERCEL_URL", "")

    @property
    def BOT_BASE(self) -> str:
        return f"{self.TELEGRAM_API}/bot{self.TELEGRAM_TOKEN}"

    @property
    def WEBHOOK_URL(self) -> str:
        base = self.VERCEL_URL
        if not base.startswith("http"):
            base = f"https://{base}"
        return f"{base}/api/webhook"

settings = Settings()
