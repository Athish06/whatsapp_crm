# Implementation Plan — Brutal Stress Test

I traced through every phase with real-world scenarios. Found **12 logical bugs** ranging from CRITICAL to LOW. Here's each one with how it breaks and the fix.

---

## 🔴 BUG #1: Ghost Customers — Silent Data Loss [CRITICAL]

**Where:** Addendum A — `recalculate_all_insights()` previous_segment tracking

**The scenario:**
1. June: Ravi buys 10 times → insight created: segment=VIP
2. July: Ravi doesn't visit AT ALL. Zero transactions in July CSV.
3. Upload July CSV → `recalculate_all_insights()` runs:
   - Step 1: Read old insights → `old_insights = {"Ravi": "vip"}`
   - Step 2: `delete_many({"shop_id": shop_id})` → **Ravi's insight DELETED**
   - Step 3: Aggregate transactions → Ravi HAS June transactions still in DB (period-scoped delete preserves them) → Ravi IS in agg_df → new insight created ✓

Wait — actually this is fine IF June transactions are preserved. But let me trace the REAL scary scenario:

**The ACTUAL scary scenario:**
1. June: Upload transactions → Ravi gets insight (VIP)
2. July: Owner uploads ONLY a customer CSV (no new transaction CSV this month)
3. Customer upload triggers `recalculate_all_insights()` IF `tx_count > 0` (line 218-222 in customer_service.py)
4. This recalculates using ALL existing transactions → Ravi's R_score drops (35+ days since last purchase) → segment changes from VIP → At-Risk ✓

OK, this path is actually fine. But here's the REAL bug:

**The REAL bug — orphaned customers:**
1. A customer exists in `customers` collection but has ZERO transactions (was added via customer CSV only, no sales data yet)
2. `recalculate_all_insights()` groups by `customer_id` from `transactions` — this customer has no transactions → no insight doc created
3. In `customer_service.py` lines 257-272, when merging insights into customers for API response, this customer gets `segment = "boring"` as fallback
4. **But** — this customer had `previous_segment` tracking from an earlier upload. After `delete_many`, their old insight (with previous_segment) is **gone forever**. No segment history preserved.

**Fix:** Don't use `delete_many` → `insert_many`. Use `bulk_write` with `UpdateOne(upsert=True)` instead:
```python
# Instead of atomic delete → insert, use upsert:
from pymongo import UpdateOne
ops = []
for doc in insight_docs:
    ops.append(UpdateOne(
        {"shop_id": shop_id, "customer_id": doc["customer_id"]},
        {"$set": doc},
        upsert=True
    ))
if ops:
    await db.customer_insights.bulk_write(ops, ordered=False)

# Then mark customers NOT in this batch as "dormant" (don't delete them):
active_ids = [doc["customer_id"] for doc in insight_docs]
await db.customer_insights.update_many(
    {"shop_id": shop_id, "customer_id": {"$nin": active_ids}},
    {"$set": {"segment": "dormant", "updated_at": now_iso}}
)
```

**Severity: 🔴 CRITICAL** — Segment history silently lost on every recalculation.

---

## 🔴 BUG #2: Period Tag Derived from Upload Date, Not Data Date [CRITICAL]

**Where:** Phase 2 — Period tagging logic

**The scenario:**
1. Shop has monthly cycle. It's July 3rd.
2. Owner uploads June's sales data (was late this month).
3. Plan says: "Compute period_tag from current date + shop's upload_cycle"
4. Period tag = `"2026-07"` ← **WRONG!** This is June's data tagged as July's.
5. Later, owner uploads actual July data → period_tag also `"2026-07"`
6. `delete_many(shop_id + "2026-07")` → **June data wiped!**

**Fix:** Let the user specify the period during upload, OR derive it from the transaction dates:
```python
# Option A: User specifies period (simple, reliable)
# Add to the upload API: period_tag query param
# Frontend shows a dropdown: "Which period is this data for?"

# Option B: Auto-detect from data (smart, but fragile)
# Use the MODE of purchase_date months in the CSV:
dominant_month = df["purchase_date"].dt.to_period("M").mode()[0]
period_tag = str(dominant_month)  # "2026-06"
```

**Recommendation:** Use Option A with Option B as default suggestion. Frontend shows "This looks like June 2026 data" and lets the user confirm/change.

**Severity: 🔴 CRITICAL** — Wrong period tag = data loss on next upload.

---

## 🔴 BUG #3: Legitimate Duplicate Transactions Deduped [CRITICAL]

**Where:** Addendum A — Transaction composite unique index

**The scenario:**
1. Ravi buys 2 packs of milk (₹50 each) at 9 AM: `(Ravi, MILK001, 2026-06-15, qty=2, amt=100)`
2. Ravi comes back at 6 PM, buys 2 more packs: `(Ravi, MILK001, 2026-06-15, qty=2, amt=100)`
3. Both rows have IDENTICAL values for all composite key fields
4. Unique index rejects the second row → **legitimate transaction lost**
5. RFM scores are wrong — Ravi's frequency and monetary are undercounted

**Fix:** Add a `transaction_id` or row number to the composite key, or use a weaker dedup strategy:
```python
# Option A: Don't use unique index at all. Use period-scoped replace instead.
# delete_many(shop_id + period_tag) → insert_many (no unique constraint)
# This is safe because we wipe the period's data first, then insert fresh.

# Option B: Add row_number to break ties:
# When parsing CSV, add a row_number column:
df["row_number"] = range(len(df))
# Include in doc: "row_number": int(row["row_number"])
# Unique index: (shop_id, period_tag, row_number) — prevents re-upload duplication
# but allows same-day same-product transactions
```

**Recommendation:** Use **Option A** (period-scoped replace). It's simpler and handles the CSV dedup problem (re-uploading same month's CSV) without breaking legitimate duplicates. The SHA-256 file hash already prevents identical-file re-processing.

**Severity: 🔴 CRITICAL** — Silently drops real sales data, corrupts RFM.

---

## 🟡 BUG #4: New Customer Rule Triggers on Returning Dormant Customers [HIGH]

**Where:** Addendum B — Rule 0: New Customer

**The scenario:**
1. January: Ravi buys once (purchase_count=1). Classified as `new_customer` ✓
2. Feb–May: Ravi doesn't visit. He's sitting in insights as `boring` or `dormant`.
3. June: Ravi comes back, buys once. Total purchase_count across all months = 2.
4. recency_days = 1 (just bought today). purchase_count = 2.
5. Rule 0: `purchase_count <= 2 AND recency_days <= 30` → **`new_customer`!** ← WRONG
6. Ravi is NOT new. He's a returning customer. He should get "Welcome back!" not "Welcome to our store!"

**Fix:** Use `previous_segment` to guard:
```python
# Rule 0 (FIXED): New Customer
if purchase_count <= 2 and recency_days <= 30 and previous_segment is None:
    return "new_customer"
```
`previous_segment is None` means they've never been classified before → truly new.

**Severity: 🟡 HIGH** — Misclassifies returning customers, sends wrong messages.

---

## 🟡 BUG #5: Quintile Scores Shift as Dataset Grows [HIGH]

**Where:** Addendum A — Cumulative classification with relative scoring

**The scenario:**
1. June: 50 customers. Ravi has F=5 (visits). He's in top 20% → f_score=5.
2. July: 200 new customers join, many with F=10-30 (heavy shoppers).
3. Recalculate: Ravi still has F=5, but now he's bottom 40% → f_score=2!
4. Ravi's total_score drops from 13 to 8. He goes from VIP → Loyal Frequent.
5. **Ravi's behavior didn't change at all.** He got demoted because OTHER customers joined.

This is a fundamental issue with quintile-based (relative) scoring on growing datasets.

**Fix:** Use absolute thresholds as floor, relative scoring as ceiling:
```python
# Hybrid approach: absolute floors + relative quintiles
# Define absolute minimums for "good" behavior (based on your supermarket):
ABSOLUTE_FLOORS = {
    "frequency_vip": 8,      # 8+ visits = guaranteed f_score >= 4
    "monetary_vip": 5000,    # ₹5000+ total spend = guaranteed m_score >= 4
    "recency_fresh": 14,     # Visited within 14 days = guaranteed r_score >= 4
}

# After quintile scoring, apply floors:
if row["frequency"] >= ABSOLUTE_FLOORS["frequency_vip"]:
    row["f_score"] = max(row["f_score"], 4)
if row["monetary"] >= ABSOLUTE_FLOORS["monetary_vip"]:
    row["m_score"] = max(row["m_score"], 4)
if row["recency_days"] <= ABSOLUTE_FLOORS["recency_fresh"]:
    row["r_score"] = max(row["r_score"], 4)
```

**Note:** The exact threshold values should be configurable per shop (small kirana vs big supermarket). For a college project, hardcoded defaults are fine.

**Severity: 🟡 HIGH** — Customers silently demoted without behavior change. Owner confusion.

---

## 🟡 BUG #6: At-Risk Churn Velocity Rule Too Aggressive [HIGH]

**Where:** Addendum B — Rule 2 refined

**The scenario:**
1. June: Ravi is VIP (R=5, F=5, M=5, total=15). previous_segment=None.
2. July: Ravi bought 2 days ago. But 60% of other customers bought TODAY.
3. Ravi's r_score = 3 (middle of the pack — he's slightly less recent than median).
4. Churn velocity rule: `previous_segment == "vip" AND r_score <= 3` → **At-Risk!**
5. But Ravi literally bought 2 days ago! He's not churning at all!

**Problem:** `r_score <= 3` is too loose. In a 5-point scale, 3 is the MEDIAN. Half of all customers have r_score <= 3. This would flag ~50% of former VIPs as At-Risk.

**Fix:** Tighten the churn velocity trigger:
```python
# Churn velocity: only trigger if R dropped significantly
if previous_segment in ("vip", "loyal_frequent") and r_score <= 2:  # Bottom 40%, not 60%
    return "at_risk"

# OR use absolute days instead of relative score:
if previous_segment in ("vip", "loyal_frequent") and recency_days >= 30:
    return "at_risk"  # 30+ days since last visit = genuinely drifting
```

**Recommendation:** Use the absolute-days version (`recency_days >= 30`). It's intuitive, doesn't depend on relative scoring, and the owner can understand it: "hasn't visited in a month."

**Severity: 🟡 HIGH** — Floods the At-Risk segment with perfectly active customers.

---

## 🟠 BUG #7: SHA-256 Hash Blocks Intentional Re-processing [MEDIUM]

**Where:** Phase 2 — File content hash dedup

**The scenario:**
1. Owner uploads June sales CSV → processed successfully.
2. Owner realizes the column mapping was wrong (mapped "price" to "quantity").
3. Owner tries to re-upload the SAME file with correct mapping.
4. SHA-256 hash matches → "duplicate: true" → **processing skipped!**
5. Owner is stuck with wrongly processed data and can't fix it.

**Fix:** Hash check should return the existing file_id but still ALLOW re-processing:
```python
# On hash match:
return {
    "file_id": existing_file_id,
    "duplicate": True,
    "message": "File already uploaded. You can re-process with different column mapping.",
    "can_reprocess": True  # Frontend shows "Re-process" button instead of "Upload"
}
# The /process endpoint should always work regardless of duplicate status
```

**Severity: 🟠 MEDIUM** — Owner locked out of correcting mistakes.

---

## 🟠 BUG #8: Zombie Products Never Removed [MEDIUM]

**Where:** Phase 2 — Product service upsert change

**The scenario:**
1. January: Upload product catalog with 500 products (including "Christmas Cake").
2. February: Upload new catalog with 480 products (Christmas Cake removed — seasonal).
3. With upsert: 480 products updated, but Christmas Cake **stays in DB** forever.
4. Level 2 profiler still shows Christmas Cake as a valid product.
5. Customer gets offer: "20% off Christmas Cake!" — in February. Embarrassing.

**Fix:** Products are the ONE collection where full-replace (delete + insert) is actually correct. Product catalogs are snapshots — the latest upload IS the complete catalog.

```python
# Keep the current delete-all + insert approach for products:
await self.db.products.delete_many({"shop_id": shop_id})
await self.db.products.insert_many(products)
# This is correct because the product CSV represents the CURRENT catalog
```

**Only transactions and customers** should accumulate. Products should be full-replace.

**Severity: 🟠 MEDIUM** — Stale/seasonal products appear in offers and templates.

---

## 🟠 BUG #9: Expired Offers Sent to Customers [MEDIUM]

**Where:** Phase 3 — Offers system

**The scenario:**
1. June 25: Owner creates offer "Summer Sale — 30% off mangoes" valid until June 30.
2. June 28: Owner creates campaign, selects this offer, schedules for June 30 at 5PM.
3. June 30: Some messages sent successfully. 50 messages fail (rate limit).
4. Auto-reschedule → next day July 1 at 9AM.
5. July 1: Messages sent with "30% off mangoes!" — but the offer expired yesterday.

**Fix:** Check offer validity at **send time**, not just campaign creation time:
```python
# In scheduler, before sending each message:
if message.get("offer_id"):
    offer = await db.offers.find_one({"id": message["offer_id"]})
    if offer and offer.get("valid_until"):
        if datetime.now() > offer["valid_until"]:
            # Skip this message or send without the offer text
            await db.messages.update_one(
                {"id": message["id"]},
                {"$set": {"status": "skipped", "error": "Offer expired"}}
            )
            continue
```

**Severity: 🟠 MEDIUM** — Sends expired offers, breaks customer trust.

---

## 🟠 BUG #10: Messages Sent After 7PM IST [MEDIUM]

**Where:** Phase 4 — Working hours enforcement

**The plan says:** Check working hours at the START of each heartbeat cycle (per-cycle check).

**The scenario:**
1. 6:55 PM IST: Heartbeat fires. Working hours check → ✅ (before 7PM).
2. Scheduler picks 50 pending messages.
3. Each message takes ~3-5 seconds (Playwright + delay).
4. 50 messages × 4s = 200 seconds = ~3.3 minutes.
5. By message #16 (at 6:56 PM + 60 seconds), it's past 7PM.
6. Messages 17-50 are sent **after working hours**.

**Fix:** Check working hours per-message, not per-cycle:
```python
for message in messages:
    if not await self.is_within_working_hours():
        # Stop processing, remaining messages stay pending for tomorrow
        logger.info("Working hours ended mid-batch. Remaining messages deferred.")
        break
    await self.send_message(message)
```

**Severity: 🟠 MEDIUM** — Messages sent at 7:03 PM isn't terrible, but violates the spec.

---

## 🟢 BUG #11: VIP Frequency Override Too Narrow [LOW]

**Where:** Addendum B — Rule 1 VIP

**The rule:** `if total_score >= 12 and (m_score >= 4 or f_score == 5)`

**Problem:** `f_score == 5` means ONLY the top 20% by frequency. A customer with f_score=4 (60-80th percentile, still very frequent!) with m_score=3 and total=12 would NOT be VIP.

**Fix:** `f_score >= 4` instead of `== 5`:
```python
if total_score >= 12 and (m_score >= 4 or f_score >= 4):
    return "vip"
```

**Severity: 🟢 LOW** — Misses some deserving VIPs but doesn't break anything.

---

## 🟢 BUG #12: WhatsApp Web Disconnect Not Handled [LOW]

**Where:** Phase 4 — WhatsApp Web sender

**The scenario:**
1. Shop owner's phone runs out of battery mid-campaign.
2. WhatsApp Web shows "Phone not connected" overlay.
3. Playwright tries to send messages → page navigation works but message never sends.
4. Messages time out → categorized as "network_error" → retry in 5 min.
5. But the phone might be dead for hours. 3 retries all fail → `failed_permanently`.

**Fix:** Detect WhatsApp Web disconnect as a distinct error:
```python
# After page load, check for disconnect banner:
disconnect_banner = await page.query_selector("text=Phone not connected")
if disconnect_banner:
    return {
        "success": False, 
        "error": "whatsapp_disconnected",
        "message": "Phone not connected to WhatsApp Web"
    }
# On this error: pause ALL sending (not just this message), notify owner
```

**Severity: 🟢 LOW** — Wastes retries but existing retry logic eventually handles it.

---

## Summary

| # | Bug | Severity | Phase | Fix Complexity |
|---|-----|----------|-------|----------------|
| 1 | Ghost customers — insights deleted, never recreated | 🔴 CRITICAL | Addendum A | Use upsert instead of delete+insert |
| 2 | Period tag from upload date, not data date | 🔴 CRITICAL | Phase 2 | Auto-detect from CSV dates + user confirm |
| 3 | Legitimate duplicate transactions deduped | 🔴 CRITICAL | Addendum A | Use period-scoped replace, no unique index on transaction fields |
| 4 | New customer rule triggers on returning customers | 🟡 HIGH | Addendum B | Add `previous_segment is None` guard |
| 5 | Quintile scores shift as dataset grows | 🟡 HIGH | Addendum A | Add absolute-value floors to scores |
| 6 | At-Risk churn velocity too aggressive | 🟡 HIGH | Addendum B | Use `recency_days >= 30` instead of `r_score <= 3` |
| 7 | SHA-256 blocks intentional re-processing | 🟠 MEDIUM | Phase 2 | Allow re-process even on hash match |
| 8 | Zombie products never removed | 🟠 MEDIUM | Phase 2 | Keep full-replace for products (don't change to upsert) |
| 9 | Expired offers sent after reschedule | 🟠 MEDIUM | Phase 3 | Check offer validity at send time |
| 10 | Messages sent after 7PM | 🟠 MEDIUM | Phase 4 | Per-message working hours check |
| 11 | VIP frequency override too narrow | 🟢 LOW | Addendum B | `f_score >= 4` instead of `== 5` |
| 12 | WhatsApp Web disconnect not handled | 🟢 LOW | Phase 4 | Detect disconnect banner, pause all |

### Verdict

The plan's architecture is solid. The 3 CRITICAL bugs are all in data handling (transactions/insights) and would cause **silent data corruption** — the worst kind of bug because the owner wouldn't know until they see wrong messages going out. The 3 HIGH bugs are in classification logic and would cause **wrong segmentation** but wouldn't lose data.

**All 12 bugs have straightforward fixes.** None require architectural changes — they're all logic-level patches. I'd recommend applying all CRITICAL + HIGH fixes before starting implementation, and the MEDIUM fixes during implementation.
