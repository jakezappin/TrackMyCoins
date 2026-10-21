# Cold Storage: design

Status: **design only, not started.** Written 2026-10-20.

## Goal

A user can take their whole collection off our servers and bring it back later.

- **Cold Storage export** (a button on the Dashboard) downloads everything the user owns, then wipes it from our
  database.
- **Restore** (offered when they log in) uploads that file and everything comes back as it was.

Some users will do this on every visit: restore when they log in, cold-store when they leave. So it has to be
**lean**: a small file, a restore in about a second, and almost no cost to us per cycle.

## Principles

1. **The file holds data only; photos never travel in it.** 500 coins come to roughly 100–300 KB compressed.
2. **Nobody can read a frozen collection without the user's file.** Not us, and not someone who gets into the server
   or a backup.
3. **Never wipe what the user doesn't safely have.** The wipe only happens after the user proves they hold a working
   copy of the file.
4. **The restore file is untrusted input.** Every row goes through the same checks as the coin form and bulk import.

## What the user downloads

One zip, `TrackMyCoins-ColdStorage-YYYY-MM-DD.zip`. The zip itself is **not** encrypted, so it opens with a
double-click on any computer.

| File | Purpose |
|---|---|
| `restore.tmc` | Encrypted restore file. Only TrackMyCoins can read it, and it's the only file used to restore. |
| `My Collection.xlsx` | For viewing offline. Uses Excel's own password protection (AES) with the **same passphrase**. |
| `README.txt` | Plain language: what each file is, keep the zip in two places, the passphrase can't be recovered, editing the spreadsheet doesn't change what gets restored. |

### `restore.tmc`

A small binary envelope. The parts that aren't encrypted (the header) name the format, the format version, the
encryption settings and the salt. The rest is an encrypted zip containing:

- `manifest.json`:
  - format version and app version (git commit)
  - export time
  - account identifier
  - row counts per table and a checksum of the data
- `data.json`: every row the user owns (see "What's in the file"). IDs stay as they were in the database; restore
  assigns new ones and remaps references.
- `media.json`: the **media key** and **vault id** (see "Photos and documents"), plus the list of every photo and
  document object: vault object name, original filename, content type, sort order, and `source_url` for slab
  photos.

**Encryption:**
- A key is derived from the passphrase with **Argon2id** (we already use argon2 for passwords). The salt and the
  Argon2 settings are stored in the header.
- The contents are encrypted with **AES-256-GCM**. GCM also detects tampering and wrong passphrases: either one
  fails cleanly with "This file is damaged or the passphrase is wrong".
- **Minimum passphrase:** 10 characters, the same rule as passwords. Show a strength meter.
- **The passphrase is never stored.** We can't recover it, and the UI must say so more than once.

### `My Collection.xlsx`

This builds on the existing Excel export (`routers/reports.py`), with extra sheets:

- **Summary:** totals for coins and bullion, values as of the export date
- **Coins:** every field, including storage location, grading service and cert, CAC, toning and error coin
- **Bullion**
- **Storage**
- **Want List**
- **Grading:** submissions and results
- **Dealers**
- **Sales**
- **Slab Photos:** PCGS/NGC image links, so those photos can still be seen online

Uploaded photos aren't in the spreadsheet; they stay encrypted on our side. Text cells are written as text, never
formulas, as the export already does.

- Password protection uses `msoffcrypto-tool`, a new dependency, because openpyxl can't encrypt.
- It opens in Excel and, I believe, Apple Numbers and LibreOffice. **Google Sheets can't open password-protected
  files.**
- **"Also include an unprotected spreadsheet":** a checkbox, **off by default**. When turned on it shows a warning
  that the file lists what you own and where it's kept.

## Photos and documents

Photos travel by **reference** only. This saves money, and it also keeps the file small.

| Kind | Where it lives | On restore |
|---|---|---|
| Your uploads (photos, receipts, PDFs) | **Cloudflare R2**, encrypted with a key held only by the user while frozen | Nothing to upload; they load straight from R2 again |
| PCGS / NGC slab photos | We keep the **original link** (`source_url`) | Fetched again when first viewed, and cached |

**How the uploads stay private while frozen:**
- **Media key:** each account has its own random key that encrypts its photos and documents.
- **Vault id:** objects are stored in R2 under that account's random vault id, never the user id:
  `vault/<vault_id>/<random object id>`.
- **While the account is active,** the media key sits in the database (itself encrypted with a server key set as a
  Fly secret), so photos can be served. Our server decrypts each photo as it serves it, which takes very little
  CPU.
- **On cold storage,** the media key and every row linking the vault to the account are deleted. The key exists
  only inside `restore.tmc`. R2 keeps encrypted files that nobody can read and that aren't tied to anyone.
- **On restore,** the media key and vault id come back with the file.

**Clean-up of abandoned vaults:** a separate `vaults` table holds `(vault_id, last_seen_at)` with **no user link**.
It's touched when a vault is restored or used. A monthly job deletes vaults not seen for **12 months** (the period is
an open question). The README and the export page say so.

**Restoring an older file:** photos deleted since that file was made are gone, so they show the usual placeholder.
Photos added after that file was made can no longer be reached and are removed by the clean-up job.

**Slab photo links break sometimes.** PCGS/NGC image addresses do change, so add a "Fetch photos again from cert"
action on the coin page.

## What's in the file

Every table in `backend/app/models.py` must be in exactly one of the groups below. A test enforces this (see
Testing), so a new table can't be forgotten.

**Exported, then wiped:**
- **Coins and collections:** `collections`, `coins`, `coin_photos` and `coin_attachments` (references only),
  `price_quotes`
- **Bullion:** `bullion_collections`, `bullion_items`, `bullion_photos` and `bullion_attachments` (references only)
- **Other user data:** `want_items`, `grading_submissions`, `grading_submission_coins`, `grading_attachments`
  (references only), `storage_spots`, `dealers`, `sales`
- **Counters:** `inventory_counters`, `collection_counters`, `bullion_counters`. These keep inventory numbers
  (MOR-00042) and collection numbers the same after restore.

**Kept, not exported:**
- `users` (email, name, password): needed to log in and restore
- `api_usage` and `price_refresh_runs`: daily quotas and the weekly refresh limit, so cold storage can't be used to
  reset them

**Wiped, not exported:**
- `label_queue`: temporary work in progress
- `collections.share_token`: share links stop working and aren't brought back. The user makes new ones.

**Shared, never touched:** `coin_types`, `catalog_entries`, `cpg_history`, `auction_sales`, `auction_fetches`,
`pcgs_guide_history`, `grade_price_sheets`, `spot_prices`, `pcgs_cache`. A restored collection is priced from
current market data on the next refresh.

**New:**
- `cold_storage` (one row per user while frozen): `frozen_at`, the export fingerprint (a SHA-256 of `restore.tmc`)
  and the format version
- `media_keys` (active accounts only): the media key encrypted with the server key, plus the vault id
- `vaults`: as described above
- `coin_photos.source_url` and `bullion_photos.source_url`: new columns

## Flows

### Cold storage

1. **Dashboard → "Cold Storage export".** The page explains:
   - what happens
   - that the file is the only copy
   - how long backups keep data (see "Honesty about backups")
2. **Choose a passphrase** (entered twice), and optionally tick the unprotected spreadsheet.
3. **Download.** The server builds the zip in memory (it's small), stores only its fingerprint, and sends it. Nothing
   is wiped yet.
4. **Verify.** "Choose the file you just saved". The user picks the zip or `restore.tmc` and types the passphrase.
   - The server checks that the fingerprint matches and that the passphrase opens the file, then discards the upload.
   - If verification fails, nothing is wiped.
5. **Confirm.** The user types `WIPE`.
6. **Wipe.** One database transaction deletes every exported-and-wiped row, the media key and the vault link, and
   sets the `cold_storage` row.
   - SQLite runs with `PRAGMA secure_delete=ON` for this delete, so deleted rows are overwritten rather than left in
     free space.
   - R2 objects are left in place, encrypted and no longer linked to anyone.
7. **Done.** The user is logged out, or shown the frozen dashboard.

### While frozen

- The dashboard shows "Your collection is in cold storage since Oct 20" with a **Restore** button.
- Adding coins or bullion is **disabled** in v1, to avoid merging (open question).
- Account settings, password change and account deletion still work.

### Restore

1. **Login → Restore.** The user uploads the zip or `restore.tmc` (KB-sized, so one normal request) and types the
   passphrase.
2. **Checks:**
   - the passphrase opens the file
   - the format version is known
   - the account matches (open question)
   - the account is empty
3. **Upgrade if needed.** Older format versions are upgraded step by step by converters (v1 → v2 → …) before
   loading.
4. **Load.**
   - Every row is validated through the existing schemas and rules, the same ones `CoinFields` / `_validate` and
     bulk import use.
   - New ids are assigned and references remapped. Inventory numbers and counters are kept.
   - Everything happens in **one transaction**, so the load either fully succeeds or leaves the account untouched.
5. **Media.** The media key and vault are put back, and the vault's `last_seen_at` is touched. References to missing
   objects show placeholders.
6. **Finish.** The `cold_storage` row is cleared and a summary is shown: "Restored 512 coins, 40 bullion items,
   1,204 photos (3 missing)".

The data is small, so restore runs inside the request: there's no background job, so the auto-stopping machine
can't interrupt it halfway.

## Honesty about backups

**"Wiped" means wiped from the live database now.** Backups keep copies for a while:
- Fly takes daily volume snapshots (about 5 days by default)
- the planned off-site backups

The export page must say plainly, for example "removed from our backups within N days", and N must actually be true.
The R2 photos are unreadable without the user's file from the moment of the wipe.

## Cost

| | Cost |
|---|---|
| One cold-storage or restore cycle | a few hundred KB each way: effectively free |
| Photos on R2 | about $0.015 per GB a month, free downloads to our server |
| Photos on the Fly volume (today) | about $0.15 per GB a month |
| Serving photos to users | the same Fly outbound cost as today (about $0.02/GB) |

**Moving photos to R2 cuts photo storage cost about 10×** for every user, not just cold-storage users. The work is
needed anyway: it's already on the wish list for off-site backups.

## Testing

Built on the regression suite (`test/regression-suite` branch).

- **Table coverage test:** lists every table in the database and fails unless it's in exactly one group under
  "What's in the file".
- **Round-trip test:**
  1. Build a full account: coins in several series, bullion, photos, documents, want list, grading submissions,
     storage, dealers, sales, sold coins and price history.
  2. Snapshot every API view.
  3. Export, verify, wipe and restore.
  4. Compare the snapshot. Everything must match, including inventory numbers.
- **Old files keep working:** a saved `restore.tmc` for each released format version is kept in the tests and must
  restore on the current code.
- **The wipe leaves nothing:**
  - no rows with the user's id remain in any exported-and-wiped table
  - the media key is gone
  - photos can no longer be fetched
  - share links return 404
- **Refusals:**
  - wrong passphrase, a damaged file, a tampered file (GCM failure), an unknown format version
  - a file from another account (if accounts are bound)
  - restoring into an account that isn't empty
  - verifying a file that doesn't match the export
- **Hostile file:** rows that fail validation, references to rows not in the file, huge numbers of rows, and
  `source_url`s pointing at hosts not on the allowed list. Each must be refused cleanly, never a 500 error.
- **End-to-end (Playwright):**
  - export, verify, wipe, then the frozen dashboard
  - log out, log back in, restore
  - the collection, photos and spreadsheet open
- **Size and speed:** a 2,000-coin account exports and restores in a couple of seconds.

## Build order

0. **Photos to R2 with media keys and vaults,** plus `source_url` on slab photos. This includes migrating existing
   photos and documents off the Fly volume. Useful by itself (cheaper, and backed up off the server).
1. **"Download a full backup"** (export only, no wipe): `restore.tmc` plus the protected spreadsheet. Also useful by
   itself.
2. **Restore** into an empty account, with the coverage and round-trip tests.
3. **Cold Storage:** verify, wipe, the frozen state and the restore prompt at login.
4. **Vault clean-up job** and the backup-retention wording.

## Open questions

1. **Encryption required, or optional?** Recommendation: required for `restore.tmc`. The unprotected spreadsheet is
   opt-in.
2. **Bind files to the account?** Should a file only restore into the account that made it? Recommendation: yes for
   v1, which is simpler and safer. Moving a collection to another account can come later.
3. **Allow adding coins while frozen?** If yes, restore must merge, which brings inventory number conflicts.
   Recommendation: no for v1.
4. **Vault retention:** how long before unused frozen photos are deleted (12 months suggested), and should we warn by
   email first? Email isn't set up yet.
5. **Backup retention N:** what number can we honestly promise? It depends on the Fly snapshot setting and the
   off-site backup plan.
6. **Should a frozen account hide that a collection ever existed?** Today the `users` row, quota counters and the
   `cold_storage` row remain. Fine for v1, but say so.
