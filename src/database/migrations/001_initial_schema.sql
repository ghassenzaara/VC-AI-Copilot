-- VC Intelligence PostgreSQL Schema
-- Complete schema supporting full extraction_output_format.json

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- CORE TABLES
-- ============================================

-- Full interaction transcripts and content
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

-- Vector embeddings for semantic search
CREATE TABLE IF NOT EXISTS company_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id TEXT NOT NULL,
    embedding VECTOR(1536),
    embedding_text TEXT,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Extraction metadata
CREATE TABLE IF NOT EXISTS extraction_metadata (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id TEXT NOT NULL,
    model_used TEXT,
    confidence FLOAT,
    warnings JSONB,
    extracted_at TIMESTAMPTZ DEFAULT NOW()
);

-- Team debates (internal discussions)
CREATE TABLE IF NOT EXISTS team_debates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id TEXT NOT NULL,
    detected BOOLEAN,
    for_arguments JSONB,
    against_arguments JSONB,
    open_questions JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Decision records
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

-- Company snapshots (point-in-time data)
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

-- Company news articles
CREATE TABLE IF NOT EXISTS company_news (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id TEXT NOT NULL,
    headline TEXT NOT NULL,
    url TEXT,
    published_at DATE,
    source TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Company signals (hiring, funding, launches)
CREATE TABLE IF NOT EXISTS company_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id TEXT NOT NULL,
    label TEXT NOT NULL,
    detected_at DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- INDEXES
-- ============================================

-- Core table indexes
CREATE INDEX IF NOT EXISTS idx_interaction_content_neo4j_id ON interaction_content(neo4j_interaction_id);
CREATE INDEX IF NOT EXISTS idx_company_embeddings_company_id ON company_embeddings(company_id);
CREATE INDEX IF NOT EXISTS idx_extraction_metadata_company_id ON extraction_metadata(company_id);
CREATE INDEX IF NOT EXISTS idx_team_debates_company_id ON team_debates(company_id);
CREATE INDEX IF NOT EXISTS idx_decision_records_company_id ON decision_records(company_id);
CREATE INDEX IF NOT EXISTS idx_decision_records_verdict ON decision_records(verdict);

-- Company now indexes
CREATE INDEX IF NOT EXISTS idx_company_snapshots_company_id ON company_snapshots(company_id);
CREATE INDEX IF NOT EXISTS idx_company_snapshots_fetched_at ON company_snapshots(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_news_company_id ON company_news(company_id);
CREATE INDEX IF NOT EXISTS idx_company_news_published_at ON company_news(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_signals_company_id ON company_signals(company_id);
CREATE INDEX IF NOT EXISTS idx_company_signals_detected_at ON company_signals(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_signals_label ON company_signals(label);

-- Vector index for similarity search
CREATE INDEX IF NOT EXISTS idx_company_embeddings_vector 
ON company_embeddings 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);

-- ============================================
-- DOCUMENTATION
-- ============================================

-- Table comments
COMMENT ON TABLE interaction_content IS 'Full transcripts and detailed content from interactions';
COMMENT ON TABLE company_embeddings IS 'Vector embeddings for semantic similarity search';
COMMENT ON TABLE extraction_metadata IS 'Metadata about LLM extraction process';
COMMENT ON TABLE team_debates IS 'Internal team discussions and debates about companies';
COMMENT ON TABLE decision_records IS 'Investment decision records and rationale';
COMMENT ON TABLE company_snapshots IS 'Point-in-time snapshots of company data from external sources';
COMMENT ON TABLE company_news IS 'Latest news articles about companies';
COMMENT ON TABLE company_signals IS 'Detected signals about company activity (hiring, funding, etc.)';

-- Column comments (hybrid architecture references)
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

-- Made with Bob
