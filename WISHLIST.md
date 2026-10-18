# TrackMyCoins wish list

Features we've talked about and put on hold, with what we learned so they're quick to pick up again.

## Up next (agreed order)

1. Install on phone (installable web app: icon, full screen).
2. Rapid batch add (scan slab after slab into a queue, review, save all).

(Bullion collections, the Precious Metals page, Grading Tracker, ICG, Storage, error coins and the Add Coin search
were built 2026-10-18. Install on phone is on hold.)

## Seller tools (eBay / Whatnot / TikTok Shop)

Agreed 2026-10-18 to keep these on their own list. **If built, they're switched on per user in Account settings
(off by default)**, so collectors who don't sell never see the extra menus, columns, buttons or dashboard cards.
Suggested order: 1 → 2 → 4 (with Connect eBay) → 5.

1. **Selling status and channels.** Per coin and bullion item: Listed on eBay / Whatnot / TikTok (listing link, price,
   date) → Sold → Shipped. Warn about double selling (listed in two places, sold in one). Aging list (listed 30/60/90
   days; CPG moved since listing).
2. **Fees and net, profit by platform.** Each platform's fee rates set once (they change; no hard-coded rates).
   "Sells for $X on Whatnot: you net $Y after fees, shipping and supplies." Gross, fees, cost of goods and net by
   platform, month and year.
3. *(not chosen yet)* Bought-a-lot cost split: spread a lot's price across its coins (evenly, by CPG, or by hand).
4. **Listing kit, then Connect eBay.**
   - Kit: eBay title under 80 characters ("1881-S Morgan Silver Dollar PCGS MS65 CAC"), item specifics, description,
     photos, copy buttons; Whatnot bulk-upload CSV and eBay bulk-listing file for chosen coins (no API needed).
   - Connect eBay (OAuth, user consent on eBay's own sign-in; we never see passwords): **List on eBay** from the coin
     page with a preview → Inventory API (inventory item by SKU = inventory #, offer, publish). Category from the
     series, item specifics via Taxonomy API, seller's shipping / payment / return policies via Account API,
     suggested price and net after fees on the preview. Coin then shows Listed on eBay with the link.
   - Needs: a RuName (redirect) in the eBay developer portal for sandbox and production →
     `https://trackmycoins.app/api/ebay/connect/callback`; refresh tokens (~18 months) stored encrypted, with
     disconnect; photos uploaded to eBay or given as short-lived private links (ours are behind login); sellers need
     eBay Business Policies on; build and test in the sandbox first.
   - Once we store eBay tokens, the Marketplace Account Deletion endpoint (`/api/ebay/account-deletion`, built
     2026-10-18, currently acknowledge-only) must delete that user's eBay connection.
   - eBay's "create a draft, finish on eBay" (Sell Listing API) seems to be limited access; plan on full listings
     with a final confirm step.
5. **Live show planner (Whatnot / TikTok Live).** Pick coins for a stream: order, starting bid and floor (from cost
   and CPG); phone-friendly run sheet during the show; afterwards enter hammer prices and buyers, which marks them
   sold with fees worked out. Giveaways and breaks tracked as cost/marketing. Pairs with printed inventory # / QR
   labels for pulling coins fast.

Other seller ideas mentioned: suggested Buy It Now / starting bid from CPG and comps; photo helpers (square crops,
obverse + reverse side by side, watermark); buyer want lists matched to new inventory; consignment (split, payout
owed); ship-by list (packaging, tracking, insurance); tax-time report (sales by platform vs 1099-K, cost of goods,
short- vs long-term). Platform APIs: eBay is documented and we have keys; TikTok Shop has an API with app approval;
no broadly open Whatnot seller API that we know of, so CSV upload there.

## On hold

### Greysheet price history (to improve "Est. value at purchase")
The estimated value at purchase is built (2026-10-17): own figure, else CPG within 2 months of purchase, else
TrackMyCoins' own CPG history, else the average of PCGS auction sales near the purchase date, else price paid.
Real CPG history from Greysheet would replace the auction step for older purchases.
- Greysheet's website shows CPG, NGC and PCGS price history per coin, but the API we use has no history: no call
  takes a date and none return past values (checked 2026-10-17).
- Next step: ask support@greysheet.com whether Dealer+/Pro API access includes historical values, how far back,
  and whether a website subscription can be linked to our API key.

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
- The "For sale on eBay now" card (Browse API, asking prices) is built and hidden until the eBay keys are set.
  Keys are now in `.env` as `EBAY_APP_ID_*` / `EBAY_CERT_ID_*` (sandbox and production); the app still reads
  `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET`, so switch it to the new names when the eBay box work starts.

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

### Dealer buy-back estimate for bullion
Show what a dealer would likely pay (below melt) next to melt value. No major U.S. dealer (APMEX, JM Bullion,
SD Bullion) has a public API (checked 2026-10-18).
- Simplest: a buy-back percentage per metal set by the owner (e.g. silver spot -3%, gold -1.5%).
- Market data: goldprice.dev's physical-prices endpoint has dealer sell and buyback quotes with premium over
  spot (22 countries incl. US) on its $19/month Basic plan; it doesn't name the U.S. dealers or products, and
  says redistribution needs a reseller plan, so ask hello@goldprice.dev before showing quotes in the app.
- Avoid scraping dealer sites (Apify scrapers exist): against their terms and brittle.
- Stack Heavy (a website, no API) tracks retail premiums only; FindBullionPrices has no public API.

### Numista catalog
- Free API (needs a key; monthly request limit) with type photos, mintages, weight and metal content, and
  many bullion rounds and bars.
- Uses: a product catalog to pick bullion items from; real type photos in place of the placeholder artwork on
  coins without photos; a starting point for world coins later.
- Decide alongside the Bullion collection design. Check current API terms first.

## Ideas

- **Single-use invite codes** with a list of who joined with which code (today one shared code works for everyone).
- **PCGS auction chart** text is small on phones (the value chart was fixed by drawing at screen width; same fix).
