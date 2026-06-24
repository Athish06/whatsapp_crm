# WhatsApp CRM — Complete Overhaul & Feature Implementation Plan

## Problem Summary

The WhatsApp CRM for local supermarkets needs a **complete data pipeline overhaul** covering: refined MongoDB schema (no duplicates), proper data period tagging (monthly/weekly), an **Offers system** linked to customer preferences, a **real WhatsApp Web message sender** (replacing the mock), a **monitoring dashboard** with auto-reschedule + working hours enforcement (9AM–7PM IST), and a refined end-to-end flow from shop creation to message delivery.

---

## Current State Analysis

### What Exists & Works
- ✅ Shop CRUD, 3-layer CSV upload (customers, products, transactions)
- ✅ RFM+B classification (VIP, At-Risk, Potential Bulk, Loyal Frequent, Boring)
- ✅ Level 2 behavioral profiling (8 template variables)
- ✅ Template system with placeholder hydration
- ✅ Batch/campaign creation with segment-based template routing
- ✅ Basic retry logic (3 retries, then `failed_permanently`)

### What's Broken / Missing
- ❌ **12 collections** in DB — too many, overlapping (`messages` + `msg_queues` + `campaign_batches`)
- ❌ No duplicate CSV prevention (re-uploading same file replaces all data)
- ❌ No period tagging (monthly/weekly) on uploaded data
- ❌ No **Offers** system — templates exist but no structured offer→product→customer linking
- ❌ Message sending is **mock** (`random.random() < 0.95`) — not real WhatsApp Web
- ❌ No monitoring dashboard (which batch succeeded, which message failed, why)
- ❌ No working hours enforcement (9AM–7PM IST)
- ❌ No auto-reschedule on WhatsApp rate limit
- ❌ No owner notification on permanent failures
- ❌ `whatsapp.py` uses `pywhatkit` (separate script) — not integrated with backend

---

## Open Questions

> [!IMPORTANT]
> **Q1: Upload Frequency** — When creating a shop, should the owner choose "monthly" or "weekly" upload cycle upfront? Or should this be changeable later? *(Plan assumes: set at shop creation, editable later)*

> [!IMPORTANT]
> **Q2: WhatsApp Web Automation** — You're using `pywhatkit` + `pyautogui` for WhatsApp Web. This requires the backend machine to have a browser open with WhatsApp Web logged in. Is that acceptable? The backend will run a Selenium/Playwright-based sender instead of pywhatkit for reliability. *(Plan assumes: yes, single machine with browser)*

> [!IMPORTANT]
> **Q3: Offer Granularity** — Should offers be linked per-product (e.g., "20% off Basmati Rice") or per-category (e.g., "15% off all Groceries")? *(Plan assumes: per-product offers, with optional category-wide offers)*

> [!IMPORTANT]  
> **Q4: Frontend Scope** — Should I build new frontend pages for Offers management and the Monitoring dashboard in this plan, or backend-only first? *(Plan assumes: full stack — backend + frontend)*

---

## Proposed Changes

### Phase 1: MongoDB Schema Refinement

**Goal:** Consolidate 12 collections → 8 clean collections. Eliminate duplicates. Add period tagging.

#### Current Collections (12) → Refined (8)

| # | Current | Action | Refined |
|---|---------|--------|---------|
| 1 | `users` | Keep as-is | `users` |
| 2 | `shops` | Add `upload_cycle` field | `shops` |
| 3 | `files` | Add `period_tag`, content hash dedup | `files` |give
| 4 | `customers` | Keep identity-only | `customers` |
| 5 | `product_inventory` | Rename → `products` | `products` |
| 6 | `transactions` | Add `period_tag`, dedup on composite key | `transactions` |
| 7 | `customer_insights` | Keep (single source of truth for RFM) | `customer_insights` |
| 8 | `templates` | Keep | `templates` |
| 9 | `campaigns` | Keep, absorb campaign_batches | `campaigns` |
| 10 | `batches` | Keep | `batches` |
| 11 | `messages` | Keep, absorb msg_queues fields | `messages` |
| 12 | `msg_queues` | **DELETE** — merge into messages | *(removed)* |
| 13 | `campaign_batches` | **DELETE** — merge into campaigns | *(removed)* |
| — | *(new)* | **ADD** | `offers` |

#### Refined Schema Documents

**`shops` — Add upload cycle + period tracking**
```json
{
  "id": "uuid",
  "user_id": "ref",
  "shop_name": "Anbu Super Market",
  "upload_cycle": "monthly",        // NEW: "monthly" | "weekly"
  "created_at": "ISO datetime"
}
```

**`files` — Content-hash dedup + period tag**
```json
{
  "_id": "ObjectId",
  "user_id": "ref",
  "shop_id": "ref",
  "data_purpose": "customer_data | product_data | transaction_data",
  "original_file_name": "sales_june.csv",
  "file_name": "uuid_sales_june.csv",
  "file_url": "https://b2...",
  "file_size": 48839,
  "content_hash": "sha256_hex",     // NEW: SHA-256 of file bytes → exact duplicate detection
  "period_tag": "2026-06",          // NEW: "2026-06" (monthly) or "2026-06-W3" (weekly)
  "row_count": 1500,                // NEW: for quick stats
  "uploaded_at": "ISO datetime"
}
```
**Dedup logic:** Unique index on `(user_id, shop_id, data_purpose, content_hash)`. If same hash exists → return existing file_id + `duplicate: true`, skip re-processing.

**`transactions` — Composite dedup**
```json
{
  "transaction_id": "uuid",
  "shop_id": "ref",
  "customer_id": "ref (from CSV)",
  "product_id": "ref",
  "category": "Grocery",
  "purchase_date": "ISODate",
  "purchase_qty": 5,
  "total_amount": 450.0,
  "period_tag": "2026-06",          // NEW: inherited from file upload
  "uploaded_at": "ISO datetime"
}
```
**Dedup:** Unique index on `(shop_id, customer_id, product_id, purchase_date, purchase_qty, total_amount)`. Prevents re-inserting identical rows from same CSV.

**`offers` — NEW collection**
```json
{
  "id": "uuid",
  "shop_id": "ref",
  "user_id": "ref",
  "title": "Summer Rice Sale",
  "description": "Get 20% off on premium Basmati Rice",
  "discount_type": "percentage",     // "percentage" | "flat" | "bogo"
  "discount_value": 20,
  "product_ids": ["P001", "P005"],   // linked products (can be empty for category-wide)
  "category": "Grocery",             // optional: category-wide offer
  "target_segments": ["vip", "loyal_frequent"],  // which customer segments get this
  "valid_from": "2026-06-15",
  "valid_until": "2026-06-30",
  "is_active": true,
  "created_at": "ISO datetime"
}
```

**`messages` — Absorb msg_queues fields, add monitoring fields**
```json
{
  "id": "uuid",
  "batch_id": "ref",
  "campaign_id": "ref",             // NEW: direct ref (was only on batch)
  "customer_id": "ref",
  "phone_number": "+919876543210",
  "customer_name": "Ravi",
  "customer_segment": "vip",
  "template_id": "ref",
  "offer_id": "ref",                // NEW: which offer was included
  "message_content": "Hi Ravi, 20% off on Basmati Rice...",
  "status": "pending|processing|sent|delivered|failed|failed_permanently|cancelled",
  "priority": 1,
  "scheduled_at": "ISODate",
  "sent_at": "ISODate",
  "retry_count": 0,
  "error_log": [{"timestamp": "...", "error": "Rate limit", "retry_count": 1}],
  "failure_reason": "rate_limit|network|invalid_number|unknown",  // NEW: categorized
  "user_id": "ref",
  "created_at": "ISO datetime"
}
```

#### [MODIFY] [database.py](file:///d:/whatsapp/backend/config/database.py)
- Remove indexes for `msg_queues` and `campaign_batches`
- Add `offers` collection indexes
- Add content-hash unique index on `files`
- Add composite dedup index on `transactions`
- Rename `product_inventory` references → `products`

#### [MODIFY] [models.py](file:///d:/whatsapp/backend/schemas/models.py)
- Add `OfferCreate`, `OfferResponse`, `OfferUpdate` Pydantic models
- Add `upload_cycle` to `ShopCreate`
- Add `period_tag` to file/transaction models
- Add `MonitoringStats` response model
- Remove `MessageQueueCreate/Response` and `CampaignBatchCreate/Response`

---

### Phase 2: Duplicate Prevention & Period Tagging

#### [MODIFY] [file_service.py](file:///d:/whatsapp/backend/services/file_service.py)
- Compute SHA-256 hash of file content before upload
- Check `files` collection for `(user_id, shop_id, data_purpose, content_hash)` match
- If match found → return existing file doc with `duplicate: true`, **skip B2 upload**
- If no match → proceed with normal upload
- Store `content_hash` and `row_count` in file doc

#### [MODIFY] [shop_service.py](file:///d:/whatsapp/backend/services/shop_service.py)
- Add `upload_cycle` to shop creation
- Compute `period_tag` from current date + shop's upload_cycle:
  - Monthly: `"2026-06"` (YYYY-MM)
  - Weekly: `"2026-06-W3"` (YYYY-MM-WN where N = week number in month)
- Pass `period_tag` to file upload and transaction processing

#### [MODIFY] [transaction_service.py](file:///d:/whatsapp/backend/services/transaction_service.py)
- Use `insert_many` with `ordered=False` + catch `BulkWriteError` to skip duplicates
- Stop doing `delete_many` before insert (was wiping all data on re-upload)
- Add `period_tag` to each transaction doc
- Only replace data for the **same period_tag** (not all shop data)

#### [MODIFY] [product_service.py](file:///d:/whatsapp/backend/services/product_service.py)
- Rename collection `product_inventory` → `products`
- Use upsert on `(shop_id, product_id)` instead of delete-all + insert
- This preserves existing products while updating changed ones

#### [MODIFY] [customer_service.py](file:///d:/whatsapp/backend/services/customer_service.py)
- Already uses upsert (good) — no major changes needed
- Add `period_tag` tracking to know which upload cycle added each customer

---

### ⚡ ADDENDUM A: Cross-Upload Customer Dedup & Cumulative Classification

> [!CAUTION]
> **CRITICAL BUG FOUND:** `transaction_service.py` line 104 does `delete_many({"shop_id": shop_id})` — this **NUKES ALL historical transactions** every time a new CSV is uploaded. So if you upload June data, then July data, June is gone. Classification only uses July. This destroys the entire RFM model.

#### The Problem (3 layers)

**Layer 1 — Customer Identity Dedup (already works ✅)**
Current `customer_service.py` already upserts on `(shop_id, phone)`. If Ravi appears in June CSV and July CSV, he gets one customer record. `first_seen` stays as June, `last_seen` updates to July. **No changes needed here.**

**Layer 2 — Transaction Accumulation (BROKEN ❌)**
Current code does `delete_many` → `insert_many`. This means:
- Upload June sales → 500 transactions stored
- Upload July sales → June's 500 transactions **deleted**, only July's 400 remain
- RFM classification now only sees 1 month of data → completely wrong scores

**Layer 3 — Dynamic Segment Re-classification (partially works ⚠️)**
Current `recalculate_all_insights()` does re-compute RFM from all transactions in DB. That logic is correct. But since Layer 2 destroys old transactions, it only ever sees the latest upload's data.

#### The Fix

##### Transaction Accumulation Strategy

```python
# OLD (BROKEN) — transaction_service.py line 103-104:
await self.db.transactions.delete_many({"shop_id": shop_id})  # NUKES EVERYTHING
await self.db.transactions.insert_many(tx_docs)

# NEW (FIXED) — Period-scoped replace + accumulate:
# Only delete transactions for the SAME period_tag (re-upload of same month)
await self.db.transactions.delete_many({
    "shop_id": shop_id, 
    "period_tag": current_period_tag  # e.g., "2026-06"
})
# Insert new period's transactions (they accumulate alongside other months)
await self.db.transactions.insert_many(tx_docs, ordered=False)
```

**Result:** After uploading June + July + August CSVs, the DB contains ALL three months of transactions. RFM classification uses the **full purchase history** across all months.

##### Row-Level Dedup Within Same Period

Even within the same month's CSV, prevent duplicate rows:
```python
# Unique compound index on transactions:
(shop_id, customer_id, product_id, purchase_date, purchase_qty, total_amount)
```
Use `insert_many(ordered=False)` and catch `BulkWriteError` — duplicate rows silently skipped.

##### Dynamic Segment Re-classification Flow

```
Month 1 (June): Upload transactions → recalculate_all_insights()
  Ravi: F=10, M=5000, R=2 days → VIP
  Priya: F=3, M=800, R=5 days → loyal_frequent

Month 2 (July): Upload transactions → June + July both in DB → recalculate_all_insights()
  Ravi: F=10, M=5000, R=35 days (hasn't come back!) → AT_RISK  ← auto-updated!
  Priya: F=8, M=4200, R=1 day (came back a lot!) → VIP  ← promoted!
  New guy Karthik: F=2, M=300, R=3 days → boring (or new_customer)
```

The segment change happens **automatically** because `recalculate_all_insights()` always runs on the **full transaction history** and does an atomic delete-old → insert-new on `customer_insights`.

##### Previous Segment Tracking

To know *what changed*, before deleting old insights, read the current segment:

```python
# In recalculate_all_insights(), BEFORE delete_many:
old_insights = {}
async for doc in db.customer_insights.find({"shop_id": shop_id}, {"customer_id": 1, "segment": 1}):
    old_insights[doc["customer_id"]] = doc["segment"]

# When building new insight docs:
doc["previous_segment"] = old_insights.get(cust_id, None)
doc["segment_changed"] = doc["previous_segment"] != doc["segment"] if doc["previous_segment"] else False
```

This enables smart template messages:
- VIP → At-Risk: *"We miss you, Ravi! Here's 20% off..."*
- Boring → Loyal Frequent: *"Thanks for being a regular, Priya!"*
- None → New: *"Welcome to Anbu Super Market!"*

##### Files Changed for Addendum A

| File | Change |
|------|--------|
| [transaction_service.py](file:///d:/whatsapp/backend/services/transaction_service.py) | Replace `delete_many(shop_id)` with `delete_many(shop_id + period_tag)`. Add `period_tag` to each doc. |
| [insights_service.py](file:///d:/whatsapp/backend/services/insights_service.py) | Read old segments before delete. Add `previous_segment` + `segment_changed` fields. |
| [customer_insights schema](file:///d:/whatsapp/backend/config/database.py) | Add `previous_segment` and `segment_changed` to insight docs. |
| [product_service.py](file:///d:/whatsapp/backend/services/product_service.py) | Replace `delete_many(shop_id)` with upsert on `(shop_id, product_id)`. Products accumulate. |

---

### ⚡ ADDENDUM B: Classification Logic — Deep Audit & Refined Rules

#### Current Waterfall (5 rules)

```python
# Rule 1: VIP — total >= 12 AND m_score >= 4
# Rule 2: At-Risk — r_score <= 2 AND (f+m) >= 5
# Rule 3: Potential Bulk — 5 <= total <= 11 AND b_score >= 4
# Rule 4: Loyal Frequent — 5 <= total <= 11 AND f >= 3 AND f >= m
# Rule 5: Boring — everything else (total <= 4 OR no rule matched)
```

#### 🔍 Issue 1: VIP Gate is Too Strict

**Problem:** `m_score >= 4` blocks customers who are extremely frequent and recent but don't spend huge amounts per visit. Example:
- Ravi visits daily, buys ₹200 worth each time. F=5, R=5, M=3 (moderate per-visit but high total). Total=13 but M<4 → **not VIP**. Falls to Rule 3/4.
- For a local supermarket, a daily customer IS a VIP even if individual purchases are small.

**Fix:** Relax VIP to allow high-frequency compensating for moderate monetary:
```python
# Rule 1 (REFINED): VIP
if total_score >= 12:       # Remove the m_score >= 4 gate
    return "vip"            # A total of 12+ means they're top-tier on SOME combo of R+F+M
# OR keep m_score gate but add frequency override:
if total_score >= 12 and (m_score >= 4 or f_score == 5):  # Daily customer = VIP too
    return "vip"
```

**Recommendation for local supermarkets:** Use the frequency override version. A customer who comes every day is gold for a kirana/supermarket.

#### 🔍 Issue 2: At-Risk Misses Gradual Churn

**Problem:** Current rule requires `r_score <= 2` (bottom 40% recency). But with cumulative data across months, churn detection needs to compare *current behavior vs. past behavior*.

Example: Ravi was VIP last month (R=5, total=14). This month he hasn't visited in 20 days. His r_score might be 3 (not yet <=2), so he's NOT flagged as At-Risk. By the time r_score hits 2, he's already gone.

**Fix:** Use `previous_segment` for churn velocity detection:
```python
# Rule 2 (REFINED): At-Risk
# Original trigger (still valid):
if r_score <= 2 and (f_score + m_score) >= 5:
    return "at_risk"
# NEW: Churn velocity trigger — was VIP/Loyal last period, R dropped significantly
if previous_segment in ("vip", "loyal_frequent") and r_score <= 3:
    return "at_risk"  # Catch them BEFORE they fully churn
```

#### 🔍 Issue 3: No "New Customer" Handling

**Problem:** A customer who appears for the first time this month has 1-2 transactions. Their RFM scores will be low (F=1, M=low, R=recent). They'll be classified as **Boring** — but they're actually **new prospects** who deserve a welcome message, not the "low-engagement" treatment.

**Fix:** Add a pre-waterfall check:
```python
# Rule 0 (NEW): New Customer — BEFORE the waterfall
if purchase_count <= 2 and recency_days <= 30:  # ≤2 purchases in last 30 days
    return "new_customer"  # Gets welcome template, not "boring" treatment
```

Add to `CustomerCategory` enum:
```python
NEW_CUSTOMER = "new_customer"  # First-time or second-time visitor
```

#### 🔍 Issue 4: "Boring" is a Black Hole (Catch-All)

**Problem:** Any customer with total_score 5-11 who doesn't match Rule 3 or 4 falls to Boring. Example:
- Score=7, b_score=3 (not bulk), f_score=2 (not frequent enough) → Boring
- But this customer has moderate engagement. They're not disengaged — they're **occasional shoppers** who could be nurtured.

**Verdict:** For a college project, keeping 5 categories (+ new_customer = 6) is cleaner than adding more. The "boring" label is just a name — rename it to **"occasional"** for business clarity, but the segmentation logic can stay as-is. The real fix is Issue 3 (pulling new customers out of the boring bucket).

**Recommendation:** Keep "boring" as the internal enum value for backward compat, but display it as "Occasional" in the frontend. This is a display-only change.

#### 🔍 Issue 5: No Segment Transition Tracking

**Problem:** When Ravi goes from VIP → At-Risk, there's no record. The old insight is atomically deleted and replaced. Templates can't say *"We noticed you haven't visited recently"* because they don't know the customer's trajectory.

**Fix:** Already covered in Addendum A — add `previous_segment` and `segment_changed` fields to `customer_insights`.

#### ✅ Refined 6-Tier Waterfall (Final)

```python
def apply_waterfall_segmentation(row, previous_segment=None):
    total_score = row['rfm_score']
    r_score = row['r_score']
    f_score = row['f_score']
    m_score = row['m_score']
    b_score = row['b_score']
    purchase_count = row.get('purchase_count', 0)
    recency_days = row.get('recency_days', 999)

    # ── Rule 0: NEW CUSTOMER (pre-waterfall escape) ──
    if purchase_count <= 2 and recency_days <= 30:
        return "new_customer"

    # ── Rule 1: VIP (Champions) ──
    # Total >= 12, with frequency override for daily shoppers
    if total_score >= 12 and (m_score >= 4 or f_score == 5):
        return "vip"

    # ── Rule 2: AT-RISK (Churn Prevention) ──
    # Classic trigger: low recency but was historically valuable
    if r_score <= 2 and (f_score + m_score) >= 5:
        return "at_risk"
    # Churn velocity: was VIP/Loyal last period, R is dropping
    if previous_segment in ("vip", "loyal_frequent") and r_score <= 3:
        return "at_risk"

    # ── Rule 3: POTENTIAL BULK (Pantry Stockers) ──
    if 5 <= total_score <= 11 and b_score >= 4:
        return "potential_bulk"

    # ── Rule 4: LOYAL FREQUENT (Daily Habit) ──
    if 5 <= total_score <= 11 and f_score >= 3 and f_score >= m_score:
        return "loyal_frequent"

    # ── Rule 5: BORING / OCCASIONAL (Baseline) ──
    return "boring"  # Display as "Occasional" in frontend
```

#### Summary of Classification Changes

| Change | What | Impact |
|--------|------|--------|
| Add `new_customer` segment | Pre-waterfall escape for ≤2 purchases in 30 days | New customers get welcome messages instead of "boring" treatment |
| Relax VIP gate | Add `f_score == 5` override | Daily shoppers become VIP even with moderate spend |
| Churn velocity At-Risk | Use `previous_segment` to catch dropping VIPs early | Catch churning customers 1 period earlier |
| `previous_segment` tracking | Store old segment before re-classification | Enables segment-transition-aware templates |
| Rename "Boring" → "Occasional" | Frontend display only | Better business language |

##### Files Changed for Addendum B

| File | Change |
|------|--------|
| [models.py](file:///d:/whatsapp/backend/schemas/models.py) | Add `NEW_CUSTOMER = "new_customer"` to `CustomerCategory` enum |
| [insights_service.py](file:///d:/whatsapp/backend/services/insights_service.py) | Update `_waterfall_segment()` with 6-tier logic + `previous_segment` param |
| [classifier.py](file:///d:/whatsapp/backend/utils/classifier.py) | Update `apply_waterfall_segmentation()` to match (kept for backward compat) |
| Frontend segment displays | Show "Occasional" instead of "Boring", add "New" badge |

---

### Phase 3: Offers System

#### [NEW] [offers_service.py](file:///d:/whatsapp/backend/services/offers_service.py)
```
OffersService class:
  - create_offer(shop_id, user_id, offer_data) → creates offer doc
  - list_offers(shop_id, user_id, active_only=True) → list offers
  - get_offer(offer_id) → single offer
  - update_offer(offer_id, updates) → edit offer
  - delete_offer(offer_id) → soft delete (is_active=false)
  - get_offers_for_segment(shop_id, segment) → offers targeting this segment
  - match_offers_to_customers(shop_id) → returns {customer_id: [matching_offer_ids]}
    Logic:
      1. Get all active offers for shop
      2. For each customer, get their segment from customer_insights
      3. For each offer, check if customer's segment is in target_segments
      4. For product-specific offers, also check if product_ids overlap with 
         customer's fav_items/recent_purchases from customer_insights
      5. Return best-matching offer per customer (prioritize product-preference match)
```

#### [NEW] [offers.py](file:///d:/whatsapp/backend/routes/offers.py)
- `POST /api/shops/{shop_id}/offers` — Create offer
- `GET /api/shops/{shop_id}/offers` — List offers (with segment filter)
- `PUT /api/shops/{shop_id}/offers/{offer_id}` — Update offer
- `DELETE /api/shops/{shop_id}/offers/{offer_id}` — Delete offer
- `GET /api/shops/{shop_id}/offers/match` — Preview offer→customer matching

#### Template Integration
- Add new placeholders: `{{offer_title}}`, `{{offer_discount}}`, `{{offer_product}}`
- When creating a campaign, user selects template + offer per segment
- `batch_service.py` hydrates offer placeholders from the matched offer

---

### Phase 4: Real WhatsApp Web Message Sender

**Replace mock sender with actual WhatsApp Web automation using `playwright`.**

#### [NEW] [whatsapp_sender.py](file:///d:/whatsapp/backend/services/whatsapp_sender.py)
```python
class WhatsAppWebSender:
    """
    Sends messages via WhatsApp Web using Playwright (headless Chromium).
    
    Key features:
    - Persistent browser session (stays logged in via saved profile)
    - Working hours enforcement (9AM-7PM IST)
    - Rate limit detection + auto-reschedule
    - 3-5 second random delay between messages (human-like)
    """
    
    WORKING_HOURS = (9, 19)  # 9AM to 7PM IST
    IST_OFFSET = timedelta(hours=5, minutes=30)
    MAX_MESSAGES_PER_DAY = 200  # WhatsApp soft limit
    
    async def is_within_working_hours(self) -> bool:
        """Check if current IST time is between 9AM-7PM."""
        
    async def send_message(self, phone: str, message: str) -> dict:
        """
        1. Check working hours → if outside, return {success: False, error: "outside_working_hours"}
        2. Check daily message count → if exceeded, return {success: False, error: "rate_limit"}
        3. Navigate to https://web.whatsapp.com/send?phone={phone}&text={encoded_message}
        4. Wait for message input to load
        5. Click send button
        6. Verify message appears in chat
        7. Return {success: True, sent_at: "..."}
        
        Error detection:
        - "Phone number shared via url is invalid" → invalid_number
        - Page timeout → network_error  
        - Repeated failures → rate_limit (auto-reschedule to next day 9AM)
        """
        
    async def initialize_browser(self):
        """Launch Playwright with persistent profile (one-time QR scan)."""
        
    async def close(self):
        """Graceful browser shutdown."""
```

#### [MODIFY] [scheduler_service.py](file:///d:/whatsapp/backend/services/scheduler_service.py)
- Replace `send_whatsapp_message()` mock with `WhatsAppWebSender.send_message()`
- Add working hours check at the start of each heartbeat cycle:
  - If outside 9AM-7PM IST → skip cycle, log "Outside working hours"
- Add daily message counter tracking
- On `rate_limit` error → auto-reschedule all remaining pending messages to next day 9AM IST
- On `invalid_number` → mark as `failed_permanently` immediately (no retry)
- Remove `msg_queues` dependency — work directly with `messages` collection

#### [MODIFY] [batch_service.py](file:///d:/whatsapp/backend/services/batch_service.py)
- Remove all `msg_queues` / `campaign_batches` references
- Add `offer_id` to message docs when offer is attached
- Simplify `_enqueue_messages` → just update message status (no separate collection)
- Add `campaign_id` directly on each message doc

---

### Phase 5: Monitoring System

#### [NEW] [monitoring_service.py](file:///d:/whatsapp/backend/services/monitoring_service.py)
```python
class MonitoringService:
    """
    Provides campaign/batch/message monitoring with drill-down.
    
    Hierarchy:
      Campaign → Batches → Messages
      
    For each level, shows:
      - Total / Sent / Failed / Pending counts
      - Failure reasons breakdown
      - Per-message error logs
    """
    
    async def get_campaign_overview(shop_id, user_id):
        """All campaigns for a shop with aggregated stats."""
        # Pipeline: campaigns → join batches → join messages → aggregate
        
    async def get_campaign_detail(campaign_id, user_id):
        """Single campaign with per-batch breakdown."""
        # For each batch: sent/failed/pending counts
        # Failed messages with error reasons
        
    async def get_batch_detail(batch_id, user_id):
        """All messages in a batch with status + error details."""
        
    async def get_failed_messages(campaign_id, user_id):
        """All failed messages with categorized failure reasons."""
        # Group by failure_reason: rate_limit, network, invalid_number, unknown
        
    async def reschedule_failed(campaign_id, user_id, mode="failed"):
        """
        Reschedule failed messages.
        mode: "failed" | "all_pending" | "specific_batch"
        
        If rate_limit → default reschedule to next day 9AM IST
        If network → reschedule in 5 minutes
        If invalid_number → skip (notify owner)
        
        Returns: {rescheduled: N, skipped: N, reasons: {...}}
        """
        
    async def get_period_summary(shop_id, period_tag):
        """Stats for a specific upload period (month/week)."""
```

#### [NEW] [monitoring.py](file:///d:/whatsapp/backend/routes/monitoring.py)
- `GET /api/shops/{shop_id}/monitoring/campaigns` — Campaign overview
- `GET /api/shops/{shop_id}/monitoring/campaigns/{campaign_id}` — Campaign detail with batch breakdown
- `GET /api/shops/{shop_id}/monitoring/batches/{batch_id}` — Batch detail with all messages
- `GET /api/shops/{shop_id}/monitoring/failed/{campaign_id}` — Failed messages breakdown
- `POST /api/shops/{shop_id}/monitoring/reschedule/{campaign_id}` — Reschedule failed
- `GET /api/shops/{shop_id}/monitoring/periods` — Period-wise summary

---

### Phase 6: Frontend Changes

#### [NEW] OffersPage.js
- CRUD UI for creating/editing offers
- Product picker (from shop's product inventory)
- Segment selector (checkboxes for VIP, At-Risk, etc.)
- Offer preview showing which customers would receive it

#### [NEW] MonitoringPage.js
- **Campaign list view**: cards showing each campaign with progress bars (sent/failed/pending)
- **Campaign detail view**: drill into batches, see per-batch stats
- **Batch detail view**: see individual messages with status icons
- **Failed messages panel**: grouped by failure reason, with "Reschedule" buttons
- **Auto-refresh**: poll every 30s while campaigns are active
- **Period filter**: filter by month/week

#### [MODIFY] ShopDashboardPage.js
- Add `upload_cycle` selector (Monthly/Weekly) on shop creation
- Show period tag on uploaded files
- Add "Offers" tab/section
- Add link to Monitoring page

#### [MODIFY] CampaignCreatorPage.js
- Add offer selection step: "Select offer for each segment"
- Show offer preview in template hydration
- Add `{{offer_title}}`, `{{offer_discount}}`, `{{offer_product}}` to placeholder help

#### [MODIFY] Sidebar.js
- Add "Offers" nav item
- Add "Monitoring" nav item

#### [MODIFY] App.js
- Add routes for `/offers` and `/monitoring`

---

### Phase 7: Server & Integration

#### [MODIFY] [server.py](file:///d:/whatsapp/backend/server.py)
- Register new routers: `offers`, `monitoring`
- Initialize `WhatsAppWebSender` on startup (with browser session)
- Pass sender instance to scheduler
- Add migration to rename `product_inventory` → `products`
- Add migration to merge `msg_queues` data into `messages` and drop collection
- Add migration to drop `campaign_batches`

#### [MODIFY] [requirements.txt](file:///d:/whatsapp/backend/requirements.txt)
- Add `playwright` (replaces pywhatkit for reliable WhatsApp Web automation)
- Remove `pywhatkit` and `pyautogui` from project dependencies

---

## Complete Refined Flow

```
1. SHOP CREATION
   Owner registers → Creates shop → Selects upload cycle (Monthly/Weekly)
   
2. CSV UPLOAD (3 files)
   Upload Customer CSV → Map columns → Upsert customers (dedup on shop_id+phone)
   Upload Product CSV  → Map columns → Upsert products (dedup on shop_id+product_id)
   Upload Transaction CSV → Map columns → Insert transactions (dedup on composite key)
   Each upload: SHA-256 hash check → skip if identical file already processed
   Each upload: auto-tagged with period_tag based on shop's upload_cycle
   
3. CLASSIFICATION (automatic — CUMULATIVE)
   After transaction upload → recalculate_all_insights() runs on ALL transactions (all months!)
   Step 0: Read current segments (for transition tracking)
   Step 1: Aggregate R, F, M, B from full purchase history
   Step 2: Quintile scoring → 6-tier waterfall (new_customer → vip → at_risk → potential_bulk → loyal_frequent → boring)
   Step 3: Compare new segment vs previous_segment → flag segment_changed
   Step 4: Level 2 behavioral profiling (8 template vars)
   Result: customer_insights updated with segment + previous_segment + 8 template vars
   
   Example across months:
     June: Ravi (F=10, R=2d) → VIP | Priya (F=3, R=5d) → loyal_frequent
     July: Ravi (F=10, R=35d, didn't come back) → AT_RISK ← auto-demoted!
           Priya (F=8, R=1d, came back a lot) → VIP ← auto-promoted!
           Karthik (F=1, R=3d, first time) → NEW_CUSTOMER ← not "boring"!
   
4. OFFERS MANAGEMENT
   Owner creates offers → Links to products + target segments
   System matches offers to customers based on:
     a. Customer segment matches offer's target_segments
     b. Customer's fav_items/recent_purchases overlap with offer's product_ids
   
5. CAMPAIGN CREATION
   Owner selects template per segment → Selects offer per segment (optional)
   System hydrates: {{customer_name}}, {{favorite_premium_product}}, {{offer_title}}, etc.
   Segment-transition-aware templates:
     VIP→At-Risk: "We miss you, Ravi! 20% off..."
     None→New: "Welcome to Anbu Super Market!"
   Preview with real customer data before scheduling
   
6. MESSAGE SCHEDULING
   Split customers into batches → Create message docs with offer_id
   All messages get scheduled_at within working hours (9AM-7PM IST)
   Priority: VIP=1, At-Risk=1, New=2, Potential Bulk=2, Loyal Frequent=3, Boring=4
   
7. MESSAGE SENDING (Real WhatsApp Web)
   Scheduler heartbeat (60s) picks pending messages ordered by priority
   WhatsAppWebSender: Playwright → web.whatsapp.com → send
   3-5s random delay between messages (human-like)
   Working hours enforced: outside 9AM-7PM IST → skip cycle
   
8. ERROR HANDLING & AUTO-RESCHEDULE
   rate_limit → auto-reschedule ALL pending to next day 9AM IST
   network_error → retry in 5 min (max 3 retries)
   invalid_number → mark failed_permanently (no retry)
   After 3 retries → failed_permanently → notify owner via dashboard
   
9. MONITORING
   Real-time dashboard: Campaign → Batch → Message drill-down
   Failed messages grouped by reason
   One-click reschedule (defaults to next day 9AM for rate limits)
   Period-wise summary (which month's campaign, how it performed)
```

---

## Verification Plan

### Automated Tests
1. **Schema dedup test**: Upload same CSV twice → verify no duplicate records in DB
2. **Period tagging test**: Create monthly shop → upload → verify `period_tag = "2026-06"`
3. **Offer matching test**: Create offer for VIP segment → verify correct customers matched
4. **Working hours test**: Mock IST time outside 9-7 → verify scheduler skips
5. **Rate limit test**: Simulate rate_limit error → verify auto-reschedule to next day 9AM
6. Run `python -m pytest` on all service tests

### Manual Verification
1. Create a shop → Upload all 3 CSVs → Verify classification in customer_insights
2. Create an offer → Create campaign with offer → Preview hydrated message
3. Schedule campaign → Monitor via dashboard → Verify message delivery
4. Re-upload same CSV → Verify "duplicate" flag returned, no data duplication
5. Test WhatsApp Web sender with real phone number (single message first)

---

## Implementation Order

| Phase | What | Effort | Priority |
|-------|------|--------|----------|
| 1 | Schema refinement + collection consolidation | 3-4 hrs | 🔴 Critical |
| 2 | Duplicate prevention + period tagging | 2-3 hrs | 🔴 Critical |
| 3 | Offers system (backend + frontend) | 3-4 hrs | 🟡 High |
| 4 | Real WhatsApp Web sender | 3-4 hrs | 🟡 High |
| 5 | Monitoring system (backend + frontend) | 3-4 hrs | 🟡 High |
| 6 | Frontend pages (Offers, Monitoring, updates) | 4-5 hrs | 🟢 Medium |
| 7 | Integration, migrations, testing | 2-3 hrs | 🟢 Medium |

**Total estimated: ~20-25 hours of implementation**
