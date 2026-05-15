# Data Source Forms

## 1. Granola — Note

**Kept fields:**

```json
{
  "id": "not_1d3tmYTlCICgjy",
  "title": "Acme AI - Intro Call",
  "owner": {
    "name": "Ahmed Zaara",
    "email": "ahmed@yellowvc.com"
  },
  "created_at": "2026-04-28T14:00:00Z",
  "calendar_event": {
    "scheduled_start_time": "2026-04-28T14:00:00Z",
    "scheduled_end_time": "2026-04-28T14:45:00Z",
    "organiser": "ahmed@yellowvc.com"
  },
  "attendees": [
    { "name": "Ahmed Zaara", "email": "ahmed@yellowvc.com" },
    { "name": "Sara Chen",   "email": "sara@acme.ai" }
  ],
  "summary_text": "Met with Sara Chen from Acme AI. B2B logistics platform, pre-seed stage, €10K MRR, 5 enterprise customers. Strong team, ex-Google engineers. Market size unclear. Ahmed to follow up in 6 weeks.",
  "transcript": [
    {
      "speaker": { "source": "microphone" },
      "text": "So tell me about your traction so far",
      "start_time": "2026-04-28T14:02:00Z",
      "end_time": "2026-04-28T14:02:14Z"
    },
    {
      "speaker": { "source": "speaker" },
      "text": "We have 5 enterprise customers paying €2K MRR each",
      "start_time": "2026-04-28T14:02:15Z",
      "end_time": "2026-04-28T14:02:40Z"
    }
  ]
}
```

**Dropped:** `updated_at`, `summary_markdown`, `folder_membership`

---

## 2. Affinity — 6 Objects

**Object 1 — Organization**
```json
{
  "id": 7133202,
  "name": "Acme AI",
  "domain": "acme.ai",
  "domains": ["acme.ai"],
  "person_ids": [89734],
  "opportunity_ids": [4],
  "interaction_dates": {
    "last_event_date": "2026-04-28T14:00:00Z",
    "next_event_date": "2026-06-09T14:00:00Z"
  }
}
```

**Object 2 — Person**
```json
{
  "id": 89734,
  "first_name": "Sara",
  "last_name": "Chen",
  "primary_email": "sara@acme.ai",
  "emails": ["sara@acme.ai"],
  "organization_ids": [7133202]
}
```

**Object 3 — Opportunity**
```json
{
  "id": 4,
  "name": "Acme AI - Seed Round",
  "organization_ids": [7133202],
  "person_ids": [89734],
  "list_entries": [
    {
      "list_id": 12058,
      "created_at": "2026-04-28T14:00:00Z"
    }
  ]
}
```

**Object 4 — Field Values**
```json
[
  { "field_id": 61223, "entity_id": 7133202, "value": "B2B SaaS" },
  { "field_id": 61224, "entity_id": 7133202, "value": "Pre-seed" },
  { "field_id": 61225, "entity_id": 7133202, "value": 10000 },
  { "field_id": 61226, "entity_id": 7133202, "value": "Berlin" },
  { "field_id": 61227, "entity_id": 7133202, "value": "Positive" },
  { "field_id": 61228, "entity_id": 7133202, "value": "Ahmed" },
  { "field_id": 61229, "entity_id": 7133202, "value": "2026-06-09" }
]
```

**Object 5 — Notes**
```json
[
  {
    "id": 9001,
    "content": "Strong team, ex-Google. Market size unclear. Follow up in 6 weeks.",
    "created_at": "2026-04-28T14:00:00Z",
    "person_ids": [89734]
  }
]
```

**Object 6 — Interactions**
```json
{
  "last_event_date": "2026-04-28T14:00:00Z",
  "next_event_date": "2026-06-09T14:00:00Z"
}
```

---

## 3. Gmail — Message

**Kept fields:**

```json
{
  "id": "msg_18e4f2a1b3c",
  "threadId": "thread_18e4f2a1b3c",
  "internalDate": "1714384500000",
  "payload": {
    "headers": [
      { "name": "From",    "value": "sara@acme.ai" },
      { "name": "To",      "value": "ahmed@yellowvc.com" },
      { "name": "Subject", "value": "Follow up - Acme AI seed deck" },
      { "name": "Date",    "value": "2026-04-29T09:15:00Z" }
    ],
    "parts": [
      {
        "mimeType": "text/plain",
        "body": {
          "data": "Hi Ahmed, great speaking yesterday. Attaching our updated deck with the market size breakdown you requested. We are targeting €500K at €3M pre-money."
        }
      }
    ]
  },
  "snippet": "Hi Ahmed, great speaking yesterday..."
}
```

**Dropped:** `labelIds`, `sizeEstimate`, `historyId`, `raw`

---

## 4. Slack — 3 Objects

**Object 1 — Message**
```json
{
  "ts": "1714308000.000200",
  "user": "U012AB3CDE",
  "text": "Just got off a call with Acme AI, really strong founder",
  "thread_ts": "1714308000.000200",
  "reply_count": 2,
  "reactions": [
    { "name": "thumbsup", "count": 2 }
  ]
}
```

**Dropped:** `blocks`, `attachments`, `edited`, `is_starred`, `pinned_to`

**Object 2 — Channel**
```json
{
  "id": "C123ABC456",
  "name": "deal-flow",
  "is_private": false
}
```

**Object 3 — User**
```json
{
  "id": "U012AB3CDE",
  "real_name": "Ahmed Zaara",
  "profile": {
    "email": "ahmed@yellowvc.com",
    "title": "Partner"
  }
}
```

**Note:** In mock data, `user` field in messages is pre-resolved to `real_name` — no raw user ID lookup needed.
