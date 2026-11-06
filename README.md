# Property Inquiry Extractor

A Python script for a Nairobi property agent. Paste in a raw WhatsApp inquiry like *"I am looking for a 3-bedroom house in Kileleshwa, budget around 80k per month"* and it uses Claude to pull out the key details as structured data. It prints them clearly and adds them as a row in `inquiries.csv`, which opens in Excel or Google Sheets.

## The problem it solves

The agent gets dozens of inquiries a week, written in every style: full sentences, "2br Kilimani 50k", Swahili, Sheng. She reads each one and copies the details into a spreadsheet by hand. This script does that step in seconds. It also flags what the client didn't say, so she knows exactly what to ask next.

## What it extracts, and why each field matters

| Field | Example | Why it matters |
|---|---|---|
| `property_type` | `house`, `apartment`, `bedsitter`, `land` | The first filter when matching a client to listings. A bedsitter seeker and a maisonette buyer are completely different leads. |
| `bedrooms` | `3` (bedsitters and studios = `0`) | Narrows the matching listings and is the main driver of price within a type. |
| `location` | `Kileleshwa`, `Runda / Karen` | Kenyan clients search by neighbourhood first. It decides which listings and which agent or viewing schedule apply. |
| `budget_kes` | `80000` (from "80k"); ranges use the upper limit | Stored as a plain number, so the spreadsheet can sort and filter by budget, and listings above it can be skipped. |
| `rental_or_sale` | `rental` or `sale` | Rentals and sales are different businesses, with different listings, commissions and paperwork. A KES 80,000 budget means very different things for each. |

If a detail isn't in the message, the field is left empty (`null`) and never guessed. The script then prints **"Ask the client for: …"**.

## How it works (prompt engineering)

- **Structured system prompt:** it defines the exact JSON keys, the allowed values, and the rules for Kenyan shorthand ("80k" → 80000, "2br" → 2, "kukodisha" → rental).
- **Few-shot examples:** three worked examples (English, Swahili, and one with missing information) show the model exactly what the output should look like.
- **JSON only:** the prompt asks for raw JSON with no explanation or markdown, so Python can parse it.
- **Defensive parsing:** if the model wraps the JSON in code fences or adds a sentence, the script still finds and parses it. Each field is then type-checked: numbers become integers, unknown property types become `other`, and anything invalid becomes empty.

## Setup

1. Get an API key at [console.anthropic.com](https://console.anthropic.com) and add credit.
2. Install the requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Create your `.env` file and paste in your key:
   ```bash
   cp .env.example .env
   ```

## Run

Paste inquiries one at a time:
```bash
python property_extractor.py
```

Run the five built-in test inquiries, including a Swahili one and one with no details at all:
```bash
python property_extractor.py --test
```

## Example output

A real run of `python property_extractor.py --test`:

```
Property Inquiry Extractor
--------------------------

Inquiry: I am looking for a 3-bedroom house in Kileleshwa, budget around 80k per month
  Property type:  House
  Bedrooms:       3
  Location:       Kileleshwa
  Budget:         KES 80,000 per month
  Rental or sale: Rental

Inquiry: Do you have any bedsitters near Westlands under 20k?
  Property type:  Bedsitter
  Bedrooms:       0 (bedsitter/studio)
  Location:       Westlands
  Budget:         KES 20,000 per month
  Rental or sale: Rental

Inquiry: Hi, I want to buy a 4 bedroom maisonette in Runda or Karen, budget 35m
  Property type:  Maisonette
  Bedrooms:       4
  Location:       Runda / Karen
  Budget:         KES 35,000,000
  Rental or sale: Sale

Inquiry: Natafuta nyumba ya kukodisha, two bedroom, Kilimani, 45k-55k
  Property type:  House
  Bedrooms:       2
  Location:       Kilimani
  Budget:         KES 55,000 per month
  Rental or sale: Rental

Inquiry: Hello, do you have anything available?
  Property type:  -- not stated --
  Bedrooms:       -- not stated --
  Location:       -- not stated --
  Budget:         -- not stated --
  Rental or sale: -- not stated --
  -> Ask the client for: property type, bedrooms, location, budget, rental or sale

Saved to inquiries.csv
```

## Errors handled

| Situation | What you see |
|---|---|
| No API key in `.env` | How to add it |
| No internet / wrong key / no credit / rate limit | A plain-English message for each |
| AI reply isn't valid JSON | "The AI didn't return JSON…", with what it said instead |
| A field has the wrong type (e.g. budget as text) | Converted where possible, otherwise left empty |

`inquiries.csv` is excluded from git because it contains real clients' messages.
