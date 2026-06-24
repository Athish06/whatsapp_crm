# WhatsApp CRM — Full Project Status Audit Report
**Date:** 2026-06-24 | **Audited by:** Antigravity AI

This report audits EVERY file in the project against the `implementation_plan.md` and gives you an honest, unfiltered view of what works, what doesn't, and what you still need to do. Read every section carefully.

---

## Section 1: What Your App Does (Complete Feature Map)

Your app is a WhatsApp CRM for local supermarket owners. The complete flow is:

1. **Owner registers / logs in** → JWT-based auth with cookie session
2. **Creates a shop** → Monthly or Weekly upload cycle
3. **Uploads 3 CSV files** → Customers, Products, Transactions
4. **System auto-classifies** → RFM+B segmentation into 5 tiers
5. **Creates WhatsApp templates** → Personalized with behavioral placeholders
6. **Creates offers** → Discount offers linked to products/segments
7. **Creates a campaign** → Selects segments + templates + offers
8. **System schedules messages** → Per-priority batches with time gating
9. **Scheduler sends messages** → Via WhatsApp Web (Playwright) or Mock
10. **Owner monitors progress** → Monitoring page with drill-down stats

---

## Section 2: Phase-by-Phase Audit vs. Implementation Plan

### ━━━ Phase 1: MongoDB Schema Refinement ━━━
**STATUS: ✅ DONE**

- ✅ Collections consolidated from 12 → 8 clean collections: `users, shops, files, customers, products, transactions, customer_insights, templates, campaigns, batches, messages, offers`
- ✅ `msg_queues` collection REMOVED — `messages` is the single source of truth
- ✅ `campaign_batches` collection REMOVED — merged into `campaigns`
- ✅ `offers` collection ADDED — full schema with product_ids, target_segments, etc.
- ✅ `upload_cycle` added to shops (monthly/weekly)
- ✅ `period_tag` added to files and transactions
- ✅ `content_hash` (SHA-256 dedup) added to files
- ✅ `campaign_id` added directly on each message doc
- ✅ `offer_id` added to message docs
- ✅ `failure_reason` + `error_log` added to messages
- ✅ `previous_segment` + `segment_changed` added to `customer_insights`

### ━━━ Phase 2: Duplicate Prevention & Period Tagging ━━━
**STATUS: ✅ MOSTLY DONE (one known gap)**

- ✅ `file_service.py`: SHA-256 hash computed before upload
- ✅ Duplicate file detection: if same hash exists, returns `duplicate:true`, skips re-upload
- ✅ `period_tag` auto-computed from shop's `upload_cycle` and current date
- ✅ `transaction_service.py`: uses `delete_many(shop_id + period_tag)` NOT all shop data
  *(This means uploading June data then July data KEEPS June data - fixed historical bug)*
- ✅ `product_service.py`: uses upsert on `(shop_id, product_id)` — products accumulate
- ✅ `can_reprocess` flag added to allow force re-processing same hash

> [!NOTE]
> **GAP 1:** The `period_tag` is computed correctly on upload, but if the same period's data is re-uploaded (e.g., corrected June data), it deletes that period's transactions and re-inserts. This is intended behavior but worth knowing.

> [!NOTE]
> **GAP 2:** Transaction row-level dedup (unique compound index on shop_id + customer_id + product_id + purchase_date + purchase_qty + total_amount) — the INDEX exists in `database.py` BUT the insert code uses `delete_many(period_tag)` THEN `insert_many`, so the index is a safety net but not the primary dedup mechanism. This is fine.

### ━━━ Addendum A: Cross-Upload Customer Dedup & Cumulative Classification ━━━
**STATUS: ✅ DONE**

- ✅ transactions now accumulate across months (the big bug is fixed)
- ✅ `previous_segment` stored in `customer_insights` before each recalculation
- ✅ `segment_changed` flag computed correctly
- ✅ `recalculate_all_insights()` runs on ALL historical transactions (not just latest)

### ━━━ Addendum B: Classification Logic Refinement ━━━
**STATUS: ⚠️ PARTIALLY DONE**

- ✅ `previous_segment` + `segment_changed` fields: DONE
- ✅ At-risk churn velocity (was VIP, R dropping): DONE in `insights_service.py`
- ✅ VIP relaxation with `f_score==5` override: DONE in `insights_service.py`

- ❌ **NOT DONE:** `new_customer` segment (`purchase_count <= 2 AND recency_days <= 30`)
  *The plan says add a "new_customer" pre-waterfall escape rule, but the `classifier.py` waterfall does NOT have this rule. New customers are still classified as "boring".*
- ❌ **NOT DONE:** Frontend display "Occasional" instead of "Boring"
  *The frontend still shows "boring" as-is in `ShopDashboardPage.js`.*
- ❌ **NOT DONE:** `CustomerCategory` enum in `models.py` does NOT have `NEW_CUSTOMER` value.

> [!IMPORTANT]
> **IMPACT:** New customers who just joined get "boring" treatment. Not a show-stopper but it's a quality issue for a supermarket CRM.

### ━━━ Phase 3: Offers System ━━━
**STATUS: ✅ DONE**

- ✅ `offers_service.py`: Full CRUD (create, list, get, update, soft-delete)
- ✅ `offers.py` routes: POST, GET, GET/match, PUT, DELETE — all registered
- ✅ Composite Affinity Rank engine: matches customers to best offer using `Affinity(c, o) = S(c,o) × [1 + P(c,o)]` with `W_PRODUCT=3.0`, `W_CATEGORY=1.0`
- ✅ `offer_match_map` runs at campaign creation time in `batch_service.py`
- ✅ offer placeholders hydrated: `{{offer_title}}`, `{{offer_discount}}`, `{{offer_product}}`
- ✅ `OffersPage.js`: Full CRUD UI — create/edit/delete offers with segment picker
- ✅ `offer_id` stored on each message doc

> [!NOTE]
> **MINOR 1:** `OffersPage.js` product picker shows product names but the DB "products" collection may be empty if products were uploaded before the `product_inventory` → `products` migration was fixed today.
> **MINOR 2:** The backend GET `/shops/{shop_id}/products` route was MISSING until today when we added it. Products couldn't load in the offers UI before.

### ━━━ Phase 4: Real WhatsApp Web Message Sender ━━━
**STATUS: ⚠️ BUILT BUT NOT ACTIVATED — NEEDS YOUR ACTION**

This is the most important section. Read it carefully.

**WHAT'S BUILT:**
- ✅ `whatsapp_sender.py`: Full Playwright-based WhatsApp Web automation
  - Persistent browser context (saves to `./whatsapp_profile` folder)
  - QR code scan required only ONCE — saved forever after
  - URL-based message delivery: `web.whatsapp.com/send?phone=&text=`
  - Waits for `button[aria-label="Send"]` then clicks it
  - Detects "invalid number" error automatically
  - Daily message counter (MAX 200/day)
  - Working hours gate: 9AM-7PM IST (**CURRENTLY DISABLED for testing**)
  - Consecutive failure rate-limit detection (5 failures → `rate_limit`)
- ✅ `provider_adapter.py`: ProviderAdapter pattern with 3 modes:
  - `mock`: 95% success rate simulation (currently active)
  - `whatsapp_web`: Real Playwright sender
  - `twilio`: Stub (not implemented)
- ✅ `scheduler_service.py`: APScheduler polls every 7 seconds
  - Picks up to 8 pending messages per cycle
  - Calls `ProviderAdapter.send_message()` for each
  - 3.5-5.0s human-like jitter between messages
  - 15-30s batch cooldown between groups

**CURRENT STATUS:**
- 🔴 `PROVIDER_MODE=mock` in `.env` — it is NOT sending real WhatsApp messages
- 🔴 WhatsApp Web sender is BUILT but DORMANT
- 🔴 Working hours gate DISABLED (commented out for testing) — re-enable for prod

> [!TIP]
> **HOW TO ACTIVATE REAL SENDING:**
> 1. Open `backend/.env`
>    Change: `PROVIDER_MODE=mock`
>    To: `PROVIDER_MODE=whatsapp_web`
> 2. Make sure Playwright Chromium is installed:
>    In terminal: `python -m playwright install chromium`
> 3. Restart the backend server (`python server.py`)
>    On first startup it will call `sender.start()` in a background task
> 4. A Chrome window will open automatically and go to WhatsApp Web. **SCAN THE QR CODE with your phone — this only happens ONCE.** After scanning, the session is saved in `backend/whatsapp_profile/`. Future restarts will auto-login without QR scan.
> 5. Create a test campaign with 1 customer → trigger it. Watch the backend logs for `[WhatsAppSender]` messages.

**WHAT COULD GO WRONG:**
- WhatsApp Web UI changes: The CSS selectors (`button[aria-label="Send"]`) may break if Meta updates the WhatsApp Web interface. This is the #1 risk.
- You MUST have WhatsApp Web open and logged in on the machine running the server.
- The phone number format must include country code: `+919876543210`.
- WhatsApp has informal limits (~200 messages/day for personal accounts). Business API accounts have higher limits but require Meta approval.
- If you run the backend without a display (headless server), Playwright needs `WHATSAPP_HEADLESS=true` in `.env` — but headless Chrome has issues with WhatsApp.

### ━━━ Phase 5: Monitoring System ━━━
**STATUS: ✅ DONE**

- ✅ `monitoring_service.py`: Full monitoring with:
  - `get_campaign_overview()`: All campaigns with stats
  - `get_campaign_detail()`: Campaign + batches + message counts
  - `get_batch_detail()`: All messages in a batch with error details
  - `get_failed_messages()`: Failed messages grouped by failure reason
  - `reschedule_failed()`: Smart reschedule (rate_limit→next 9AM, network→5min)
  - `get_period_summary()`: Period-wise (monthly/weekly) campaign stats
- ✅ `monitoring.py` routes: All 6 endpoints registered
- ✅ `MonitoringPage.js`: Full monitoring UI with:
  - Campaign list with progress bars
  - Campaign detail drill-down
  - Batch detail with individual message statuses
  - Failed messages panel with Reschedule button
  - Auto-refresh every 30s
  - Period filter

### ━━━ Phase 6: Frontend Pages ━━━
**STATUS: ✅ MOSTLY DONE**

- ✅ `OffersPage.js`: CRUD UI — create/edit/delete offers
- ✅ `MonitoringPage.js`: Full monitoring dashboard
- ✅ `ShopDashboardPage.js`: upload_cycle selector, period tag display, Offers link
- ✅ `CampaignCreatorPage.js`: offer selection step, `{{offer_*}}` placeholder help
- ✅ `App.js`: Routes for `/shop/:id/offers` and `/shop/:id/monitoring`
- ✅ `Sidebar.js`: Navigation links

- ❌ **NOT DONE:** `TemplatesPage` segment-transition-aware template suggestions (showing "We miss you Ravi" style for VIP→AtRisk transitions)
- ❌ **NOT DONE:** "Occasional" display label for "boring" segment
- ❌ **NOT DONE:** "New Customer" badge / segment in frontend

### ━━━ Phase 7: Server & Integration ━━━
**STATUS: ✅ DONE**

- ✅ `server.py`: All routers registered
- ✅ WhatsApp Web sender initialized on startup when `PROVIDER_MODE=whatsapp_web`
- ✅ `migrations.py` runs on startup: `product_inventory` → `products` rename
- ✅ APScheduler starts on server boot
- ✅ Graceful shutdown: scheduler stopped, WhatsApp sender stopped, DB disconnected
- ✅ `requirements.txt`: `playwright>=1.42.0` added (`pywhatkit` removed)

### ━━━ Testing Status ━━━
**STATUS: ❌ ZERO TESTS WRITTEN — COMPLETE GAP**

From the plan's Verification section, NONE of these have been done:
- ❌ Schema dedup test: upload same CSV twice → verify no duplicates
- ❌ Period tagging test: verify `period_tag = "2026-06"` on upload
- ❌ Offer matching test: create offer for VIP → verify correct customers
- ❌ Working hours test: mock time outside 9-7 → verify scheduler skips
- ❌ Rate limit test: simulate `rate_limit` → verify auto-reschedule
- ❌ pytest suite: no test files exist anywhere in the project
- ❌ Manual verification of complete flow end-to-end with real WhatsApp

---

## Section 3: Complete Env Variables Reference

Your current `backend/.env` has:

**REQUIRED (already set ✅):**
```env
MONGO_URL=mongodb+srv://...       # Your Atlas cloud MongoDB
DB_NAME=whatsapp_crm
JWT_SECRET_KEY=...                # Auto-generated secure key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080 # 7 days login session
CORS_ORIGINS=http://localhost:3000,...
DEBUG=True
SENDER_EMAIL=...                  # Gmail for OTP emails
GOOGLE_APP_PASSWORD=...           # Gmail App Password (not your real password)
B2_APPLICATION_KEY_ID=...         # Backblaze B2 file storage
B2_APPLICATION_KEY=...
B2_BUCKET_NAME=whatsapp-crm
B2_BUCKET_ID=...
```

**NEEDS CHANGE FOR REAL SENDING ❗:**
```env
PROVIDER_MODE=mock                # CHANGE TO: whatsapp_web
```

**OPTIONAL (not currently in .env, uses defaults):**
```env
WHATSAPP_HEADLESS=false           # Set to true for server without display
WHATSAPP_MAX_PER_DAY=200          # Max messages per day limit
```

---

## Section 4: Your Old `whatsapp.py` — What Is It?

The file at root: `whatsapp_crm/whatsapp.py` is your ORIGINAL script. It uses `pywhatkit` + `pyautogui` — the old, unreliable approach.

**HOW IT WORKS (old script):**
- `pywhatkit.sendwhatmsg_instantly()` opens WhatsApp Web in browser
- `pyautogui.press('enter')` simulates a keyboard press to send
- `pyautogui.hotkey('ctrl', 'w')` closes the browser tab after sending
- It's a STANDALONE script — manually run it from terminal
- It is NOT connected to the CRM backend at all

**WHY WE REPLACED IT:**
- `pywhatkit` is unreliable — sometimes fails to press Enter
- `pyautogui` can't handle screen scaling issues (HiDPI monitors)
- It opens/closes browser tabs which is slow and janky
- No error detection (can't tell if number is invalid)
- No session persistence (reopens WhatsApp Web every time)
- Completely manual — no scheduler integration

**THE NEW APPROACH (`whatsapp_sender.py`):**
- Uses Playwright (Microsoft's browser automation library)
- Persistent browser context — logs in ONCE, stays logged in
- Uses URL-based sending: `wa.me` redirect approach
- Proper wait for UI elements before clicking
- Detects invalid numbers via DOM check
- Integrated with the scheduler — fully automatic
- Error handling, retry logic, rate limit detection

> [!TIP]
> **STATUS:** `whatsapp.py` is DEAD CODE — can be deleted. The new system is in `backend/services/whatsapp_sender.py`.

---

## Section 5: Honest System Health Assessment

Is your system congested / in good health? Honest answer:

### Architecture: 7/10
The architecture is SOLID for a college project and surprisingly mature. You have: JWT auth, MongoDB Atlas (cloud), Backblaze B2 (cloud storage), APScheduler (background jobs), Playwright (browser automation), React frontend. The layering is good: `routes` → `services` → `DB`.

### Code Consistency: 6/10
You've had a persistent problem with import errors crashing the React app (ArrowLeft, Users, Settings, Link all missing at various points). This tells me the development process had some messy cleanup phases where icons were removed and not tracked.
The `product_inventory` → `products` rename was incomplete — several services were still pointing to the old collection name until today. This is exactly the kind of consistency problem that causes "works on my machine" bugs.

### Database Design: 8/10
Actually quite good! The schema is well thought out. The single-source-of-truth pattern for `customer_insights` is smart. The `period_tag` system for accumulating data across months is correct. The offer affinity engine math is proper.

### Scheduler: 8/10
The APScheduler + state machine approach is solid. The atomic concurrency lock (checking `modified_count` before processing) prevents duplicate sends. The exponential retry with jitter is correct. The rate-limit bulk-reschedule is a nice touch.

### WhatsApp Sender: 5/10 (incomplete activation)
The code is written and correct in theory. BUT:
- It's never been tested with a real phone number end-to-end
- The selector `'button[aria-label="Send"]'` may or may not work on current WhatsApp Web (Meta changes the UI regularly)
- The `wa.me` redirect approach (URL with phone+text) is the most reliable method but still requires the WhatsApp Web page to fully load
- If WhatsApp Web adds anti-automation detection, Playwright could get blocked

### Frontend: 7/10
The UI is functional and well-styled (dark theme, Lucide icons, Sonner toasts). The pages are connected properly via React Router. The API layer (`lib/api.js`) is clean with Axios interceptors.

### OVERALL ASSESSMENT: 6.5/10 — Nearly Production Ready
The core product works. Data flows from CSV → Classification → Campaign → Messages → Scheduler. The missing piece is actual WhatsApp message delivery (currently mock). With `PROVIDER_MODE=whatsapp_web` and a QR scan, it should theoretically work — but it has NEVER been tested end-to-end with a real phone.

---

## Section 6: What's Missing / Not Done (Prioritized)

🔴 **CRITICAL (blocks real usage):**
1. Working hours gate is disabled — RE-ENABLE before production:
   - File: `backend/services/scheduler_service.py` line ~120
   - File: `backend/services/whatsapp_sender.py` line ~115
   *(Just un-comment the "return" lines).*
2. `PROVIDER_MODE` is still "mock" — real messages not sending. Change to `"whatsapp_web"` in `backend/.env`.
3. End-to-end WhatsApp test not done. You don't know if the Playwright sender actually works until you try it with a real phone number.

🟡 **IMPORTANT (degrades quality):**
4. `new_customer` segment not implemented. New first-time customers still get "boring" classification.
   *(Fix: Add rule 0 in `insights_service.py` waterfall function).*
5. "Occasional" display label for "boring" not done in frontend.
6. Frontend may have more hidden icon import issues (Run: `npm start` and look for any compilation warnings).
7. The `products` collection may be empty if product CSV was uploaded before today's fix. Re-upload your product CSV to populate it.

---

## Section 7: How to Make the Real WhatsApp Sender Work

### Step-by-Step Guide:

**Step 1: ENABLE REAL MODE**
Open: `backend/.env`. Change: `PROVIDER_MODE=mock` To: `PROVIDER_MODE=whatsapp_web`. Save the file.

**Step 2: INSTALL PLAYWRIGHT BROWSER**
Open terminal in backend folder: `python -m playwright install chromium`. This downloads Chromium browser to AppData.

**Step 3: RE-ENABLE WORKING HOURS (for production)**
In `scheduler_service.py` around line 120, un-comment "return". In `whatsapp_sender.py` around line 115, un-comment the working hours check.

**Step 4: RESTART THE BACKEND**
`python server.py`. Watch the logs — you should see:
`[WhatsAppSender] Starting Playwright persistent context...`
`[WhatsAppSender] Navigating to WhatsApp Web. Please scan QR if needed.`

**Step 5: SCAN THE QR CODE**
A Chrome browser window will open automatically on your machine. Open WhatsApp on your phone → Linked Devices → Link a Device. Scan the QR code. DONE — this only happens once. The session is saved in `backend/whatsapp_profile/`.

**Step 6: TEST WITH ONE CUSTOMER**
Create a test campaign with just 1 customer (yourself). Schedule it for "now". Watch backend logs for:
`[WhatsAppSender] ✓ Sent to +91XXXXXXXXXX (sid=wa_...)`

**Step 7: CHECK FOR ERRORS**
- If you see **"Timeout waiting for send button"**: WhatsApp Web's UI may have changed. Inspect the Send button in Chrome DevTools and update the selector in `whatsapp_sender.py`. Current selector: `'button[aria-label="Send"]'`.
- If you see **"playwright_not_running"**: The `sender.start()` task may have failed silently. Add more logging or call `await sender.start()` directly.
- If you see **"invalid_number"**: The phone number format is wrong. Must be `+919876543210` (with +91 prefix).

---

## Section 8: Complete File Inventory

**BACKEND (`/backend`):**
- `server.py` ✅ Complete — all routers, startup/shutdown, migrations
- `migrations.py` ✅ product_inventory → products migration
- `requirements.txt` ✅ All deps including playwright
- `.env` ⚠️ `PROVIDER_MODE` needs change for real sending
- **/routes:**
  - `auth.py` ✅ Login, register, OTP, forgot password, refresh
  - `shops.py` ✅ CRUD + file upload + products endpoint
  - `customers.py` ✅ Upload, map columns, list, insights
  - `templates.py` ✅ CRUD for message templates
  - `batches.py` ✅ Create campaign, pause, resume, cancel
  - `files.py` ✅ Upload, detect columns, list files
  - `offers.py` ✅ Full CRUD + match preview
  - `monitoring.py` ✅ Campaign/batch/message drill-down
  - `dashboard.py` ✅ Queue stats
- **/services:**
  - `auth_service.py` ✅ JWT, OTP via Gmail, password reset
  - `shop_service.py` ✅ Fixed today (Atomic Cascading Cleanup)
  - `customer_service.py` ✅ Fixed today (Recalculate trigger isolated)
  - `product_service.py` ✅ Fixed today (product_inventory→products)
  - `transaction_service.py` ✅ Fixed today (period-scoped delete)
  - `insights_service.py` ✅ Fixed today (products), RFM+B computation
  - `batch_service.py` ✅ Campaign creation, message hydration, offer matching
  - `scheduler_service.py` ⚠️ Working hours DISABLED for testing
  - `whatsapp_sender.py` ⚠️ Built but never tested end-to-end
  - `provider_adapter.py` ✅ Adapter pattern (mock/whatsapp_web/twilio)
  - `offers_service.py` ✅ Full CRUD + affinity engine
  - `monitoring_service.py` ✅ Stats, drill-down, reschedule
  - `template_service.py` ✅ CRUD
  - `file_service.py` ✅ SHA-256 dedup, B2 upload, period tag
  - `dashboard_service.py` ✅ Queue stats aggregation
- **/schemas:**
  - `models.py` ✅ All Pydantic models (offers, shops, batches, etc.)
- **/utils:**
  - `classifier.py` ⚠️ 5-tier waterfall
  - `level2_profiler.py` ✅ Behavioral profiling (8 template variables)

**FRONTEND (`/frontend/src`):**
- `App.js` ✅ All routes registered
- **/pages:**
  - `LoginPage.js` ✅ Auth form with animations
  - `ForgotPasswordPage.js` ✅ OTP flow
  - `DashboardPage.js` ✅ Shop list
  - `ShopDashboardPage.js` ✅ Full shop detail, stats, upload
  - `CampaignCreatorPage.js` ✅ Multi-step campaign creation with offers
  - `TemplatesPage.js` ✅ Template CRUD with variable helper
  - `OffersPage.js` ✅ Offer CRUD with segment + product picker
  - `MonitoringPage.js` ✅ Campaign monitoring dashboard
  - `BatchMonitorPage.js` ✅ Legacy batch monitor (kept for compat)
- **/components:**
  - `Sidebar.js` ✅ Navigation with Offers + Monitoring links
- **/lib:**
  - `api.js` ✅ Axios instance + all API helper objects

**ROOT:**
- `whatsapp.py` ❌ **DEAD CODE** — old pywhatkit script, not integrated
- `implementation_plan.md` ✅ Reference document
- `test_csv` ✅ Sample CSV data for testing
