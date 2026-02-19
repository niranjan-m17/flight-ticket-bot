# ✈️ Flight Ticket Bot

A production-grade Telegram bot that accepts flight ticket screenshots or PDFs,
extracts all data using **GPT-4o Vision**, and replies with a clean structured **PDF**.

---

## Architecture

```
User (Telegram)
  │
  ├─ sends photos / PDF
  ▼
Telegram Servers
  │  webhook POST
  ▼
Vercel (FastAPI)  ←──── this repo
  │
  ├─ Supabase      (session: stores file_ids per user)
  ├─ OpenAI GPT-4o (vision OCR + structured extraction)
  └─ ReportLab     (PDF generation)
  │
  └─ sends PDF back to Telegram
```

---

## Deployment (Step by Step)

### Step 1 — Supabase Setup

1. Go to [supabase.com](https://supabase.com) → Your project → **SQL Editor**
2. Paste the contents of `supabase_setup.sql` and click **Run**
3. Go to **Settings → API** and copy:
   - `Project URL`  → this is your `SUPABASE_URL`
   - `service_role` key (not anon!) → this is your `SUPABASE_SERVICE_KEY`

### Step 2 — Push to GitHub

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/flight-ticket-bot.git
git push -u origin main
```

### Step 3 — Deploy to Vercel

1. Go to [vercel.com](https://vercel.com) → **New Project**
2. Import your GitHub repo
3. **Framework Preset**: leave as "Other"
4. Click **Deploy** (first deploy will fail — that's expected, env vars not set yet)

### Step 4 — Add Environment Variables in Vercel

Go to your project → **Settings → Environment Variables** and add:

| Variable | Value |
|----------|-------|
| `TELEGRAM_TOKEN` | Your bot token from [@BotFather](https://t.me/BotFather) |
| `OPENAI_API_KEY` | `sk-...` from [platform.openai.com](https://platform.openai.com) |
| `SUPABASE_URL` | `https://xxxx.supabase.co` |
| `SUPABASE_SERVICE_KEY` | service_role key from Supabase |
| `AGENCY_NAME` | `Exile Automate` (or your name) |
| `OPENAI_MODEL` | `gpt-4o` |

### Step 5 — Redeploy

Vercel Dashboard → **Deployments → Redeploy** (with new env vars)

### Step 6 — Register Telegram Webhook

Once deployed, visit this URL in your browser once:

```
https://YOUR-PROJECT.vercel.app/api/setup
```

You should see:
```json
{"status": "ok", "webhook_url": "https://...", "telegram_response": {"ok": true}}
```

### Step 7 — Test!

Open Telegram → your bot → send `/start`

---

## How to Use the Bot

```
User: /start
Bot: Welcome! Send flight ticket images or PDF, then type /analyze

User: [sends 3 screenshots of flight ticket]
Bot: ✅ File 1 received
Bot: ✅ File 2 received
Bot: ✅ File 3 received

User: /analyze
Bot: ⏳ Processing 3 files... (15-30 seconds)
Bot: [sends PDF] ✈️ Flight Ticket Summary
```

---

## File Structure

```
flight-ticket-bot/
├── api/
│   ├── index.py        ← FastAPI app (Vercel entry point + webhook handler)
│   ├── config.py       ← Settings from environment variables
│   ├── telegram.py     ← Telegram Bot API wrapper
│   ├── session.py      ← Supabase session management
│   ├── extractor.py    ← GPT-4o Vision OCR + structured extraction
│   └── pdf_gen.py      ← ReportLab PDF generation
├── vercel.json         ← Vercel deployment config
├── requirements.txt    ← Python dependencies
├── supabase_setup.sql  ← Run once in Supabase SQL Editor
├── .env.example        ← Copy env vars to Vercel dashboard
└── .gitignore
```

---

## Supported Input Formats

| Format | How to send | Notes |
|--------|------------|-------|
| Screenshots | Send as photo (camera icon) | Best quality |
| Images | Send as photo | JPG, PNG, WEBP |
| PDF | Send as document (paperclip icon) | Scanned or digital |

**Tips for best results:**
- Send screenshots from the booking confirmation email
- If the PDF has multiple pages, send the whole PDF — all pages are processed
- Route, times, baggage, price can each be in separate screenshots — bot combines them all

---

## How It Works Internally

1. **File received** → stored as `{file_id, type}` in Supabase session
2. `/analyze` triggered:
   - Downloads all files from Telegram servers
   - PDFs → each page rendered to PNG at 144 DPI (PyMuPDF, no poppler needed)
   - All images batched into **one GPT-4o Vision call**
   - GPT-4o cross-references all images and returns structured JSON
3. JSON → ReportLab → beautiful branded PDF
4. PDF sent back via Telegram

---

## Vercel Plan Requirements

- **Hobby** (free): 10s function timeout — **may timeout on large PDFs or 5+ images**
- **Pro** ($20/mo): 60s timeout — ✅ Recommended for production

---

## Adding Features Later

The code is modular — easy to extend:

- **Multi-language support** → update the GPT-4o prompt in `extractor.py`
- **Google Drive upload** → add after `generate_pdf()` in `index.py`
- **WhatsApp support** → add a new `/api/whatsapp` webhook route
- **Database logging** → add a `logs` table to Supabase and write ticket data there
- **Admin dashboard** → query the `sessions` table from a separate frontend
