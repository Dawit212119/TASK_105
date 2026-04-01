# Business Logic Questions Log

## 1. Community Binding Constraints

**Question:** The prompt enforces "one active group leader per community" but does not clarify transition rules when replacing a leader.
**My Understanding:** Only one `active=true` binding exists at a time; replacing requires deactivating the previous record.
**Solution:** Enforce a unique partial index on `(community_id, active=true)` and require atomic swap (transaction: deactivate old → activate new).

---

## 2. Service Area vs Community Relationship

**Question:** It’s unclear whether a community can have multiple service areas or just one.
**My Understanding:** A community likely maps to multiple service areas (coverage zones).
**Solution:** Define `ServiceAreas` as a child table of `Communities` with one-to-many relation.

---

## 3. Commission Rule Overrides

**Question:** What happens when both default commission and category-specific commission exist?
**My Understanding:** Category-level overrides take precedence over defaults.
**Solution:** Implement priority resolution: `category_rule > community_default > system_default`.

---

## 4. Settlement Dispute Handling

**Question:** The 2-day dispute window is defined, but no resolution workflow is specified.
**My Understanding:** Disputes temporarily block settlement finalization.
**Solution:** Add `SettlementDisputes` table with status (open/resolved/rejected) and prevent payout until resolved.

---

## 5. Settlement Idempotency

**Question:** Idempotency key is required, but retry behavior is unclear.
**My Understanding:** Same key should not generate duplicate settlements.
**Solution:** Enforce unique constraint on `idempotency_key` and return existing result on retry.

---

## 6. Search “Trending” Definition

**Question:** “Trending” is based on last 7 days, but ranking logic is not defined.
**My Understanding:** Frequency-based ranking with decay over time.
**Solution:** Implement weighted scoring: `score = frequency / recency_factor`.

---

## 7. Zero-Result Guidance Logic

**Question:** How are "closest-match brands/tags" computed?
**My Understanding:** Likely fuzzy matching or similarity scoring.
**Solution:** Use trigram similarity or Levenshtein distance against brands/tags.

---

## 8. Inventory Costing Immutability

**Question:** FIFO vs moving-average is immutable after transactions, but migration strategy is unclear.
**My Understanding:** Each SKU locks costing method after first transaction.
**Solution:** Add `costing_method` column with constraint preventing updates after first transaction exists.

---

## 9. Inventory Adjustment Audit

**Question:** Adjustments require audit logs, but level of detail is not specified.
**My Understanding:** Every adjustment must include reason and user.
**Solution:** Append-only audit log with fields: `user_id`, `reason`, `before_qty`, `after_qty`.

---

## 10. Slow-Moving Inventory Threshold

**Question:** “No issue for 60 days” is defined, but does receipt reset the timer?
**My Understanding:** Only outbound movement (issue) resets the timer.
**Solution:** Track last issue timestamp per SKU; ignore receipts.

---

## 11. Messaging Storage Limits

**Question:** Attachments are metadata-only, but size/storage constraints are unclear.
**My Understanding:** Files are not stored, only references.
**Solution:** Validate metadata fields only and reject actual file storage.

---

## 12. Offline Message Redelivery

**Question:** Retry/backoff strategy is not defined.
**My Understanding:** Exponential backoff with max retry window of 7 days.
**Solution:** Implement retry queue with exponential delays capped at 7 days TTL.

---

## 13. Content Version Compatibility

**Question:** “Older versions remain parseable” lacks enforcement rules.
**My Understanding:** New versions must not break schema of old ones.
**Solution:** Enforce schema evolution rules: additive changes or explicit mapping functions.

---

## 14. Template Migration Rules

**Question:** Deterministic mapping is required but not defined.
**My Understanding:** Each migration must define field transformations.
**Solution:** Store migration functions or mapping configs per version pair.

---

## 15. Role-Based Data Scope

**Question:** Row-level access is mentioned but not fully defined per role.
**My Understanding:** Group leaders are scoped to their communities; others vary by role.
**Solution:** Implement row-level filters in ORM queries based on role + ownership context.

---

## 16. Soft Delete vs Hard Delete

**Question:** Deletion behavior is not defined.
**My Understanding:** System requires auditability → soft delete.
**Solution:** Add `deleted_at` field and exclude records in queries by default.

---

## 17. Attachment Storage Constraints

**Question:** Files are stored locally with 25MB limit, but cleanup policy is unclear.
**My Understanding:** Orphaned files should be cleaned.
**Solution:** Implement periodic job to remove unreferenced attachments.

---

## 18. API Latency Requirement Scope

**Question:** 300ms P99 applies to search, but unclear if filters/pagination included.
**My Understanding:** Applies to full search query including filters and sorting.
**Solution:** Add indexes on searchable fields and precompute trending data.

---

## 19. Audit Log Granularity

**Question:** “Immutable append-only log” but not clear which actions are included.
**My Understanding:** Includes moderation, settlement, and inventory changes only.
**Solution:** Centralize audit logging middleware for critical operations.

---

## 20. Authentication Lockout Reset

**Question:** Lockout is 15 minutes after 5 failures, but reset condition unclear.
**My Understanding:** Counter resets after successful login or timeout.
**Solution:** Track failed attempts with timestamp; reset after success or expiry.

---
