# Bug Fix Summary - Data Ingestion Connectors

## Overview
This document tracks all bug fixes applied to the data ingestion layer based on the comprehensive audit.

## Critical Fixes (Blockers)

### 1. ✅ Affinity Authentication - FIXED
**Issue:** Used `Bearer` token instead of HTTP Basic Auth
**Location:** `src/ingestion/affinity.py:46-49`
**Fix:** Changed to Basic Auth with base64 encoding (empty username, API key as password)
```python
auth_string = base64.b64encode(f":{self.api_key}".encode()).decode()
self.headers = {"Authorization": f"Basic {auth_string}", ...}
```

### 2. 🔄 Gmail OAuth Token Persistence - IN PROGRESS
**Issue:** Re-runs browser flow on every authenticate(), no token caching
**Location:** `src/ingestion/gmail.py:48-55`
**Fix Required:**
- Add token.json persistence
- Check for existing token before running flow
- Implement token refresh with `creds.refresh(Request())`
- Make authenticate() idempotent

### 3. 🔄 Slack Timestamp Timezone - IN PROGRESS
**Issue:** `datetime.fromtimestamp()` returns local time but labeled as UTC
**Location:** `src/ingestion/slack.py:319-327`
**Fix Required:**
```python
dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)  # Force UTC
return dt.isoformat().replace('+00:00', 'Z')
```

### 4. 🔄 occurred_at Normalization - IN PROGRESS
**Issue:** Four different timestamp formats across connectors
**Solution:** Created `src/ingestion/utils.py` with `normalize_to_utc_iso()` function
**Applies to:**
- Granola: ISO 8601 ✓ (already correct)
- Gmail: RFC 2822 OR milliseconds string (needs fix)
- Affinity: ISO 8601 OR empty string (needs fix)
- Slack: Wrong timezone ISO (needs fix)

## High-Impact Fixes

### 5. 🔄 Slack ID Collision - IN PROGRESS
**Issue:** `id=f"slack_{message.ts}"` - ts only unique per channel
**Location:** `src/ingestion/slack.py:290`
**Fix Required:**
```python
id=f"slack_{channel.id}_{message.ts}"
```

### 6. ✅ Pydantic v2 Migration - FIXED
**Issue:** Mixed v1 (.dict()) and v2 (pydantic-settings) usage
**Fix:** Changed all `.dict()` calls to `.model_dump()`
**Locations:**
- `granola.py:181, 192`
- `affinity.py:180, 293, 316`
- `gmail.py:203`
- `slack.py:208, 308`

### 7. ✅ UnifiedInteraction.type Enum - FIXED
**Issue:** Docstring says one thing, code emits another ("crm_record", "slack_message")
**Location:** `src/ingestion/models.py:235`
**Fix:** Added `Literal["meeting", "email", "message", "note"]` and documentation
**Connector Fixes Needed:**
- `affinity.py:303` - Change "crm_record" to "note"
- `slack.py:292` - Change "slack_message" to "message"

### 8. 🔄 Granola Transcript Speakers - IN PROGRESS
**Issue:** "microphone:" and "speaker:" are channels, not names
**Location:** `src/ingestion/granola.py:166-169`
**Fix Required:**
- Map "microphone" → owner email
- Map "speaker" → other attendees
- Or remove misleading labels entirely

### 9. 🔄 Slack Participant Extraction - IN PROGRESS
**Issue:** Overwrites user ID with name, then tries to match back; bot messages ignored
**Location:** `slack.py:166-168, 268-278`
**Fix Required:**
- Keep original user ID for matching
- Handle bot messages (bot_id field)
- Resolve users properly

### 10. 🔄 Affinity Empty occurred_at - IN PROGRESS
**Issue:** Can emit empty string when no interactions
**Location:** `affinity.py:306`
**Fix Required:**
```python
occurred_at=safe_get_last_event_date(affinity_data.interactions)
```

## Architectural Fixes

### 11. 🔄 BaseConnector.validate_data - IN PROGRESS
**Issue:** Dead code, only checks isinstance(dict) and len > 0
**Location:** `src/ingestion/base.py:62-73`
**Decision:** Remove or make subclasses override with meaningful validation

### 12. 🔄 Repeated Authentication - IN PROGRESS
**Issue:** `ingest()` calls `authenticate()` every time
**Location:** `src/ingestion/base.py:86-89`
**Fix:** Make authenticate() idempotent, cache auth state

### 13. 🔄 Inconsistent Return Types - IN PROGRESS
**Issue:** Affinity returns aggregated bundles, others return flat items
**Location:** `affinity.py:85-99` vs others
**Decision:** Document the asymmetry or normalize

### 14. 🔄 Gmail OAuth Contract Violation - IN PROGRESS
**Issue:** Gmail doesn't use api_key but inherits BaseConnector
**Location:** `gmail.py:29-39`
**Fix:** Either make BaseConnector more flexible or document the exception

### 15. ✅ Type Enum Documentation - FIXED
**Issue:** Pre-LLM type vs post-LLM type confusion
**Location:** `src/ingestion/models.py:231-241`
**Fix:** Added clear documentation distinguishing the two

## Implementation Status

### Completed (5/15)
- [x] Affinity Basic Auth
- [x] Pydantic v2 model_dump()
- [x] UnifiedInteraction.type Literal
- [x] Type enum documentation
- [x] Created utils.py with normalize_to_utc_iso()

### In Progress (10/15)
- [ ] Gmail OAuth token persistence
- [ ] Slack timezone fix
- [ ] occurred_at normalization in all connectors
- [ ] Slack ID collision fix
- [ ] Granola speaker mapping
- [ ] Slack participant extraction
- [ ] Affinity empty occurred_at
- [ ] validate_data cleanup
- [ ] Auth caching
- [ ] Return type consistency

## Next Steps

1. Fix Gmail OAuth with token.json persistence
2. Apply normalize_to_utc_iso() to all connectors
3. Fix Slack ID collision and timezone
4. Fix type enum violations in Affinity and Slack
5. Improve Granola speaker resolution
6. Clean up architectural issues

## Testing Required

After all fixes:
1. Test each connector against real APIs
2. Verify timestamp normalization
3. Confirm no Pydantic v2 warnings
4. Validate UnifiedInteraction type constraints
5. Check for ID collisions in Slack
6. Verify OAuth token persistence in Gmail