# TrackMyCoins wish list

Features we've talked about and put on hold, with what we learned so they're quick to pick up again.

## Up next (agreed order)

1. Install on phone (installable web app: icon, full screen).
2. Rapid batch add (scan slab after slab into a queue, review, save all).
3. **Bullion collection** (bars, rounds, etc.): works differently from numismatic coins (weight, purity, melt-based
   value, quantities). Design to be discussed before building.

## On hold

### Estimated value at purchase (Greysheet price history)
Show what a coin was worth when it was bought ("paid $1,250, value then $1,400, 11% below market"), and rebuild the
value-over-time chart from real history instead of the dashed backfill.
- Greysheet's website shows CPG, NGC and PCGS price history per coin, but the API we use has no history: no call
  takes a date and none return past values (checked 2026-10-17).
- Next step: ask support@greysheet.com whether Dealer+/Pro API access includes historical values, how far back,
  and whether a website subscription can be linked to our API key.
- Fallback idea: an optional "Estimated value at purchase" field, filled automatically from CPG for purchases in
  the last ~30 days and typed by hand for older ones.

### NGC, PCGS and Greysheet wholesale values from Greysheet
- The API already returns `NgcVal`, `PcgsVal`, `GreyVal` and `BlueBookVal`, but they're empty on our tier.
  Greysheet says: "An active Dealer+ or Pro subscription is required for Advanced API Access."
- If we get Advanced access: show them on the coin page next to CPG (small change; the fields are already parsed
  for `GreyVal`).

### "Add to TrackMyCoins" bookmark for NGC
- Built and switched off (`NGC_BOOKMARK_ENABLED` in `frontend/src/ngcButton.ts`). Desktop flow felt clunky.
- Planned refinement: one-tab round trip (save the form, open NGC in the same tab with cert + grade, the bookmark
  brings the tab back filled in). NGC's Cloudflare check cuts `window.opener`, so a two-tab hand-off won't work.

### eBay sold prices
- Needs eBay's Marketplace Insights API (limited release; apply through eBay developer support).
- The "For sale on eBay now" card (Browse API, asking prices) is built and hidden until `EBAY_CLIENT_ID` /
  `EBAY_CLIENT_SECRET` are set; it appears automatically once they are.

### Forgot password by email
- Plan: reset tokens (hashed, 1-hour expiry), email via Resend, rate-limited request endpoint.
- Needs a Resend account and DNS records for trackmycoins.app on Cloudflare.

### Off-site backups (more important now that others use the site)
- Today: Fly keeps 5 daily snapshots of the volume, but they live with Fly, not off-site.
- Plan: nightly SQLite backup + photos to Cloudflare R2 (S3 API), run lazily since the Fly machine auto-stops.
- Needs an R2 bucket and access keys. R2 is also a cheaper home for photos than the Fly volume.

### Weekly email digest
- Portfolio change, price movers, want-list matches. Needs the same email setup as "Forgot password" (Resend +
  DNS on Cloudflare), so build the two together.

### QR code stickers
- Printable QR stickers (e.g. for flips or slab sleeves) that open the coin's page. Only the owner (logged in) would
  see the coin; consider what a stranger scanning one should see.

### Storage location (back burner)
- Where each coin is kept (home safe, bank box). Probably unpopular: many collectors don't want to record where their
  stack is; the Notes field covers anyone who does.

### Historical spot prices (gold, silver, platinum)
- Today the app only knows the current spot price (gold-api.com). Daily history would show what bullion was
  worth when bought, chart a stack's value over time, and give past melt values for numismatic coins.
- Options: a metals-price API with daily history (free/cheap tiers) or the LBMA daily fix. Check current terms,
  limits and cost before choosing.
- Decide when designing the Bullion collection; that feature depends on it.

### Numista catalog
- Free API (needs a key; monthly request limit) with type photos, mintages, weight and metal content, and
  many bullion rounds and bars.
- Uses: a product catalog to pick bullion items from; real type photos in place of the placeholder artwork on
  coins without photos; a starting point for world coins later.
- Decide alongside the Bullion collection design. Check current API terms first.

## Ideas

- **Single-use invite codes** with a list of who joined with which code (today one shared code works for everyone).
- **PCGS auction chart** text is small on phones (the value chart was fixed by drawing at screen width; same fix).
