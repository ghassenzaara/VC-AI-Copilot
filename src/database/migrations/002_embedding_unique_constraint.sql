-- Migration 002: Add uniqueness on company_embeddings.company_id so we can
-- upsert one row per company instead of appending forever (BUG-065).

-- Deduplicate any pre-existing rows: keep the latest per company_id.
DELETE FROM company_embeddings a
USING company_embeddings b
WHERE a.company_id = b.company_id
  AND a.generated_at < b.generated_at;

-- Now safe to add the unique constraint.
ALTER TABLE company_embeddings
    ADD CONSTRAINT uniq_company_embedding UNIQUE (company_id);

-- Made with Bob
