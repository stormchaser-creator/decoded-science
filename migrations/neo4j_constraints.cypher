// Neo4j constraints and indexes for the Decoded pipeline
// Run: cypher-shell -u neo4j -p <password> < migrations/neo4j_constraints.cypher

// ---- Node uniqueness constraints ----

CREATE CONSTRAINT paper_id IF NOT EXISTS
    FOR (p:Paper) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT entity_id IF NOT EXISTS
    FOR (e:Entity) REQUIRE e.id IS UNIQUE;

CREATE CONSTRAINT concept_name IF NOT EXISTS
    FOR (c:Concept) REQUIRE c.name IS UNIQUE;

// ---- Indexes for common lookups ----

CREATE INDEX paper_title IF NOT EXISTS
    FOR (p:Paper) ON (p.title);

CREATE INDEX paper_published IF NOT EXISTS
    FOR (p:Paper) ON (p.published_date);

CREATE INDEX paper_status IF NOT EXISTS
    FOR (p:Paper) ON (p.status);

CREATE INDEX entity_type IF NOT EXISTS
    FOR (e:Entity) ON (e.entity_type);

CREATE INDEX entity_text IF NOT EXISTS
    FOR (e:Entity) ON (e.text);

CREATE INDEX concept_type IF NOT EXISTS
    FOR (c:Concept) ON (c.concept_type);

// ---- Relationship indexes ----

CREATE INDEX connection_type IF NOT EXISTS
    FOR ()-[r:CONNECTS]-() ON (r.connection_type);

CREATE INDEX connection_confidence IF NOT EXISTS
    FOR ()-[r:CONNECTS]-() ON (r.confidence);

RETURN "Neo4j schema initialized" AS status;
