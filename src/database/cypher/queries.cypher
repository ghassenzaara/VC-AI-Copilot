// Common Neo4j Queries for VC Intelligence Platform

// ============================================
// COMPANY QUERIES
// ============================================

// Get company by ID with all relationships
MATCH (c:Company {id: $company_id})
OPTIONAL MATCH (c)-[:HAS_CONTACT]->(p:Person)
OPTIONAL MATCH (c)-[:IN_SECTOR]->(s:Sector)
OPTIONAL MATCH (c)-[:TAGGED_WITH]->(t:Tag)
OPTIONAL MATCH (c)<-[:ABOUT]-(i:Interaction)
OPTIONAL MATCH (v:VCPartner)-[:OWNS]->(c)
RETURN c, collect(DISTINCT p) as contacts, s, collect(DISTINCT t) as tags, 
       collect(DISTINCT i) as interactions, collect(DISTINCT v) as owners;

// Find similar companies
MATCH (c:Company {id: $company_id})-[r:SIMILAR_TO]->(similar:Company)
WHERE r.score >= $threshold
RETURN similar, r.score
ORDER BY r.score DESC
LIMIT $limit;

// Search companies by sector and stage
MATCH (c:Company)-[:IN_SECTOR]->(s:Sector {name: $sector})
WHERE c.stage = $stage
RETURN c
ORDER BY c.last_touch_at DESC;

// Get companies by verdict
MATCH (c:Company)
WHERE c.verdict = $verdict
RETURN c
ORDER BY c.decided_at DESC;

// ============================================
// INTERACTION QUERIES
// ============================================

// Get recent interactions for a company
MATCH (c:Company {id: $company_id})<-[:ABOUT]-(i:Interaction)
RETURN i
ORDER BY i.occurred_at DESC
LIMIT $limit;

// Get all interactions involving a person
MATCH (p:Person {id: $person_id})-[:INVOLVES]-(i:Interaction)
RETURN i
ORDER BY i.occurred_at DESC;

// Get interactions by type and date range
MATCH (i:Interaction)-[:ABOUT]->(c:Company)
WHERE i.type = $interaction_type 
  AND i.occurred_at >= datetime($start_date)
  AND i.occurred_at <= datetime($end_date)
RETURN i, c
ORDER BY i.occurred_at DESC;

// ============================================
// PERSON & CONTACT QUERIES
// ============================================

// Get all contacts for a company
MATCH (c:Company {id: $company_id})-[:HAS_CONTACT]->(p:Person)
RETURN p
ORDER BY p.is_primary DESC, p.name;

// Find founders of a company
MATCH (p:Person)-[:FOUNDER_OF]->(c:Company {id: $company_id})
RETURN p;

// Get person with all their companies
MATCH (p:Person {id: $person_id})
OPTIONAL MATCH (p)-[:FOUNDER_OF]->(founded:Company)
OPTIONAL MATCH (p)-[:WORKS_AT]->(works:Company)
OPTIONAL MATCH (p)<-[:HAS_CONTACT]-(contact:Company)
RETURN p, collect(DISTINCT founded) as founded_companies, 
       collect(DISTINCT works) as works_at, 
       collect(DISTINCT contact) as contact_for;

// ============================================
// VC PARTNER QUERIES
// ============================================

// Get all companies owned by a VC partner
MATCH (v:VCPartner {id: $partner_id})-[:OWNS]->(c:Company)
RETURN c
ORDER BY c.last_touch_at DESC;

// Get VC partner's recent interactions
MATCH (v:VCPartner {id: $partner_id})-[:PARTICIPATED_IN]->(i:Interaction)
RETURN i
ORDER BY i.occurred_at DESC
LIMIT $limit;

// ============================================
// SECTOR & TAG QUERIES
// ============================================

// Get all companies in a sector
MATCH (c:Company)-[:IN_SECTOR]->(s:Sector {name: $sector_name})
RETURN c
ORDER BY c.last_touch_at DESC;

// Get companies with specific tags
MATCH (c:Company)-[:TAGGED_WITH]->(t:Tag)
WHERE t.name IN $tag_names
WITH c, collect(t.name) as tags
WHERE size(tags) = size($tag_names)
RETURN c, tags;

// Get tag distribution
MATCH (t:Tag)<-[:TAGGED_WITH]-(c:Company)
RETURN t.name, count(c) as company_count
ORDER BY company_count DESC;

// ============================================
// COMPETITOR QUERIES
// ============================================

// Find competitors of a company
MATCH (c:Company {id: $company_id})-[:COMPETED_WITH]->(competitor:Company)
RETURN competitor;

// Find companies competing in same space
MATCH (c:Company {id: $company_id})-[:IN_SECTOR]->(s:Sector)
MATCH (other:Company)-[:IN_SECTOR]->(s)
WHERE c <> other AND other.stage = c.stage
RETURN other
LIMIT $limit;

// ============================================
// ANALYTICS QUERIES
// ============================================

// Get pipeline summary by stage
MATCH (c:Company)
RETURN c.pipeline_stage as stage, count(c) as count
ORDER BY count DESC;

// Get deal momentum distribution
MATCH (c:Company)
WHERE c.deal_momentum IS NOT NULL
RETURN c.deal_momentum as momentum, count(c) as count
ORDER BY count DESC;

// Get companies by location
MATCH (c:Company)
WHERE c.location_country = $country
RETURN c.location_city as city, count(c) as count
ORDER BY count DESC;

// Get interaction frequency by type
MATCH (i:Interaction)
WHERE i.occurred_at >= datetime($start_date)
RETURN i.type as type, count(i) as count
ORDER BY count DESC;

// ============================================
// COMPLEX ANALYTICAL QUERIES
// ============================================

// Find hot deals (recent interactions + high momentum)
MATCH (c:Company)<-[:ABOUT]-(i:Interaction)
WHERE i.occurred_at >= datetime() - duration({days: 30})
  AND c.deal_momentum IN ['hot', 'very_hot']
WITH c, count(i) as interaction_count
RETURN c, interaction_count
ORDER BY interaction_count DESC
LIMIT $limit;

// Find similar companies with recent activity
MATCH (c:Company {id: $company_id})-[r:SIMILAR_TO]->(similar:Company)
MATCH (similar)<-[:ABOUT]-(i:Interaction)
WHERE r.score >= $threshold
  AND i.occurred_at >= datetime() - duration({days: $days})
WITH similar, r.score, count(i) as recent_interactions
RETURN similar, r.score, recent_interactions
ORDER BY r.score DESC, recent_interactions DESC
LIMIT $limit;

// Find companies needing follow-up
MATCH (c:Company)
WHERE c.next_step IS NOT NULL
  AND c.last_touch_at < datetime() - duration({days: 14})
  AND c.verdict NOT IN ['passed', 'invested']
RETURN c
ORDER BY c.last_touch_at ASC;

// Get network effect (companies connected through people)
MATCH (c1:Company {id: $company_id})-[:HAS_CONTACT]->(p:Person)<-[:HAS_CONTACT]-(c2:Company)
WHERE c1 <> c2
WITH c2, collect(DISTINCT p.name) as shared_contacts
RETURN c2, shared_contacts, size(shared_contacts) as connection_strength
ORDER BY connection_strength DESC
LIMIT $limit;