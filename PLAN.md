# Coin App: Plan

A local web app for tracking a coin collection, starting with Morgan dollars.
It's built so Peace dollars, Franklins and other types can be added later
without changing the schema.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic migrations
- **Database:** SQLite file (`data/coin-app.db`) to start. Moving to Postgres for hosting is a config change.
- **Photos:** stored on disk under `data/photos/<coin_id>/`. Can move to S3 or similar storage when hosted.
- **Frontend:** React, TypeScript, Vite
- **Auth:** email and password, hashed with argon2, session sent as an httpOnly cookie
- **Secrets:** a `.env` file that is never committed. It holds the Greysheet key and token, the PCGS token and the session secret.

## Data model

```
users
  id, email (unique), first_name, last_name, password_hash, created_at

coin_types              -- seeded with "Morgan Dollar"; later Peace, Franklin, ...
  id, name, slug, inventory_prefix (e.g. "MOR")

collections             -- "Morgan Dollar Collection 1", ...
  id, user_id, coin_type_id, name, created_at

coins
  id, user_id, coin_type_id, collection_id
  inventory_number      -- app-generated, unique, e.g. MOR-00001
  year, mint_mark       -- mint: P (none), O, S, CC, D
  grading_service       -- PCGS | NGC | ANACS | CACG | raw
  cert_number
  grade                 -- numeric 1-70
  strike                -- MS | PR
  designation           -- none | PL | DMPL | DPL | CAM | DCAM
  plus, star            -- grade modifiers
  vam                   -- free text, e.g. "VAM-1A"
  pcgs_number           -- PCGS catalog # (date/mint/designation); key for CPG pricing
  cac                   -- bool
  cac_sticker           -- green | gold | null
  slab_soapbox, slab_ngc_fatty, slab_rattler, slab_ogh   -- bools
  toning_obverse, toning_reverse, toning_dual, toning_rainbow  -- bools
  price_paid, purchase_date, purchased_from
  sale_price, sale_date, sold_to       -- null = on hand; set = sold
  notes
  lookup_raw (JSON)     -- full response from the grading service, kept for reference
  created_at, updated_at

coin_photos             -- up to 10 per coin
  id, coin_id, file_path, sort_order, source (upload | pcgs | ngc ...)

price_quotes            -- full history; each "Get CPG Price" click adds a row
  id, coin_id, source (CPG | PCGS | ...), value, grade_used, fetched_at, raw (JSON)
```

### Sold coins

A sold coin keeps its `collection_id`, so you can still see which collection it
came from. It's hidden from that collection's list and totals and appears on
the **Sold** list for its coin type (e.g. "Morgans – Sold"). Clearing the sale
fields puts it back in the collection.

### Collection summary cards

Collection summary cards only count coins on hand:

- **Total Price Paid**: sum of `price_paid`
- **Total CPG Value**: sum of each coin's latest CPG quote
- **Est. Wholesale**: Total CPG × 0.90
- Count of coins without a CPG quote, so the totals aren't misleading

## Cert lookups

All lookups share one interface: `lookup(cert_number) -> CoinLookupResult`.
The result fills in the add-coin form, and you review it before saving.

| Service | Method | Notes |
|---|---|---|
| PCGS  | Official public API | Year, mint, grade, designation, variety, photos |
| NGC   | No public API; ToS forbids automation | "Verify" opens the official page; enter details by hand. Ask NGC for partner access later. |
| ANACS | No public API; site is bot-protected | Same as NGC |
| CAC   | Public lookup page (cacgrading.com/lookup/{cert}) | Checks whether a PCGS or NGC cert is stickered; sticker color parsing is best effort |

## Pricing

- **Get CPG Price:** Greysheet CDN Public API v2 `GetPricingRequest?PcgsNumber=&Grade=`. Uses the CAC row for CAC coins. Every call is stored in `price_quotes`.
- **Later:** look up the PCGS number from the Greysheet catalog using date, mint and designation, so non-PCGS coins don't need it entered by hand.
- Each coin shows its price history.

## Screens

1. Sign up / Log in
2. Dashboard: coin types, then collections, plus a link to the Sold list
3. Collection view: summary cards and a coin table (sort and filter by year, mint, grade, toning, slab)
4. Sold list for each coin type: sale price, sale date, profit and loss
5. Add/Edit coin: cert lookup bar at the top, form below, photo uploader (max 10)
6. Coin detail: photos, all fields, CPG history, "Get CPG Price" button

## Build order

1. Backend scaffold, database models and migrations, auth
2. Collections and coins CRUD, inventory numbers, sold logic, photo upload
3. React frontend: auth, collections, coin form and table, summary cards
4. PCGS lookup, then CAC, NGC, ANACS
5. Greysheet CPG pricing and price history
