// VC Intelligence Neo4j Schema
// This schema defines the knowledge graph structure

// ============================================
// CONSTRAINTS (Unique identifiers)
// ============================================

// Company node
CREATE CONSTRAINT company_id IF NOT EXISTS
FOR (c:Company) REQUIRE c.id IS UNIQUE;

CREATE INDEX company_name IF NOT EXISTS
FOR (c:Company) ON (c.name);

CREATE INDEX company_sector IF NOT EXISTS
FOR (c:Company) ON (c.sector);

CREATE INDEX company_stage IF NOT EXISTS
FOR (c:Company) ON (c.stage);

CREATE INDEX company_verdict IF NOT EXISTS
FOR (c:Company) ON (c.verdict);

// Person node
CREATE CONSTRAINT person_id IF NOT EXISTS
FOR (p:Person) REQUIRE p.id IS UNIQUE;

CREATE INDEX person_email IF NOT EXISTS
FOR (p:Person) ON (p.email);

// VCPartner node
CREATE CONSTRAINT vc_partner_id IF NOT EXISTS
FOR (v:VCPartner) REQUIRE v.id IS UNIQUE;

CREATE INDEX vc_partner_name IF NOT EXISTS
FOR (v:VCPartner) ON (v.name);

// Interaction node
CREATE CONSTRAINT interaction_id IF NOT EXISTS
FOR (i:Interaction) REQUIRE i.id IS UNIQUE;

CREATE INDEX interaction_type IF NOT EXISTS
FOR (i:Interaction) ON (i.type);

CREATE INDEX interaction_occurred_at IF NOT EXISTS
FOR (i:Interaction) ON (i.occurred_at);

// Sector node
CREATE CONSTRAINT sector_name IF NOT EXISTS
FOR (s:Sector) REQUIRE s.name IS UNIQUE;

// Tag node
CREATE CONSTRAINT tag_name IF NOT EXISTS
FOR (t:Tag) REQUIRE t.name IS UNIQUE;

// Cluster node (for market map clustering)
CREATE CONSTRAINT cluster_id IF NOT EXISTS
FOR (cl:Cluster) REQUIRE cl.id IS UNIQUE;

CREATE INDEX cluster_name IF NOT EXISTS
FOR (cl:Cluster) ON (cl.name);

CREATE INDEX cluster_number IF NOT EXISTS
FOR (cl:Cluster) ON (cl.cluster_number);

// ============================================
// SAMPLE QUERIES (for reference)
// ============================================

// Find all companies in a sector
// MATCH (c:Company)-[:IN_SECTOR]->(s:Sector {name: "AI"})
// RETURN c;

// Find similar companies
// MATCH (c:Company {name: "Example Corp"})-[r:SIMILAR_TO]->(similar:Company)
// WHERE r.score > 0.8
// RETURN similar.name, r.score
// ORDER BY r.score DESC;

// Find all interactions for a company
// MATCH (c:Company {name: "Example Corp"})<-[:ABOUT]-(i:Interaction)
// RETURN i
// ORDER BY i.occurred_at DESC;

// Find companies owned by a VC partner
// MATCH (v:VCPartner {name: "John Doe"})-[:OWNS]->(c:Company)
// RETURN c;

// Find founders of a company
// MATCH (p:Person)-[:FOUNDER_OF]->(c:Company {name: "Example Corp"})
// RETURN p;

// Find all contacts for a company
// MATCH (c:Company {name: "Example Corp"})-[:HAS_CONTACT]->(p:Person)
// RETURN p;

// Find companies with specific tags
// MATCH (c:Company)-[:TAGGED_WITH]->(t:Tag)
// WHERE t.name IN ["B2B", "SaaS"]
// RETURN c, collect(t.name) as tags;

// Find competitors
// MATCH (c:Company {name: "Example Corp"})-[:COMPETED_WITH]->(competitor:Company)
// RETURN competitor;

// Complex query: Find similar companies in same sector with recent interactions
// MATCH (c:Company {name: "Example Corp"})-[:SIMILAR_TO]->(similar:Company)
// MATCH (similar)-[:IN_SECTOR]->(s:Sector)
// MATCH (similar)<-[:ABOUT]-(i:Interaction)
// WHERE i.occurred_at > datetime() - duration({days: 30})
// RETURN similar.name, s.name, count(i) as recent_interactions
// ORDER BY recent_interactions DESC;

// Find all companies in a cluster
// MATCH (c:Company)-[:BELONGS_TO_CLUSTER]->(cl:Cluster {name: "Enterprise AI Infrastructure"})
// RETURN c.name, c.sector, c.stage
// ORDER BY c.name;

// Find cluster for a specific company
// MATCH (c:Company {name: "Example Corp"})-[:BELONGS_TO_CLUSTER]->(cl:Cluster)
// RETURN cl.name, cl.description;

// Get cluster statistics
// MATCH (cl:Cluster)<-[:BELONGS_TO_CLUSTER]-(c:Company)
// RETURN cl.name, cl.cluster_number, count(c) as company_count
// ORDER BY company_count DESC;