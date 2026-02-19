"""
Flight Details Analyzer
Takes all raw extracted text (from multiple screenshots/pages)
and uses Claude to intelligently parse out structured flight data.
Handles split information across multiple screenshots.
"""

import os
import json
import logging
import httpx
import re

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"


async def analyze_flight_details(combined_text: str) -> dict | None:
    """
    Send all combined raw text to Claude.
    Claude extracts and structures the flight details
    even if information is split across multiple screenshots.
    Returns a structured dict or None if no flight data found.
    """

    prompt = f"""You are a flight ticket data extractor. 
I will give you raw text extracted from multiple flight ticket screenshots or PDFs.
The information may be SPLIT across multiple files — for example:
- Screenshot 1 might have origin, destination, flight times
- Screenshot 2 might have baggage allowance and price
- Screenshot 3 might have passenger name and booking reference

Your job: Read ALL the text carefully, combine information intelligently, and return a single JSON object.

RAW EXTRACTED TEXT FROM ALL FILES:
---
{combined_text}
---

Return ONLY a valid JSON object with these exact fields (use null for missing values):

{{
  "company_name": "Travel agency or company name if visible, else null",
  "travel_date": "Date in 'Mar 02' format or full date",
  "airline": "Airline name (e.g., Air India Express)",
  "flight_number": "Flight number (e.g., IX 344)",
  "origin": "Origin city/airport code (e.g., CNN or Calicut)",
  "origin_full": "Full origin name (e.g., Calicut International Airport)",
  "destination": "Destination city/airport code (e.g., DOH or Doha)",
  "destination_full": "Full destination name (e.g., Hamad International Airport)",
  "departure_time": "Departure time (e.g., 19:15)",
  "arrival_time": "Arrival time (e.g., 21:20)",
  "duration": "Flight duration (e.g., 4 hours 35 mins)",
  "stops": "direct or number of stops (e.g., direct, 1 stop)",
  "cabin_baggage": "Cabin baggage (e.g., 7kg)",
  "check_in_baggage": "Check-in baggage (e.g., 30kg)",
  "price": "Total price with currency (e.g., ₹14,000 or AED 250)",
  "passenger_name": "Passenger name if visible",
  "pnr": "PNR or booking reference if visible",
  "seat": "Seat number if visible",
  "terminal": "Terminal info if visible",
  "meal": "Meal included or not if mentioned",
  "notes": "Any other important details"
}}

Return ONLY the JSON, no explanation, no markdown code blocks."""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    payload = {
        "model": "claude-opus-4-6",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": prompt}
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(ANTHROPIC_API, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            raw = data["content"][0]["text"].strip()

        # Clean up any accidental markdown fences
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()

        flight_data = json.loads(raw)
        logger.info(f"Parsed flight data: {flight_data}")
        return flight_data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {e}\nRaw: {raw}")
        return None
    except Exception as e:
        logger.error(f"Flight analysis failed: {e}")
        return None
