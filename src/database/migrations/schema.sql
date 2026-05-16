-- VC Intelligence PostgreSQL Schema

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- CORE TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS interaction_content (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    neo4j_interaction_id TEXT NOT NULL,
    full_transcript TEXT,
    summary TEXT,
    takeaways JSONB,
    topics JSONB,
    quotes JSONB,
    metrics_mentioned JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- One embedding row per company (UNIQUE on company_id prevents accumulation
-- across pipeline reruns; the postgres writer upserts on this constraint).
CREATE TABLE IF NOT EXISTS company_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id TEXT NOT NULL UNIQUE,
    embedding VECTOR(768),
    embedding_text TEXT,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS extraction_metadata (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id TEXT NOT NULL,
    model_used TEXT,
    confidence FLOAT,
    warnings JSONB,
    extracted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS team_debates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id TEXT NOT NULL,
    detected BOOLEAN,
    for_arguments JSONB,
    against_arguments JSONB,
    open_questions JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS decision_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
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
    company_id TEXT NOT NULL,
    headline TEXT NOT NULL,
    url TEXT,
    published_at DATE,
    source TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id TEXT NOT NULL,
    label TEXT NOT NULL,
    detected_at DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- MARKET MAP CLUSTERING TABLES
-- ============================================

-- Cluster definitions
CREATE TABLE IF NOT EXISTS market_clusters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cluster_number INT NOT NULL,
    name TEXT,  -- LLM-generated name
    description TEXT,  -- LLM-generated description
    centroid VECTOR(768),  -- Cluster center in embedding space
    company_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(cluster_number)
);

-- Company-to-cluster assignments
CREATE TABLE IF NOT EXISTS company_cluster_assignments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id TEXT NOT NULL REFERENCES company_embeddings(company_id),
    cluster_id UUID NOT NULL REFERENCES market_clusters(id),
    distance_to_centroid FLOAT,  -- How close to cluster center
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_id)  -- Each company in exactly one cluster
);

-- Cluster metadata (for LLM naming context)
CREATE TABLE IF NOT EXISTS cluster_metadata (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cluster_id UUID NOT NULL REFERENCES market_clusters(id),
    common_sectors JSONB,  -- ["AI Infrastructure", "B2B SaaS"]
    common_stages JSONB,   -- ["Seed", "Series A"]
    common_tags JSONB,     -- ["B2B", "Enterprise", "AI"]
    avg_deal_momentum TEXT,  -- "accelerating" | "stable" | etc.
    sample_companies JSONB,  -- [{name, one_liner}] for LLM context
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- INDEXES
-- ============================================

CREATE INDEX IF NOT EXISTS idx_interaction_content_neo4j_id ON interaction_content(neo4j_interaction_id);
CREATE INDEX IF NOT EXISTS idx_company_embeddings_company_id ON company_embeddings(company_id);
CREATE INDEX IF NOT EXISTS idx_extraction_metadata_company_id ON extraction_metadata(company_id);
CREATE INDEX IF NOT EXISTS idx_team_debates_company_id ON team_debates(company_id);
CREATE INDEX IF NOT EXISTS idx_decision_records_company_id ON decision_records(company_id);
CREATE INDEX IF NOT EXISTS idx_decision_records_verdict ON decision_records(verdict);
CREATE INDEX IF NOT EXISTS idx_company_snapshots_company_id ON company_snapshots(company_id);
CREATE INDEX IF NOT EXISTS idx_company_snapshots_fetched_at ON company_snapshots(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_news_company_id ON company_news(company_id);
CREATE INDEX IF NOT EXISTS idx_company_news_published_at ON company_news(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_signals_company_id ON company_signals(company_id);
CREATE INDEX IF NOT EXISTS idx_company_signals_detected_at ON company_signals(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_signals_label ON company_signals(label);

-- Clustering indexes
CREATE INDEX IF NOT EXISTS idx_cluster_assignments_company ON company_cluster_assignments(company_id);
CREATE INDEX IF NOT EXISTS idx_cluster_assignments_cluster ON company_cluster_assignments(cluster_id);
CREATE INDEX IF NOT EXISTS idx_cluster_metadata_cluster ON cluster_metadata(cluster_id);
CREATE INDEX IF NOT EXISTS idx_market_clusters_name ON market_clusters(name);

CREATE INDEX IF NOT EXISTS idx_company_embeddings_vector
    ON company_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ============================================
-- COMMENTS
-- ============================================

COMMENT ON TABLE interaction_content IS 'Full transcripts and detailed content from interactions';
COMMENT ON TABLE company_embeddings IS 'Vector embeddings (768-dim) for semantic similarity search';
COMMENT ON TABLE extraction_metadata IS 'Metadata about LLM extraction process';
COMMENT ON TABLE team_debates IS 'Internal team discussions and debates about companies';
COMMENT ON TABLE decision_records IS 'Investment decision records and rationale';
COMMENT ON TABLE company_snapshots IS 'Point-in-time snapshots of company data from external sources';
COMMENT ON TABLE company_news IS 'Latest news articles about companies';
COMMENT ON TABLE company_signals IS 'Detected signals about company activity (hiring, funding, etc.)';

COMMENT ON COLUMN interaction_content.neo4j_interaction_id IS 'References Neo4j Interaction.id';
COMMENT ON COLUMN interaction_content.topics IS 'Array of topic strings discussed in the interaction';
COMMENT ON COLUMN company_embeddings.company_id IS 'References Neo4j Company.id';
COMMENT ON COLUMN extraction_metadata.company_id IS 'References Neo4j Company.id';
COMMENT ON COLUMN team_debates.company_id IS 'References Neo4j Company.id';
COMMENT ON COLUMN decision_records.company_id IS 'References Neo4j Company.id';
COMMENT ON COLUMN decision_records.verdict IS 'Investment decision: tracking | diligence | invested | passed';
COMMENT ON COLUMN decision_records.check_size IS 'Investment check size (e.g., "$500K", "$2M")';
COMMENT ON COLUMN decision_records.valuation IS 'Company valuation at decision time';
COMMENT ON COLUMN company_snapshots.company_id IS 'References Neo4j Company.id';
COMMENT ON COLUMN company_news.company_id IS 'References Neo4j Company.id';
COMMENT ON COLUMN company_signals.company_id IS 'References Neo4j Company.id';

-- Clustering table comments
COMMENT ON TABLE market_clusters IS 'Market map clusters with LLM-generated names';
COMMENT ON TABLE company_cluster_assignments IS 'Company-to-cluster assignments for market map';
COMMENT ON TABLE cluster_metadata IS 'Aggregated metadata for LLM cluster naming';
COMMENT ON COLUMN market_clusters.centroid IS 'Cluster center in 768-dimensional embedding space';
COMMENT ON COLUMN market_clusters.name IS 'LLM-generated cluster name (e.g., "Enterprise AI Infrastructure")';
COMMENT ON COLUMN company_cluster_assignments.distance_to_centroid IS 'Euclidean distance from company embedding to cluster centroid';
