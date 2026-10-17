# Coin App

Track a coin collection: Morgan dollars first, other series later.

- **Backend:** Python FastAPI and SQLite (`backend/`)
- **Frontend:** React, TypeScript and Vite (`frontend/`)

## First-time setup

Already done on this machine:

- the Python venv in `backend/.venv`
- Node in `.tools/node`
- the frontend packages
- a `.env` file with a random session secret

### What you need to add

1. **API keys.** Open `.env` and fill in:
   - `PCGS_API_TOKEN`: sign in at https://www.pcgs.com/publicapi and copy the token from the documentation page. The free tier allows 1,000 calls a day.
   - `GREYSHEET_API_KEY` and `GREYSHEET_API_TOKEN`: from your Greysheet account's API credentials page. Sandbox and production use different credentials. If you only have sandbox keys, set `GREYSHEET_USE_SANDBOX=true`.
2. **Restart.** After editing `.env`, restart the app.

## Running

```bash
./dev.sh
```

Then open http://localhost:5173. The first time, click **Create one** to make your account.

`dev.sh` does three things:

- applies database migrations
- starts the API on port 8000
- starts the web app on port 5173

Press Ctrl-C to stop both.

## Forgot your password?

There's no email reset yet. Set a new password from Terminal:

```bash
cd backend && .venv/bin/python -m scripts.reset_password you@example.com
```

Run it without an email to list the accounts.

## Where data lives

- `data/coin-app.db`: the SQLite database
- `data/photos/<coin id>/`: uploaded and imported photos

Back up the whole `data/` folder to back up your collection. It is not committed to git.

## Cert lookups

| Service | How it works |
|---|---|
| PCGS | Official API. Fills in year, mint, grade, designation, PCGS #, VAM (when listed) and photos. |
| CAC | Checked automatically for PCGS and NGC certs on the public cacgrading.com lookup page. Sticker colour detection is best effort, so please confirm it. |
| NGC, ANACS | No public API. NGC's terms forbid automated access. The **Verify ↗** button opens the official page; type the details in. |

## CPG pricing

"Get CPG Price" calls the Greysheet API with the coin's **PCGS coin number** and grade:

- For CAC coins, it uses the CAC price row when one exists.
- Every fetch is saved, so you get a price history.
- You can also type a CPG value by hand.

### Finding the PCGS number

**If the coin has no PCGS number, the app finds it** from the date, mint, finish (MS, Proof or Silver Proof) and designation:

- It downloads that series' section of Greysheet's catalog the first time it's needed, caches it locally, and refreshes it every 30 days.
- If there's exactly one plain match, it fills in the PCGS # and prices the coin.
- If there are several (e.g. 1878 8TF vs 7TF, or which 1936 commemorative), the **Find** button lists them so you can pick one.
- A **Variety / issue** typed on the coin (e.g. "Boone", "8TF", "Type 2") narrows the match.
- In Silver Proof collections, the silver issue is chosen when a date has both clad and silver; in Proof collections, the clad one.
- VAM is just a note and isn't used for matching.
- **GSA Hard Pack / Soft Pack** (Morgans only): GSA coins are priced from Greysheet's separate GSA listings. If Greysheet has no listing for that date and pack, the app says so instead of guessing.

To check your Greysheet setup and what the catalog has for each series:

```bash
cd backend && .venv/bin/python -m scripts.greysheet_check                        # all series
cd backend && .venv/bin/python -m scripts.greysheet_check kennedy-half-dollars   # one, with samples
```

### PCGS market data

**Get PCGS Data** on a coin's page fetches, for its PCGS # and grade:

- the **PCGS Price Guide** value, saved to the price history next to CPG
- the **PCGS population** (and how many are graded higher)
- the **last 10 auction sales**, shown as a chart with the PCGS Guide and CPG as reference lines, plus a list linking to each lot

Each fetch uses 2 of PCGS's 1,000 free API calls a day.

## Coin types

44 series: copper through Ike dollars, classic commemoratives, classic $1-$20 gold, American Silver Eagles and the four American Gold Eagle sizes.

The supported series, their inventory prefixes and their Greysheet catalog sections are listed in `backend/app/series.py`.

- **Adding a series:** add an entry there and restart the app.
- **Collection types:** each series offers MS, plus Proof and/or Silver Proof where they exist. Each collection is one series and one finish, so its URL looks like `/collections/kennedy-half-dollars-proof/1`.
- **Grades:** proof collections only accept PR grades.

## Collection Status and Export

- **Collection Status** (on each collection page) lists every date and mint in the series for that collection's finish, earliest first. It shows the coins you own beside each one, and you can filter to just the missing ones.
  - The list of dates comes from Greysheet's catalog.
  - Some coins are listed by issue rather than by date:
    - classic commemoratives (e.g. "1936 Boone")
    - Washington quarters from 1999 on (State, Territories, ATB and American Women designs, e.g. "1999 Delaware")
    - the 1878 Philadelphia Morgan tail-feather varieties (8TF, 7TF Reverse of 1878, 7TF Reverse of 1879, 7/8TF Strong, 7/8TF Weak)
  - A coin is matched to its issue by its PCGS # or by the Variety / issue field.
  - **Classic commemoratives** have a **Full set / Type set** switch:
    - **Full set:** every issue, date, mint and listed variety (146 lines).
    - **Type set:** one coin per design, any date or mint (51 designs).
    - The Excel export includes both, as the Checklist and Type Set sheets.
  - Sold coins don't count.
- **Export** downloads an Excel file with four sheets:
  - **Summary:** the collection's totals
  - **Coins:** every coin with all its details
  - **Checklist:** have / missing for each date
  - **Sold:** coins sold out of the collection

## Development

```bash
cd backend && .venv/bin/pytest -q                                   # backend tests
cd backend && .venv/bin/alembic revision --autogenerate -m "msg"    # after model changes
cd frontend && PATH="../.tools/node/bin:$PATH" npx tsc -b           # type-check
```
