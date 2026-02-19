"""
PDF Generator using ReportLab.
Produces a professional, branded flight ticket summary PDF.
"""
import io, logging
from api.extractor import FlightTicket
from api.config import settings

logger = logging.getLogger(__name__)


def generate_pdf(ticket: FlightTicket) -> bytes:
    """Return raw PDF bytes for the given FlightTicket."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer,
        HRFlowable, Table, TableStyle,
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

    # ── Palette ───────────────────────────────────────────────
    NAVY   = colors.HexColor("#0D1B3E")
    GOLD   = colors.HexColor("#C8963E")
    LGRAY  = colors.HexColor("#F4F6FA")
    MGRAY  = colors.HexColor("#8892A4")
    DGRAY  = colors.HexColor("#2D3748")
    WHITE  = colors.white
    BORDER = colors.HexColor("#D1D9E6")

    # ── Style factory ─────────────────────────────────────────
    def S(name, **kw):
        return ParagraphStyle(name, **kw)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=18*mm, bottomMargin=18*mm)

    W = 170*mm   # usable width

    def lbl(text, align=TA_LEFT):
        return Paragraph(text.upper(),
            S("lbl", fontSize=7, fontName="Helvetica",
              textColor=MGRAY, alignment=align, spaceAfter=1))

    def val(text, size=13, align=TA_LEFT):
        return Paragraph(str(text) or "—",
            S("val", fontSize=size, fontName="Helvetica-Bold",
              textColor=DGRAY, alignment=align, spaceAfter=3))

    # ── Story ─────────────────────────────────────────────────
    s = []

    # ---- Header ----
    s.append(Paragraph(settings.AGENCY_NAME,
        S("agency", fontSize=24, fontName="Helvetica-Bold",
          textColor=NAVY, alignment=TA_CENTER, spaceAfter=2)))
    s.append(Paragraph("Flight Ticket Summary",
        S("sub", fontSize=9, fontName="Helvetica",
          textColor=MGRAY, alignment=TA_CENTER, spaceAfter=10)))
    s.append(HRFlowable(width="100%", thickness=2.5,
                         color=GOLD, spaceAfter=12))

    # ---- Passenger / Ref row ----
    show_top = ticket.passenger_name or ticket.booking_ref
    if show_top:
        left  = [lbl("Passenger"), val(ticket.passenger_name or "—", 12)]
        right = [lbl("Booking Ref", TA_RIGHT), val(ticket.booking_ref or "—", 12, TA_RIGHT)]
        t = Table([[
            Table([left],  colWidths=[W/2]),
            Table([right], colWidths=[W/2]),
        ]], colWidths=[W/2, W/2])
        t.setStyle(TableStyle([
            ("LEFTPADDING",  (0,0),(-1,-1), 0),
            ("RIGHTPADDING", (0,0),(-1,-1), 0),
            ("TOPPADDING",   (0,0),(-1,-1), 0),
            ("BOTTOMPADDING",(0,0),(-1,-1), 0),
        ]))
        s.append(t)
        s.append(Spacer(1, 8))

    # ── Flight Segments ───────────────────────────────────────
    for i, seg in enumerate(ticket.segments):
        if len(ticket.segments) > 1:
            label = "OUTBOUND FLIGHT" if i == 0 else "RETURN FLIGHT"
            s.append(Paragraph(label,
                S("seg_hdr", fontSize=8, fontName="Helvetica-Bold",
                  textColor=MGRAY, letterSpacing=1.5,
                  spaceBefore=10, spaceAfter=6)))

        # Airline + flight number
        fn = f"  <font color='#8892A4' size='9'>{seg.flight_number}</font>" if seg.flight_number else ""
        s.append(Paragraph(
            f"<font color='#C8963E'>✈</font>  {seg.airline or 'Unknown Airline'}{fn}",
            S("al", fontSize=13, fontName="Helvetica-Bold",
              textColor=DGRAY, spaceBefore=4, spaceAfter=8)))

        # Date badge
        date_t = Table([[Paragraph(seg.departure_date or "—",
            S("db", fontSize=9, fontName="Helvetica-Bold",
              textColor=WHITE, alignment=TA_CENTER))]],
            colWidths=[45*mm])
        date_t.setStyle(TableStyle([
            ("BACKGROUND",     (0,0),(-1,-1), NAVY),
            ("TOPPADDING",     (0,0),(-1,-1), 5),
            ("BOTTOMPADDING",  (0,0),(-1,-1), 5),
            ("LEFTPADDING",    (0,0),(-1,-1), 8),
            ("RIGHTPADDING",   (0,0),(-1,-1), 8),
        ]))
        s.append(date_t)
        s.append(Spacer(1, 6))

        # Route: CODE → CODE
        fr = seg.from_code or seg.from_city or "???"
        to = seg.to_code   or seg.to_city   or "???"
        s.append(Paragraph(f"{fr}  →  {to}",
            S("route", fontSize=30, fontName="Helvetica-Bold",
              textColor=NAVY, alignment=TA_CENTER, spaceAfter=2)))

        # City names under codes
        city_t = Table([[
            Paragraph(seg.from_city,
                S("fc", fontSize=9, fontName="Helvetica",
                  textColor=MGRAY, alignment=TA_LEFT)),
            Paragraph(seg.to_city,
                S("tc", fontSize=9, fontName="Helvetica",
                  textColor=MGRAY, alignment=TA_RIGHT)),
        ]], colWidths=[W/2, W/2])
        city_t.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0),
                                    ("RIGHTPADDING",(0,0),(-1,-1),0)]))
        s.append(city_t)
        s.append(Spacer(1, 10))

        # Times / Duration block (shaded card)
        dep_col = Table([[
            lbl("Departure"),
            Paragraph(seg.departure_time or "—",
                S("dt", fontSize=22, fontName="Helvetica-Bold", textColor=NAVY)),
            Paragraph(f"from {seg.from_code or seg.from_city}",
                S("ds", fontSize=9, fontName="Helvetica", textColor=MGRAY)),
        ]], colWidths=[W*0.3])

        dur_col = Table([[
            lbl("Duration", TA_CENTER),
            Paragraph(seg.duration or "—",
                S("du", fontSize=14, fontName="Helvetica-Bold",
                  textColor=DGRAY, alignment=TA_CENTER)),
            Paragraph(seg.stops,
                S("st", fontSize=9, fontName="Helvetica-Bold",
                  textColor=GOLD, alignment=TA_CENTER)),
        ]], colWidths=[W*0.4])

        arr_col = Table([[
            lbl("Arrival", TA_RIGHT),
            Paragraph(seg.arrival_time or "—",
                S("at", fontSize=22, fontName="Helvetica-Bold",
                  textColor=NAVY, alignment=TA_RIGHT)),
            Paragraph(f"at {seg.to_code or seg.to_city}",
                S("as_", fontSize=9, fontName="Helvetica",
                  textColor=MGRAY, alignment=TA_RIGHT)),
        ]], colWidths=[W*0.3])

        times_t = Table([[dep_col, dur_col, arr_col]],
                        colWidths=[W*0.3, W*0.4, W*0.3])
        times_t.setStyle(TableStyle([
            ("BACKGROUND",     (0,0),(-1,-1), LGRAY),
            ("TOPPADDING",     (0,0),(-1,-1), 12),
            ("BOTTOMPADDING",  (0,0),(-1,-1), 12),
            ("LEFTPADDING",    (0,0),(-1,-1), 14),
            ("RIGHTPADDING",   (0,0),(-1,-1), 14),
            ("VALIGN",         (0,0),(-1,-1), "MIDDLE"),
        ]))
        s.append(times_t)
        s.append(Spacer(1, 10))

        # Baggage row
        bag_t = Table([[
            Paragraph("🎒  Cabin Baggage",
                S("bl", fontSize=8, fontName="Helvetica-Bold", textColor=MGRAY)),
            val(seg.cabin_baggage or "—", 12),
            Paragraph("🧳  Check-in Baggage",
                S("ck", fontSize=8, fontName="Helvetica-Bold",
                  textColor=MGRAY, alignment=TA_RIGHT)),
            val(seg.checkin_baggage or "—", 12, TA_RIGHT),
        ]], colWidths=[50*mm, 25*mm, 65*mm, 30*mm])
        bag_t.setStyle(TableStyle([
            ("LEFTPADDING",  (0,0),(-1,-1), 0),
            ("RIGHTPADDING", (0,0),(-1,-1), 0),
            ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ]))
        s.append(bag_t)

        # Separator between segments
        if i < len(ticket.segments) - 1:
            s.append(Spacer(1, 8))
            s.append(HRFlowable(width="100%", thickness=1,
                                 color=BORDER, spaceAfter=10, dash=[5,3]))

    # ── Price ─────────────────────────────────────────────────
    s.append(Spacer(1, 12))
    s.append(HRFlowable(width="100%", thickness=2.5, color=GOLD, spaceAfter=10))

    if ticket.total_price:
        sym = {"INR":"₹","USD":"$","AED":"AED ","QAR":"QAR ",
               "SAR":"SAR ","OMR":"OMR ","KWD":"KWD "}.get(ticket.currency, "")
        try:
            price_str = f"{sym}{int(ticket.total_price):,}"
        except Exception:
            price_str = f"{sym}{ticket.total_price}"

        s.append(Paragraph("TOTAL PRICE",
            S("pl", fontSize=9, fontName="Helvetica-Bold",
              textColor=MGRAY, alignment=TA_CENTER, letterSpacing=1.5)))
        s.append(Paragraph(price_str,
            S("pv", fontSize=24, fontName="Helvetica-Bold",
              textColor=NAVY, alignment=TA_CENTER, spaceBefore=4)))

    # Notes
    if ticket.raw_notes:
        s.append(Spacer(1, 6))
        s.append(Paragraph(f"<i>{ticket.raw_notes}</i>",
            S("notes", fontSize=8, fontName="Helvetica-Oblique",
              textColor=MGRAY, alignment=TA_CENTER)))

    # ── Footer ────────────────────────────────────────────────
    s.append(Spacer(1, 14))
    s.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    s.append(Paragraph(
        f"{settings.AGENCY_NAME}  •  Auto-generated flight ticket summary",
        S("ft", fontSize=8, fontName="Helvetica",
          textColor=MGRAY, alignment=TA_CENTER, spaceBefore=5)))

    doc.build(s)
    return buf.getvalue()
