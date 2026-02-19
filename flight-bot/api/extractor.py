"""
OCR + Structured Flight Data Extraction via GPT-4o Vision.

Handles:
  - JPEG / PNG / WEBP screenshots
  - Scanned PDFs  (rendered to images via PyMuPDF — no poppler needed)
  - Multi-page PDFs

All images from all files are batched into a SINGLE GPT-4o call
so the model can cross-reference details spread across screenshots.
"""
import base64, io, json, logging
from dataclasses import dataclass, field
import httpx
from api.config import settings

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class FlightSegment:
    airline:          str = ""
    flight_number:    str = ""
    from_code:        str = ""
    from_city:        str = ""
    to_code:          str = ""
    to_city:          str = ""
    departure_date:   str = ""
    departure_time:   str = ""
    arrival_time:     str = ""
    duration:         str = ""
    stops:            str = "Direct"
    cabin_baggage:    str = ""
    checkin_baggage:  str = ""


@dataclass
class FlightTicket:
    booking_ref:    str  = ""
    passenger_name: str  = ""
    segments:       list = field(default_factory=list)
    total_price:    str  = ""
    currency:       str  = "INR"
    contact_email:  str  = ""
    contact_phone:  str  = ""
    raw_notes:      str  = ""


# ── PDF → images ──────────────────────────────────────────────────────────────

def pdf_to_images(pdf_bytes: bytes) -> list:
    """Render every PDF page to PNG using PyMuPDF (no poppler, works on Vercel)."""
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    imgs = []
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))   # 144 DPI
        imgs.append(pix.tobytes("png"))
    doc.close()
    logger.info(f"PDF rendered to {len(imgs)} page image(s)")
    return imgs


def image_to_png(raw: bytes) -> bytes:
    """Normalize any image format to PNG via Pillow."""
    from PIL import Image
    img = Image.open(io.BytesIO(raw))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def file_to_images(raw: bytes, file_type: str) -> list:
    """
    file_type: "pdf" | "image"
    Returns list of PNG bytes.
    """
    if file_type == "pdf":
        return pdf_to_images(raw)
    try:
        return [image_to_png(raw)]
    except Exception:
        return [raw]   # fallback: send as-is


# ── Extraction prompt ─────────────────────────────────────────────────────────

PROMPT = """
You are an expert flight booking data extractor.

I'm giving you one or more images from a flight e-ticket or booking confirmation.
The images may be DIFFERENT screenshots of the SAME booking:
  • Image 1  → route + times
  • Image 2  → baggage allowance
  • Image 3  → price / booking reference
  • Image 4  → passenger name / contact

YOUR JOB: Combine ALL images and return ONE complete JSON.
Return ONLY valid JSON — no markdown fences, no explanation.

{
  "booking_ref":    "PNR or booking code, else empty string",
  "passenger_name": "full name if visible, else empty string",
  "total_price":    "total as numeric string e.g. 14000",
  "currency":       "INR | USD | AED | QAR | SAR | OMR | KWD",
  "contact_email":  "email or empty string",
  "contact_phone":  "phone or empty string",
  "segments": [
    {
      "airline":          "e.g. Air India Express",
      "flight_number":    "e.g. IX 342",
      "from_code":        "3-letter IATA e.g. CNN",
      "from_city":        "e.g. Kozhikode",
      "to_code":          "e.g. DOH",
      "to_city":          "e.g. Doha",
      "departure_date":   "e.g. 02 Mar 2025",
      "departure_time":   "e.g. 19:15",
      "arrival_time":     "e.g. 21:20",
      "duration":         "e.g. 4h 35m",
      "stops":            "Direct | 1 Stop | 2 Stops",
      "cabin_baggage":    "e.g. 7 kg",
      "checkin_baggage":  "e.g. 30 kg"
    }
  ],
  "raw_notes": "anything else relevant"
}

RULES:
- Round trip → two segment objects
- Missing info → empty string ""
- Common IATA codes: Chennai=MAA, Kozhikode/Calicut=CNN, Mumbai=BOM, Delhi=DEL,
  Kochi=COK, Bengaluru=BLR, Dubai=DXB, Doha=DOH, Abu Dhabi=AUH,
  Riyadh=RUH, Jeddah=JED, Muscat=MCT, Kuwait=KWI, Bahrain=BAH
- Prices: strip commas (14,000 → 14000)
- Data is spread across images — find it all
"""


# ── Main extraction call ──────────────────────────────────────────────────────

async def extract_flight_data(all_images: list) -> FlightTicket:
    """
    Batch all PNG images into one GPT-4o call and return FlightTicket.
    all_images: list of bytes (PNG)
    """
    logger.info(f"GPT-4o Vision call: {len(all_images)} image(s)")

    content = [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{base64.b64encode(img).decode()}",
                "detail": "high",
            },
        }
        for img in all_images
    ]
    content.append({"type": "text", "text": PROMPT})

    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": "Return valid JSON only. No markdown."},
                    {"role": "user", "content": content},
                ],
                "max_tokens": 2000,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"]

    logger.info(f"GPT-4o raw: {raw[:250]}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from GPT-4o: {e}\n{raw}")

    ticket = FlightTicket(
        booking_ref=data.get("booking_ref", ""),
        passenger_name=data.get("passenger_name", ""),
        total_price=data.get("total_price", ""),
        currency=data.get("currency", "INR"),
        contact_email=data.get("contact_email", ""),
        contact_phone=data.get("contact_phone", ""),
        raw_notes=data.get("raw_notes", ""),
    )
    for s in data.get("segments", []):
        ticket.segments.append(FlightSegment(
            airline=s.get("airline", ""),
            flight_number=s.get("flight_number", ""),
            from_code=s.get("from_code", ""),
            from_city=s.get("from_city", ""),
            to_code=s.get("to_code", ""),
            to_city=s.get("to_city", ""),
            departure_date=s.get("departure_date", ""),
            departure_time=s.get("departure_time", ""),
            arrival_time=s.get("arrival_time", ""),
            duration=s.get("duration", ""),
            stops=s.get("stops", "Direct"),
            cabin_baggage=s.get("cabin_baggage", ""),
            checkin_baggage=s.get("checkin_baggage", ""),
        ))

    logger.info(f"Ticket: {len(ticket.segments)} segment(s), ₹{ticket.total_price}")
    return ticket
