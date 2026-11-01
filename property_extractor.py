"""
Property Inquiry Extractor
--------------------------
Turns a raw WhatsApp property inquiry into structured data using Claude.

Example input:
    "I am looking for a 3-bedroom house in Kileleshwa, budget around 80k per month"
Extracted:
    property_type, bedrooms, location, budget_kes, rental_or_sale

Each result is printed cleanly and appended to inquiries.csv, which opens
in Excel or Google Sheets - no more copying details by hand.

Usage:
    python property_extractor.py           # paste inquiries one by one
    python property_extractor.py --test    # run the built-in test messages

Requirements:
    pip install -r requirements.txt
    A .env file containing:
        ANTHROPIC_API_KEY=your_key_here
"""

import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")
MAX_TOKENS = 200
CSV_FILE = Path(__file__).with_name("inquiries.csv")
FIELDS = ["property_type", "bedrooms", "location", "budget_kes", "rental_or_sale"]
PROPERTY_TYPES = {"house", "apartment", "bedsitter", "studio", "single room",
                  "maisonette", "bungalow", "townhouse", "land", "commercial", "other"}

SYSTEM_PROMPT = """You extract property requirements from WhatsApp inquiries sent to a
real estate agent in Nairobi, Kenya. Messages may be in English, Swahili or Sheng.

Return ONLY a JSON object with exactly these keys:
{"property_type": string or null,
 "bedrooms": integer or null,
 "location": string or null,
 "budget_kes": integer or null,
 "rental_or_sale": "rental" or "sale" or null}

Rules:
- property_type: one of house, apartment, bedsitter, studio, single room, maisonette,
  bungalow, townhouse, land, commercial, other. "Flat" means apartment.
- bedrooms: a whole number. "2br", "2 bedroom", "two-bed" -> 2. Bedsitters, studios
  and single rooms -> 0. null if not stated.
- location: the area name as written, properly capitalised (e.g. "Kileleshwa").
  If several areas are given, join them with " / ".
- budget_kes: a whole number in Kenyan shillings. "80k" -> 80000, "1.5m" -> 1500000,
  "20,000" -> 20000. For a range, use the upper limit. null if not stated.
- rental_or_sale: "rental" for rent, per month, monthly, kukodisha; "sale" for buy,
  purchase, kununua. A monthly budget means rental. null if it can't be told.
- Never guess. If a value is not in the message, use null.
- No explanation. No markdown. Just the JSON.

Examples:
Message: "I am looking for a 3-bedroom house in Kileleshwa, budget around 80k per month"
{"property_type": "house", "bedrooms": 3, "location": "Kileleshwa", "budget_kes": 80000, "rental_or_sale": "rental"}

Message: "Natafuta bedsitter karibu na Westlands, chini ya 20k"
{"property_type": "bedsitter", "bedrooms": 0, "location": "Westlands", "budget_kes": 20000, "rental_or_sale": "rental"}

Message: "Interested in buying a plot in Kitengela"
{"property_type": "land", "bedrooms": null, "location": "Kitengela", "budget_kes": null, "rental_or_sale": "sale"}
"""

TEST_MESSAGES = [
    "I am looking for a 3-bedroom house in Kileleshwa, budget around 80k per month",
    "Do you have any bedsitters near Westlands under 20k?",
    "Hi, I want to buy a 4 bedroom maisonette in Runda or Karen, budget 35m",
    "Natafuta nyumba ya kukodisha, two bedroom, Kilimani, 45k-55k",
    "Hello, do you have anything available?",
]


class ExtractionError(Exception):
    """A problem we can explain to the agent in plain English."""


def get_client():
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        sys.exit("No API key found. Add ANTHROPIC_API_KEY=your_key_here to your .env file.")
    return anthropic.Anthropic(api_key=api_key)


def call_model(client, inquiry):
    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Message: {inquiry}"}],
        )
    except anthropic.APIConnectionError:
        raise ExtractionError("No internet connection. Check your connection and try again.")
    except anthropic.AuthenticationError:
        raise ExtractionError("API key is wrong or expired. Check your .env file.")
    except anthropic.RateLimitError:
        raise ExtractionError("Too many requests. Wait 60 seconds and try again.")
    except anthropic.BadRequestError as err:
        if "credit balance" in str(err).lower():
            raise ExtractionError("Your Anthropic account has no credit. "
                                  "Add funds at console.anthropic.com > Billing.")
        raise ExtractionError(f"The request was rejected: {err.message}")
    except anthropic.NotFoundError:
        raise ExtractionError(f"Model '{MODEL}' wasn't found. Check CLAUDE_MODEL in your .env file.")
    except anthropic.APIStatusError as err:
        raise ExtractionError(f"The AI service returned an error ({err.status_code}). Try again shortly.")
    return "".join(block.text for block in message.content if block.type == "text").strip()


def parse_json(raw):
    """Turn the model's reply into a dict, tolerating stray code fences or text."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ExtractionError(f"The AI didn't return JSON. It said: {raw[:120]}")
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        raise ExtractionError(f"The AI returned invalid JSON: {raw[:120]}")
    if not isinstance(data, dict):
        raise ExtractionError("The AI returned JSON, but not an object.")
    return data


def to_int(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except ValueError:
        return None


def clean(data):
    """Keep only the expected fields, with the right types; anything odd becomes None."""
    ptype = data.get("property_type")
    ptype = ptype.strip().lower() if isinstance(ptype, str) else None
    deal = data.get("rental_or_sale")
    deal = deal.strip().lower() if isinstance(deal, str) else None
    location = data.get("location")
    return {
        "property_type": ptype if ptype in PROPERTY_TYPES else (ptype and "other"),
        "bedrooms": to_int(data.get("bedrooms")),
        "location": location.strip() if isinstance(location, str) and location.strip() else None,
        "budget_kes": to_int(data.get("budget_kes")),
        "rental_or_sale": deal if deal in ("rental", "sale") else None,
    }


def extract(client, inquiry):
    return clean(parse_json(call_model(client, inquiry)))


def show(result):
    labels = {
        "property_type": "Property type",
        "bedrooms": "Bedrooms",
        "location": "Location",
        "budget_kes": "Budget",
        "rental_or_sale": "Rental or sale",
    }
    missing = []
    for field in FIELDS:
        value = result[field]
        if value is None:
            text = "-- not stated --"
            missing.append(labels[field].lower())
        elif field == "budget_kes":
            text = f"KES {value:,}" + (" per month" if result["rental_or_sale"] == "rental" else "")
        elif field == "bedrooms" and value == 0:
            text = "0 (bedsitter/studio)"
        else:
            text = str(value).title() if field != "location" else value
        print(f"  {labels[field] + ':':<16}{text}")
    if missing:
        print(f"  -> Ask the client for: {', '.join(missing)}")


def save_to_csv(inquiry, result):
    is_new = not CSV_FILE.exists()
    with open(CSV_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["received_at", "message"] + FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow({"received_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                         "message": inquiry, **result})


def process(client, inquiry):
    print(f"\nInquiry: {inquiry}")
    result = extract(client, inquiry)
    show(result)
    save_to_csv(inquiry, result)


def main():
    print("Property Inquiry Extractor")
    print("-" * 26)
    client = get_client()
    try:
        if "--test" in sys.argv[1:]:
            for inquiry in TEST_MESSAGES:
                process(client, inquiry)
        else:
            print("Paste a client's inquiry and press Enter. Empty line to quit.")
            while True:
                try:
                    inquiry = input("\nInquiry: ").strip()
                except (KeyboardInterrupt, EOFError):
                    print()
                    break
                if not inquiry:
                    break
                result = extract(client, inquiry)
                show(result)
                save_to_csv(inquiry, result)
        print(f"\nSaved to {CSV_FILE.name}")
    except ExtractionError as err:
        print(f"\nSorry: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
