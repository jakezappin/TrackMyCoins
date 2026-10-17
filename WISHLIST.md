# TrackMyCoins wish list

Features we've talked about and put on hold, with what we learned so they're quick to pick up again.

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

### Off-site backups
- Plan: nightly SQLite backup + photos to Cloudflare R2 (S3 API), run lazily since the Fly machine auto-stops.
- Needs an R2 bucket and access keys. R2 is also a cheaper home for photos than the Fly volume.

## Ideas

- **Price by grade table** on the coin page: one Greysheet call already returns every grade (and CAC) for a coin,
  so a ladder like "MS62 $115 · MS63 $130 · MS64 $165" costs no extra API calls.
- **Single-use invite codes** with a list of who joined with which code (today one shared code works for everyone).
- **Coin list as cards on phones** instead of a sideways-scrolling table.
- **PCGS auction chart** text is small on phones (the value chart was fixed by drawing at screen width; same fix).
