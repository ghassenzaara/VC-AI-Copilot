-- VC Intelligence PostgreSQL Schema (multi-tenant: per-clerk_id isolation)

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- USERS (tenant root)
-- ============================================

CREATE TABLE IF NOT EXISTS users (
    clerk_id     TEXT PRIMARY KEY,
    email        TEXT,
    full_name    TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================
-- CORE TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS interaction_content (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_clerk_id TEXT NOT NULL REFERENCES users(clerk_id) ON DELETE CASCADE,
    neo4j_interaction_id TEXT NOT NULL,
    full_transcript TEXT,
    summary TEXT,
    takeaways JSONB,
    topics JSONB,
    quotes JSONB,
    metrics_mentioned JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (owner_clerk_id, neo4j_interaction_id)
);

-- One embedding row per (user, company) — upsert key.
CREATE TABLE IF NOT EXISTS company_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_clerk_id TEXT NOT NULL REFERENCES users(clerk_id) ON DELETE CASCADE,
    company_id TEXT NOT NULL,
    embedding VECTOR(768),
    embedding_text TEXT,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (owner_clerk_id, company_id)
);

CREATE TABLE IF NOT EXISTS extraction_metadata (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_clerk_id TEXT NOT NULL REFERENCES users(clerk_id) ON DELETE CASCADE,
    company_id TEXT NOT NULL,
    model_used TEXT,
    confidence FLOAT,
    warnings JSONB,
    extracted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS team_debates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_clerk_id TEXT NOT NULL REFERENCES users(clerk_id) ON DELETE CASCADE,
    company_id TEXT NOT NULL,
    detected BOOLEAN,
    for_arguments JSONB,
    against_arguments JSONB,
    open_questions JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS decision_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_clerk_id TEXT NOT NULL REFERENCES users(clerk_id) ON DELETE CASCADE,
    company_id TEXT NOT NULL,
    verdict TEXT CHECK (verdict IN ('tracking', 'diligence', 'invested', 'passed')),
    rationale TEXT,
    conditions JSONB,
    check_size TEXT,
    valuation TEXT,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- COMPANY NOW TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS company_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_clerk_id TEXT NOT NULL REFERENCES users(clerk_id) ON DELETE CASCADE,
    company_id TEXT NOT NULL,
    domain TEXT,
    headcount INT,
    open_roles INT,
    funding JSONB,
    fetched_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_news (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_clerk_id TEXT NOT NULL REFERENCES users(clerk_id) ON DELETE CASCADE,
    company_id TEXT NOT NULL,
    headline TEXT NOT NULL,
    url TEXT,
    published_at DATE,
    source TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_clerk_id TEXT NOT NULL REFERENCES users(clerk_id) ON DELETE CASCADE,
    company_id TEXT NOT NULL,
    label TEXT NOT NULL,
    detected_at DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- MARKET MAP CLUSTERING TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS market_clusters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_clerk_id TEXT NOT NULL REFERENCES users(clerk_id) ON DELETE CASCADE,
    cluster_number INT NOT NULL,
    name TEXT,
    description TEXT,
    centroid VECTOR(768),
    company_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (owner_clerk_id, cluster_number)
);

CREATE TABLE IF NOT EXISTS company_cluster_assignments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_clerk_id TEXT NOT NULL REFERENCES users(clerk_id) ON DELETE CASCADE,
    company_id TEXT NOT NULL,
    cluster_id UUID NOT NULL REFERENCES market_clusters(id) ON DELETE CASCADE,
    distance_to_centroid FLOAT,
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (owner_clerk_id, company_id)
);

CREATE TABLE IF NOT EXISTS cluster_metadata (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_clerk_id TEXT NOT NULL REFERENCES users(clerk_id) ON DELETE CASCADE,
    cluster_id UUID NOT NULL REFERENCES market_clusters(id) ON DELETE CASCADE,
    common_sectors JSONB,
    common_stages JSONB,
    common_tags JSONB,
    avg_deal_momentum TEXT,
    sample_companies JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- INDEXES
-- ============================================

CREATE INDEX IF NOT EXISTS idx_interaction_content_neo4j_id ON interaction_content(neo4j_interaction_id);
CREATE INDEX IF NOT EXISTS idx_interaction_content_owner ON interaction_content(owner_clerk_id);
CREATE INDEX IF NOT EXISTS idx_company_embeddings_owner_company ON company_embeddings(owner_clerk_id, company_id);
CREATE INDEX IF NOT EXISTS idx_company_embeddings_owner ON company_embeddings(owner_clerk_id);
CREATE INDEX IF NOT EXISTS idx_extraction_metadata_owner_company ON extraction_metadata(owner_clerk_id, company_id);
CREATE INDEX IF NOT EXISTS idx_team_debates_owner_company ON team_debates(owner_clerk_id, company_id);
CREATE INDEX IF NOT EXISTS idx_decision_records_owner_company ON decision_records(owner_clerk_id, company_id);
CREATE INDEX IF NOT EXISTS idx_decision_records_verdict ON decision_records(verdict);
CREATE INDEX IF NOT EXISTS idx_company_snapshots_owner_company ON company_snapshots(owner_clerk_id, company_id);
CREATE INDEX IF NOT EXISTS idx_company_snapshots_fetched_at ON company_snapshots(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_news_owner_company ON company_news(owner_clerk_id, company_id);
CREATE INDEX IF NOT EXISTS idx_company_news_published_at ON company_news(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_signals_owner_company ON company_signals(owner_clerk_id, company_id);
CREATE INDEX IF NOT EXISTS idx_company_signals_detected_at ON company_signals(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_signals_label ON company_signals(label);

-- Clustering indexes
CREATE INDEX IF NOT EXISTS idx_cluster_assignments_owner ON company_cluster_assignments(owner_clerk_id);
CREATE INDEX IF NOT EXISTS idx_cluster_assignments_cluster ON company_cluster_assignments(cluster_id);
CREATE INDEX IF NOT EXISTS idx_cluster_metadata_cluster ON cluster_metadata(cluster_id);
CREATE INDEX IF NOT EXISTS idx_market_clusters_owner ON market_clusters(owner_clerk_id);
CREATE INDEX IF NOT EXISTS idx_market_clusters_name ON market_clusters(name);

CREATE INDEX IF NOT EXISTS idx_company_embeddings_vector
    ON company_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ============================================
-- COMMENTS
-- ============================================

COMMENT ON TABLE users IS 'Tenant root: one row per Clerk user, FK target for every domain table';
COMMENT ON COLUMN users.clerk_id IS 'Clerk subject (sub claim from JWT)';
COMMENT ON TABLE interaction_content IS 'Full transcripts and detailed content from interactions';
COMMENT ON TABLE company_embeddings IS 'Vector embeddings (768-dim) for semantic similarity search, per user';
COMMENT ON TABLE extraction_metadata IS 'Metadata about LLM extraction process, per user';
COMMENT ON TABLE team_debates IS 'Internal team discussions and debates about companies, per user';
COMMENT ON TABLE decision_records IS 'Investment decision records and rationale, per user';
COMMENT ON TABLE company_snapshots IS 'Point-in-time snapshots of company data from external sources';
COMMENT ON TABLE company_news IS 'Latest news articles about companies';
COMMENT ON TABLE company_signals IS 'Detected signals about company activity (hiring, funding, etc.)';

-- Clustering table comments
COMMENT ON TABLE market_clusters IS 'Market map clusters with LLM-generated names, per user';
COMMENT ON TABLE company_cluster_assignments IS 'Company-to-cluster assignments for market map, per user';
COMMENT ON TABLE cluster_metadata IS 'Aggregated metadata for LLM cluster naming, per user';
