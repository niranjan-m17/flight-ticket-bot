"""
Main FastAPI Application — Vercel Entry Point.

Telegram Bot Webhook → Handles all messages:
  /start    — Welcome message
  /new      — Abandon current session, start fresh
  /analyze  — Process all collected files and return PDF
  Photo     — Add image to session
  Document  — Add PDF to session (scanned/digital both handled)

Deploy: set up webhook by visiting  GET /api/setup
"""
import logging
import sys
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

# Configure logging early
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Flight Ticket Bot API", version="1.0.0")


# ── Webhook ───────────────────────────────────────────────────────────────────

@app.post("/api/webhook")
async def webhook(request: Request):
    """Receive all Telegram updates."""
    try:
        update = await request.json()
    except Exception:
        return Response(status_code=200)   # Always 200 to Telegram

    try:
        await handle_update(update)
    except Exception as e:
        logger.exception(f"Unhandled error in update handler: {e}")

    return Response(status_code=200)   # Must always return 200 to Telegram


# ── Update Router ─────────────────────────────────────────────────────────────

async def handle_update(update: dict):
    msg = update.get("message")
    if not msg:
        return

    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    text    = msg.get("text", "")

    # ── Commands ──────────────────────────────────────────────
    if text.startswith("/start"):
        await handle_start(chat_id)

    elif text.startswith("/new"):
        await handle_new(chat_id, user_id)

    elif text.startswith("/analyze"):
        await handle_analyze(chat_id, user_id)

    # ── Photo (screenshot / image) ────────────────────────────
    elif msg.get("photo"):
        # Telegram sends multiple resolutions — take the largest
        photo = max(msg["photo"], key=lambda p: p.get("file_size", 0))
        await handle_file(chat_id, user_id, photo["file_id"], "image", "photo.jpg")

    # ── Document (PDF or image sent as file) ──────────────────
    elif msg.get("document"):
        doc  = msg["document"]
        mime = doc.get("mime_type", "")
        name = doc.get("file_name", "file")

        if "pdf" in mime:
            ftype = "pdf"
        elif mime.startswith("image/"):
            ftype = "image"
        else:
            await send_unsupported(chat_id)
            return

        await handle_file(chat_id, user_id, doc["file_id"], ftype, name)

    else:
        # Unknown text / message type
        await send_hint(chat_id)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_start(chat_id: int):
    from api.telegram import send_message
    await send_message(chat_id, (
        "👋 <b>Welcome to the Flight Ticket Bot!</b>\n\n"
        "Here's how to use me:\n\n"
        "1️⃣  Send me <b>photos</b> or <b>PDF</b> of your flight ticket\n"
        "   (screenshots are fine — send as many as you need)\n\n"
        "2️⃣  Type <b>/analyze</b> when you're done uploading\n\n"
        "3️⃣  I'll send back a clean, structured PDF ✈️\n\n"
        "<b>Commands:</b>\n"
        "/analyze — Process uploaded files &amp; generate PDF\n"
        "/new     — Clear current files and start fresh\n"
        "/start   — Show this message"
    ))


async def handle_new(chat_id: int, user_id: int):
    from api.telegram import send_message
    import api.session as session
    await session.abandon_all(user_id)
    await send_message(chat_id,
        "🔄 Session cleared! Send your flight ticket images or PDF and type /analyze when ready.")


async def handle_file(chat_id: int, user_id: int, file_id: str, ftype: str, fname: str):
    from api.telegram import send_message, send_action
    import api.session as session

    await send_action(chat_id, "typing")

    try:
        sess = await session.get_or_create(user_id, chat_id)
        file_count = len(sess.get("files", []))

        if file_count >= 15:
            await send_message(chat_id,
                "⚠️ Maximum 15 files per session. Type /analyze to process what you have, or /new to start fresh.")
            return

        await session.add_file(sess["id"], {
            "file_id": file_id,
            "type": ftype,
            "name": fname,
        })

        new_count = file_count + 1
        await send_message(chat_id,
            f"✅ <b>File {new_count} received</b>  ({fname})\n\n"
            f"Send more files or type /analyze to generate your ticket PDF.")

    except Exception as e:
        logger.error(f"Error saving file for user {user_id}: {e}")
        await send_message(chat_id,
            "❌ Something went wrong saving your file. Please try again.")


async def handle_analyze(chat_id: int, user_id: int):
    from api.telegram import send_message, send_action, send_document, download_file
    from api.extractor import extract_flight_data, file_to_images
    from api.pdf_gen import generate_pdf
    import api.session as session

    # Check session has files
    sess = await session.get_active(user_id)

    if not sess or not sess.get("files"):
        await send_message(chat_id,
            "📂 No files found! Please send your flight ticket images or PDF first, then type /analyze.")
        return

    files = sess["files"]
    logger.info(f"Analyzing {len(files)} file(s) for user {user_id}")

    # ── Step 1: Notify user ───────────────────────────────────
    await send_message(chat_id,
        f"⏳ Processing <b>{len(files)} file(s)</b>...\n"
        "Extracting text with AI Vision — this takes 15–30 seconds.")
    await send_action(chat_id, "upload_document")

    # ── Step 2: Mark session as processing ───────────────────
    await session.set_status(sess["id"], "processing")

    try:
        # ── Step 3: Download all files & convert to images ───
        all_images = []
        for f in files:
            try:
                raw = await download_file(f["file_id"])
                imgs = file_to_images(raw, f["type"])
                all_images.extend(imgs)
                logger.info(f"  {f['name']}: {len(imgs)} image(s)")
            except Exception as e:
                logger.warning(f"Failed to process file {f['name']}: {e}")
                continue

        if not all_images:
            await send_message(chat_id,
                "❌ Could not read any of the uploaded files. Please try uploading again.")
            await session.set_status(sess["id"], "error")
            return

        logger.info(f"Total images to send to GPT-4o: {len(all_images)}")

        # ── Step 4: GPT-4o Vision extraction ─────────────────
        ticket = await extract_flight_data(all_images)

        if not ticket.segments:
            await send_message(chat_id,
                "⚠️ I couldn't identify flight details in these images.\n\n"
                "Please make sure the images clearly show flight route, times, or booking details.\n"
                "Type /new and try again with better quality images.")
            await session.set_status(sess["id"], "error")
            return

        # ── Step 5: Generate PDF ──────────────────────────────
        pdf_bytes = generate_pdf(ticket)

        # ── Step 6: Build summary caption ────────────────────
        caption_lines = ["<b>✈️ Flight Ticket Summary</b>"]
        if ticket.passenger_name:
            caption_lines.append(f"👤 {ticket.passenger_name}")
        if ticket.booking_ref:
            caption_lines.append(f"🔖 Ref: {ticket.booking_ref}")

        for seg in ticket.segments:
            route = f"{seg.from_code or seg.from_city} → {seg.to_code or seg.to_city}"
            caption_lines.append(f"\n🛫 <b>{seg.airline}</b>")
            caption_lines.append(f"📍 {route}")
            if seg.departure_date:
                caption_lines.append(f"📅 {seg.departure_date}")
            if seg.departure_time:
                caption_lines.append(f"🕐 Dep: {seg.departure_time}  |  Arr: {seg.arrival_time}")
            if seg.duration:
                caption_lines.append(f"⏱ {seg.duration}  •  {seg.stops}")
            bag = []
            if seg.cabin_baggage:   bag.append(f"Cabin {seg.cabin_baggage}")
            if seg.checkin_baggage: bag.append(f"Check-in {seg.checkin_baggage}")
            if bag:
                caption_lines.append(f"🧳 {' + '.join(bag)}")

        if ticket.total_price:
            sym = {"INR":"₹","USD":"$","AED":"AED ","QAR":"QAR "}.get(ticket.currency, "")
            try:
                caption_lines.append(f"\n💰 <b>{sym}{int(ticket.total_price):,}</b>")
            except Exception:
                caption_lines.append(f"\n💰 <b>{sym}{ticket.total_price}</b>")

        caption = "\n".join(caption_lines)

        # ── Step 7: Send PDF ──────────────────────────────────
        seg0 = ticket.segments[0] if ticket.segments else None
        fn_parts = []
        if seg0:
            fn_parts.append(seg0.from_code or "XX")
            fn_parts.append(seg0.to_code or "XX")
            fn_parts.append(seg0.departure_date.replace(" ", "_") if seg0.departure_date else "")
        filename = f"ticket_{'_'.join(p for p in fn_parts if p)}.pdf" or "ticket.pdf"

        await send_document(chat_id, pdf_bytes, filename, caption)

        # ── Step 8: Mark done ─────────────────────────────────
        await session.set_status(sess["id"], "done")
        logger.info(f"Successfully processed ticket for user {user_id}")

    except Exception as e:
        logger.exception(f"Analysis failed for user {user_id}: {e}")
        await session.set_status(sess["id"], "error")
        await send_message(chat_id,
            f"❌ <b>Processing failed.</b>\n\n"
            f"Error: <code>{str(e)[:200]}</code>\n\n"
            "Please try again or contact support.")


async def send_unsupported(chat_id: int):
    from api.telegram import send_message
    await send_message(chat_id,
        "⚠️ Unsupported file type. Please send:\n"
        "• 📸 Photos / screenshots\n"
        "• 📄 PDF documents")


async def send_hint(chat_id: int):
    from api.telegram import send_message
    await send_message(chat_id,
        "📋 Send me flight ticket images or a PDF, then type /analyze to get your structured ticket.")


# ── Setup / Health Endpoints ──────────────────────────────────────────────────

@app.get("/api/setup")
async def setup_webhook(request: Request):
    """
    Visit this URL once after deploying to register your webhook with Telegram.
    GET https://your-vercel-url.vercel.app/api/setup
    """
    from api.telegram import set_webhook
    from api.config import settings

    # Build webhook URL from request host if VERCEL_URL not set
    host = str(request.base_url).rstrip("/")
    webhook_url = f"{host}/api/webhook"

    result = await set_webhook(webhook_url)
    return JSONResponse({
        "status": "ok" if result.get("ok") else "error",
        "webhook_url": webhook_url,
        "telegram_response": result,
    })


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "flight-ticket-bot"}


@app.get("/")
async def root():
    return {"message": "Flight Ticket Bot is running. Visit /api/setup to register webhook."}
