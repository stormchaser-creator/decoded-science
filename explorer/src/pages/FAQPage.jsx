import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { s, useIsMobile } from '../shared.js'

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: '48px' }}>
      <h2 style={{ fontSize: '20px', fontWeight: '700', color: '#c4bef8', margin: '0 0 16px', paddingBottom: '8px', borderBottom: '1px solid #1e1e2e' }}>
        {title}
      </h2>
      {children}
    </div>
  )
}

function Prose({ children }) {
  return (
    <p style={{ fontSize: '14px', color: '#9991d0', lineHeight: '1.8', margin: '0 0 14px' }}>
      {children}
    </p>
  )
}

function QA({ question, children, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen || false)
  return (
    <div
      style={{
        ...s.card,
        padding: 0,
        marginBottom: '8px',
        borderColor: open ? '#2d2060' : '#1e1e2e',
        transition: 'border-color 0.2s',
      }}
    >
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          width: '100%',
          padding: '16px 20px',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
          gap: '12px',
        }}
      >
        <span style={{ fontSize: '14px', fontWeight: '600', color: open ? '#c4bef8' : '#e0e0e8', lineHeight: '1.5' }}>
          {question}
        </span>
        <span style={{ fontSize: '18px', color: '#7c6af7', flexShrink: 0, transform: open ? 'rotate(45deg)' : 'none', transition: 'transform 0.2s' }}>
          +
        </span>
      </button>
      {open && (
        <div style={{ padding: '0 20px 16px', borderTop: '1px solid #1e1e2e' }}>
          <div style={{ paddingTop: '14px' }}>
            {children}
          </div>
        </div>
      )}
    </div>
  )
}

function NavFeature({ icon, title, to, children }) {
  return (
    <div style={{ ...s.card, padding: '20px', borderLeft: '3px solid #2d2060' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
        <span style={{ fontSize: '20px' }}>{icon}</span>
        <Link to={to} style={{ fontSize: '15px', fontWeight: '700', color: '#7c6af7', textDecoration: 'none' }}>
          {title} &rarr;
        </Link>
      </div>
      <div style={{ fontSize: '13px', color: '#9991d0', lineHeight: '1.8' }}>
        {children}
      </div>
    </div>
  )
}

function Term({ label, children }) {
  return (
    <div style={{ display: 'flex', gap: '12px', paddingBottom: '12px', marginBottom: '12px', borderBottom: '1px solid #1e1e2e' }}>
      <div style={{ fontSize: '12px', fontWeight: '700', color: '#4ade80', flexShrink: 0, width: '160px', textTransform: 'uppercase', letterSpacing: '0.3px' }}>{label}</div>
      <div style={{ fontSize: '13px', color: '#9991d0', lineHeight: '1.7' }}>{children}</div>
    </div>
  )
}

export default function FAQPage() {
  const isMobile = useIsMobile()
  return (
    <div style={{ ...s.page, maxWidth: '780px', margin: '0 auto', padding: isMobile ? '16px' : '24px' }}>
      {/* Hero */}
      <div style={{ textAlign: 'center', paddingTop: '48px', marginBottom: '56px' }}>
        <div style={{ fontSize: '40px', marginBottom: '16px' }}>?</div>
        <h1 style={{ fontSize: '34px', fontWeight: '800', color: '#e0e0e8', margin: '0 0 12px', letterSpacing: '-1px' }}>
          Frequently Asked Questions
        </h1>
        <p style={{ fontSize: '15px', color: '#9991d0', lineHeight: '1.8', maxWidth: '560px', margin: '0 auto' }}>
          Everything you need to understand the Connectome Explorer, what each page does, and how the system discovers hidden connections across research.
        </p>
      </div>

      {/* ---- The Big Picture ---- */}
      <Section title="The Big Picture">
        <QA question="What is the Connectome Explorer?" defaultOpen>
          <Prose>
            The Connectome Explorer is an interactive research intelligence tool that lets you explore a knowledge graph built from open-access scientific papers. Unlike a search engine that just finds papers, this system extracts the scientific content from every paper — entities, claims, mechanisms, methods — and connects them into a living network.
          </Prose>
          <Prose>
            The "connectome" is borrowed from neuroscience, where it describes the map of all neural connections in a brain. Here, it describes the map of all conceptual connections across the scientific literature. The result is a structural picture of how knowledge relates across disciplines, methods, and findings — including connections no individual researcher could see.
          </Prose>
        </QA>

        <QA question="Where does the data come from?">
          <Prose>
            All papers come from open-access sources: <strong style={{ color: '#c4bef8' }}>PubMed Central</strong> (the NIH's open-access repository), <strong style={{ color: '#c4bef8' }}>bioRxiv</strong> (biology preprints), and <strong style={{ color: '#c4bef8' }}>medRxiv</strong> (medical preprints). Every paper is legally available under Creative Commons licenses for text mining and computational analysis.
          </Prose>
          <Prose>
            The system currently focuses on neuroscience, cerebrovascular disease, and neuroinflammation as its seed domain, expanding into neuroimmunology, gut-brain axis research, geroscience, and cross-domain mechanisms.
          </Prose>
        </QA>

        <QA question="How is this different from PubMed, Google Scholar, or Semantic Scholar?">
          <Prose>
            Those tools connect papers through <strong style={{ color: '#c4bef8' }}>citations</strong> — who cited whom. If two papers have never cited each other, those tools can't connect them. The Connectome Explorer connects papers through their <strong style={{ color: '#c4bef8' }}>scientific content</strong>. When two papers in different fields both study IL-6, they connect through the same entity node — whether or not either author has ever read the other's work.
          </Prose>
          <Prose>
            This system also doesn't just answer questions you ask. It discovers patterns nobody asked about: convergences across disciplines, contradictions nobody has reconciled, field gaps where research should exist but doesn't, and bridge connections between concepts never studied together.
          </Prose>
        </QA>

        <QA question="Is the analysis AI-generated?">
          <Prose>
            Yes. Every extraction, connection, intelligence brief, and bridge hypothesis is generated by AI and clearly labeled as such. The AI models (primarily Claude by Anthropic) extract entities, identify mechanisms, validate connections, and generate analyses. <strong style={{ color: '#c4bef8' }}>No AI output is presented as human review.</strong> Researchers should evaluate every connection and insight using their own expertise.
          </Prose>
        </QA>
      </Section>

      {/* ---- Pages & Navigation ---- */}
      <Section title="Pages & Navigation">
        <Prose>
          Each page in the Explorer gives you a different lens into the knowledge graph. Here's what they do and when to use them.
        </Prose>

        <div style={{ display: 'grid', gap: '12px', marginTop: '16px' }}>
          <NavFeature icon="📄" title="Papers" to="/papers">
            <strong style={{ color: '#e0e0e8' }}>The library.</strong> Browse and search every paper in the system by title, author, or keyword. Each paper card shows its title, source, journal, and publication date. Click any paper to see its full detail page with extracted entities, claims, mechanisms, connections, and its intelligence brief.
            <br /><br />
            <strong style={{ color: '#e0e0e8' }}>When to use it:</strong> You have a specific topic or paper in mind and want to see what the system extracted from it, or you want to browse the full collection.
          </NavFeature>

          <NavFeature icon="⬡" title="Graph Explorer" to="/explore">
            <strong style={{ color: '#e0e0e8' }}>The visual map.</strong> An interactive force-directed graph where every dot is a paper and every line is a discovered connection. Papers are colored by discipline — purple for PubMed, green for bioRxiv, amber for medRxiv. You can zoom, pan, drag nodes, and click any paper node to see its details.
            <br /><br />
            Clusters of tightly-connected nodes reveal research neighborhoods. Lone bridges between clusters show cross-disciplinary connections. The graph updates as new papers and connections enter the system.
            <br /><br />
            <strong style={{ color: '#e0e0e8' }}>When to use it:</strong> You want a bird's-eye view of the research landscape, want to spot clusters and bridges visually, or want to explore the network structure intuitively.
          </NavFeature>

          <NavFeature icon="🔗" title="Connections" to="/connections">
            <strong style={{ color: '#e0e0e8' }}>The relationship catalog.</strong> Every discovered connection between papers, listed and filterable. Each connection shows the two papers involved, the relationship type (extends, contradicts, shares target, mechanism, convergent evidence, or methodological parallel), a confidence score, a novelty score, and a plain-language description of why the connection exists.
            <br /><br />
            Connections are color-coded by their epistemic status: blue for factual/extends, purple for mechanistic, amber for shared targets, green for convergent evidence, and red for contradictions.
            <br /><br />
            <strong style={{ color: '#e0e0e8' }}>When to use it:</strong> You want to find specific relationship types (e.g., all contradictions), see the most novel or highest-confidence connections, or understand exactly how two papers are related.
          </NavFeature>

          <NavFeature icon="🎯" title="Convergences" to="/convergences">
            <strong style={{ color: '#e0e0e8' }}>Where evidence piles up.</strong> Convergence zones are places in the graph where multiple papers from independent labs in different disciplines arrive at compatible conclusions. This is a stronger signal than any single paper — it means the finding has been reproduced or supported from multiple angles.
            <br /><br />
            Each convergence zone shows the participating papers, the shared finding or mechanism, and a strength score based on how many independent lines of evidence support it.
            <br /><br />
            <strong style={{ color: '#e0e0e8' }}>When to use it:</strong> You want to find the most robust, multiply-supported findings in the literature, or you want to see where independent research programs are unknowingly converging.
          </NavFeature>

          <NavFeature icon="🧠" title="Intelligence Briefs" to="/briefs">
            <strong style={{ color: '#e0e0e8' }}>AI analysis of individual papers.</strong> For papers that meet quality thresholds, the system generates a detailed intelligence brief: a structured critique covering methodological strengths and weaknesses, what the paper contributes to the broader network, connections the authors likely missed, and suggested follow-up analyses.
            <br /><br />
            Briefs are rated by overall quality (<span style={{ color: '#4ade80', fontWeight: '600' }}>high</span>, <span style={{ color: '#fbbf24', fontWeight: '600' }}>medium</span>, or <span style={{ color: '#f87171', fontWeight: '600' }}>low</span>) and can be filtered and sorted.
            <br /><br />
            <strong style={{ color: '#e0e0e8' }}>When to use it:</strong> You want a deep dive into what the graph reveals about a specific paper that wasn't visible when the paper was published.
          </NavFeature>

          <NavFeature icon="🌉" title="Bridge Query" to="/bridge">
            <strong style={{ color: '#e0e0e8' }}>Ask "is there a connection?"</strong> Enter two research concepts and the system searches the knowledge graph for paths between them. If a path exists, you get a hypothesis with a confidence score, a description of the connection chain, the intermediate papers and entities, and an honest assessment of whether the connection is direct, indirect, or speculative.
            <br /><br />
            Bridge queries are cached so repeated queries are instant. The bridge doesn't invent connections — it reports what the graph contains and classifies the strength of evidence.
            <br /><br />
            <strong style={{ color: '#e0e0e8' }}>When to use it:</strong> You have two concepts and want to know if there's a hidden connection between them. Especially powerful for cross-disciplinary hunches.
          </NavFeature>

          <NavFeature icon="🔬" title="Analyze" to="/analyze">
            <strong style={{ color: '#e0e0e8' }}>Run an analysis on any paper.</strong> Paste a DOI (e.g., 10.1016/j.cell.2024.01.001) and the system will fetch the paper (if available in open-access repositories), run it through the full extraction pipeline, and generate a fresh intelligence brief. This lets you analyze papers that aren't yet in the system or re-analyze papers with updated models.
            <br /><br />
            <strong style={{ color: '#e0e0e8' }}>When to use it:</strong> You have a specific paper's DOI and want to add it to the connectome, or you want to see what connections emerge from a paper not yet in the system.
          </NavFeature>

          <NavFeature icon="📖" title="About" to="/about">
            <strong style={{ color: '#e0e0e8' }}>The full story.</strong> A detailed explanation of the project's philosophy, architecture, how it differs from existing tools, the six-stage pipeline (ingest, extract, graph, connect, critique, explore), what this is not, and its relationship to The Encoded Human Project.
            <br /><br />
            <strong style={{ color: '#e0e0e8' }}>When to use it:</strong> You want the deepest explanation of why this system exists and how it's built.
          </NavFeature>
        </div>
      </Section>

      {/* ---- Key Concepts ---- */}
      <Section title="Key Concepts & Terminology">
        <div style={{ ...s.card, padding: '24px' }}>
          <Term label="Entity">
            A named scientific thing extracted from a paper: a gene, protein, drug, disease, cell type, organism, anatomical structure, or pathway. Entities are the primary nodes connecting papers across disciplines. When two papers both mention "TNF-alpha," they share an entity node in the graph.
          </Term>
          <Term label="Claim">
            A specific scientific assertion extracted from a paper, with an evidence strength rating (strong, moderate, weak). Claims are the things papers actually say, separated from the interpretation.
          </Term>
          <Term label="Mechanism">
            A biological process or causal pathway described in a paper. Mechanisms include upstream triggers and downstream effects. When two papers describe the same mechanism from different angles, that's a mechanistic connection.
          </Term>
          <Term label="Connection">
            A discovered relationship between two papers. Connections can be <strong style={{ color: '#3b82f6' }}>extends</strong> (builds on), <strong style={{ color: '#f43f5e' }}>contradicts</strong>, <strong style={{ color: '#8b5cf6' }}>mechanism_for</strong>, <strong style={{ color: '#f59e0b' }}>shares_target</strong>, <strong style={{ color: '#10b981' }}>convergent_evidence</strong>, or <strong style={{ color: '#94a3b8' }}>methodological_parallel</strong>.
          </Term>
          <Term label="Confidence Score">
            A 0-to-1 rating of how reliable a discovered connection is. Higher means more evidence supports the link. Connections below 0.3 are flagged as speculative.
          </Term>
          <Term label="Novelty Score">
            A 0-to-1 rating of how surprising or non-obvious a connection is. A novelty score of 0.9 means the connection is between papers that are unlikely to be found through normal citation or keyword search. High novelty is where the most interesting discoveries live.
          </Term>
          <Term label="Convergence Zone">
            A cluster where 3+ papers from independent sources support the same finding or mechanism. Convergence zones represent the strongest signals in the graph because they're supported by multiple independent lines of evidence.
          </Term>
          <Term label="Bridge">
            A path through the graph connecting two concepts that don't have a direct relationship. Bridge results include the intermediate papers and entities that form the chain, plus a confidence assessment.
          </Term>
          <Term label="Intelligence Brief">
            An AI-generated analysis of a paper's position in the knowledge graph: what the graph reveals about the paper that wasn't visible at publication, including missed connections, methodological context, and research trajectory.
          </Term>
          <Term label="Epistemic Color">
            The color system used across the site to indicate the nature of evidence. <span style={{ color: '#3b82f6' }}>Blue</span> = factual/strong. <span style={{ color: '#8b5cf6' }}>Purple</span> = interpretive. <span style={{ color: '#f59e0b' }}>Amber</span> = hypothesis. <span style={{ color: '#10b981' }}>Green</span> = convergent. <span style={{ color: '#f43f5e' }}>Red</span> = contradiction. <span style={{ color: '#94a3b8' }}>Slate</span> = speculative.
          </Term>
          <Term label="Entity Co-occurrence">
            A connection type based on shared entities between papers. When two papers share 3 or more named entities (genes, proteins, diseases, etc.), an entity co-occurrence connection is created — even if neither paper cites the other. This significantly increases the density of the graph.
          </Term>
          <div style={{ display: 'flex', gap: '12px' }}>
            <div style={{ fontSize: '12px', fontWeight: '700', color: '#4ade80', flexShrink: 0, width: '160px', textTransform: 'uppercase', letterSpacing: '0.3px' }}>Discipline Colors</div>
            <div style={{ fontSize: '13px', color: '#9991d0', lineHeight: '1.7' }}>
              In the Graph Explorer and background visualization, papers are colored by source: <span style={{ color: '#7c6af7', fontWeight: '600' }}>purple</span> for PubMed, <span style={{ color: '#10b981', fontWeight: '600' }}>green</span> for bioRxiv, <span style={{ color: '#f59e0b', fontWeight: '600' }}>amber</span> for medRxiv, and <span style={{ color: '#60a5fa', fontWeight: '600' }}>blue</span> for arXiv.
            </div>
          </div>
        </div>
      </Section>

      {/* ---- How It Works ---- */}
      <Section title="How the System Works">
        <QA question="How are papers processed?">
          <Prose>
            Every paper goes through a six-stage pipeline:
          </Prose>
          <div style={{ paddingLeft: '8px' }}>
            <Prose>
              <strong style={{ color: '#7c6af7' }}>1. Ingest</strong> — Full-text papers are downloaded from open-access repositories as structured XML, preserving sections, references, and metadata.
            </Prose>
            <Prose>
              <strong style={{ color: '#7c6af7' }}>2. Extract</strong> — AI models identify entities (genes, proteins, drugs, diseases), extract claims with evidence strength ratings, identify biological mechanisms, classify the study design, and generate a vector embedding for semantic similarity.
            </Prose>
            <Prose>
              <strong style={{ color: '#7c6af7' }}>3. Graph</strong> — Extracted content becomes nodes and edges in a knowledge graph. Papers, entities, claims, and mechanisms are all first-class nodes. Entities are deduplicated so papers from different fields connect through shared scientific content.
            </Prose>
            <Prose>
              <strong style={{ color: '#7c6af7' }}>4. Connect</strong> — Three engines discover connections: graph traversal (shared entities, mechanisms, methods), embedding similarity (semantically similar content), and AI validation (verifies candidates, assigns confidence and novelty scores).
            </Prose>
            <Prose>
              <strong style={{ color: '#7c6af7' }}>5. Critique</strong> — High-impact papers receive an Intelligence Brief: deep analysis of methodological strengths, missed connections, and research trajectory.
            </Prose>
            <Prose>
              <strong style={{ color: '#7c6af7' }}>6. Explore</strong> — Everything becomes available here in the Connectome Explorer.
            </Prose>
          </div>
        </QA>

        <QA question="How are connections discovered?">
          <Prose>
            Connections come from three sources, each catching different kinds of relationships:
          </Prose>
          <Prose>
            <strong style={{ color: '#c4bef8' }}>Graph traversal:</strong> If two papers share 3+ entities (genes, proteins, diseases), they get an entity co-occurrence connection. If they describe the same biological mechanism or use similar methods, those create connections too. This finds links that are invisible to citation-based systems.
          </Prose>
          <Prose>
            <strong style={{ color: '#c4bef8' }}>Embedding similarity:</strong> Each paper has a vector embedding capturing its semantic meaning. Papers with highly similar embeddings but no shared graph nodes are candidates for connections that pure entity matching would miss.
          </Prose>
          <Prose>
            <strong style={{ color: '#c4bef8' }}>AI validation:</strong> Candidate connections are verified by a language model that classifies the relationship type (extends, contradicts, mechanistic, etc.), writes a plain-language description, and assigns confidence and novelty scores.
          </Prose>
        </QA>

        <QA question="What do the confidence and novelty scores mean?">
          <Prose>
            <strong style={{ color: '#c4bef8' }}>Confidence (0.0 - 1.0):</strong> How much evidence supports this connection. A confidence of 0.9 means strong, multi-faceted evidence. Below 0.3 is speculative. Confidence reflects the <em>reliability</em> of the connection.
          </Prose>
          <Prose>
            <strong style={{ color: '#c4bef8' }}>Novelty (0.0 - 1.0):</strong> How surprising the connection is. A novelty of 0.9 means these papers would almost never be found together through normal search or citation. High novelty connections are the system's most unique contribution — they're the ones researchers couldn't have found on their own.
          </Prose>
          <Prose>
            The most interesting connections are often <strong style={{ color: '#e0e0e8' }}>high confidence + high novelty</strong> — reliable but surprising.
          </Prose>
        </QA>

        <QA question="What does the epistemic color system mean?">
          <Prose>
            Colors communicate the <em>nature</em> of evidence at a glance across the entire site:
          </Prose>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: '8px', marginTop: '8px' }}>
            {[
              { color: '#3b82f6', label: 'Blue — Factual / Strong', desc: 'Well-supported by direct evidence. High confidence claims and "extends" connections.' },
              { color: '#8b5cf6', label: 'Purple — Interpretive', desc: 'Mechanistic connections and moderate-strength claims. Supported but involves interpretation.' },
              { color: '#f59e0b', label: 'Amber — Hypothesis', desc: 'Shared-target connections and weak/indirect evidence. Interesting but needs more support.' },
              { color: '#10b981', label: 'Green — Convergent', desc: 'Multiple independent sources agree. The strongest signal — replicated or convergent evidence.' },
              { color: '#f43f5e', label: 'Red — Contradiction', desc: 'Papers that reach opposing conclusions. Just as valuable as agreement — flags unresolved conflicts.' },
              { color: '#94a3b8', label: 'Slate — Speculative', desc: 'Low evidence or methodological parallels. Worth noting but treat with caution.' },
            ].map(({ color, label, desc }) => (
              <div key={label} style={{ display: 'flex', gap: '10px', padding: '10px 12px', background: '#0d0d18', borderRadius: '6px', border: '1px solid #1e1e2e' }}>
                <div style={{ width: '4px', borderRadius: '2px', background: color, flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: '12px', fontWeight: '700', color, marginBottom: '4px' }}>{label}</div>
                  <div style={{ fontSize: '11px', color: '#6b7280', lineHeight: '1.6' }}>{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </QA>
      </Section>

      {/* ---- Using the Explorer ---- */}
      <Section title="Using the Explorer">
        <QA question="How do I find a specific paper?">
          <Prose>
            Go to <Link to="/papers" style={{ color: '#7c6af7' }}>Papers</Link> and use the search bar. You can search by title, author, or keyword. You can also filter by source (PubMed, bioRxiv, medRxiv). Click any paper to see its full detail page with all extracted data.
          </Prose>
        </QA>

        <QA question="How do I read a paper detail page?">
          <Prose>
            The paper detail page has two columns on desktop. The <strong style={{ color: '#c4bef8' }}>left column</strong> shows the paper's metadata, abstract, extracted entities, claims (color-coded by evidence strength), mechanisms (with upstream/downstream annotations), and its intelligence brief if one exists.
          </Prose>
          <Prose>
            The <strong style={{ color: '#c4bef8' }}>right column</strong> shows a mini force-graph of the paper's local neighborhood (its connections to other papers) and a list of its connections sorted by novelty score. High-novelty connections appear first because those are the most interesting.
          </Prose>
        </QA>

        <QA question="What does the graph visualization on the homepage show?">
          <Prose>
            The background graph on the homepage renders the top 100 most-connected papers in the system as a force-directed network. It gives you an ambient, at-a-glance sense of the graph's structure. Clusters represent research neighborhoods; bridges between clusters represent cross-disciplinary connections. The visualization is non-interactive on the homepage — for full interactivity, go to the <Link to="/explore" style={{ color: '#7c6af7' }}>Graph Explorer</Link>.
          </Prose>
        </QA>

        <QA question="How do I use Bridge Query?">
          <Prose>
            Go to <Link to="/bridge" style={{ color: '#7c6af7' }}>Bridge</Link>, enter two research concepts (e.g., "neuroinflammation" and "gut microbiome"), and submit. The system searches the knowledge graph for paths connecting them. Results show:
          </Prose>
          <Prose>
            - The connection chain (which papers and entities form the path)<br />
            - A confidence score for the bridge<br />
            - A plain-language hypothesis explaining the connection<br />
            - An honest classification: direct, indirect, or speculative
          </Prose>
          <Prose>
            Bridge results are cached, so running the same query twice is instant. Try concepts from different fields for the most interesting results.
          </Prose>
        </QA>

        <QA question="What are the stats on the homepage?">
          <Prose>
            The four stat cards show the current state of the knowledge graph in real time:
          </Prose>
          <Prose>
            <strong style={{ color: '#7c6af7' }}>Total Papers</strong> — how many papers have been ingested and processed.<br />
            <strong style={{ color: '#fbbf24' }}>Connections</strong> — total discovered relationships between papers (citation-independent).<br />
            <strong style={{ color: '#4ade80' }}>Claims Extracted</strong> — individual scientific assertions pulled from papers.<br />
            <strong style={{ color: '#60a5fa' }}>Intelligence Briefs</strong> — papers that have received AI-generated deep analyses.
          </Prose>
        </QA>

        <QA question="Do I need an account?">
          <Prose>
            Most features work without signing in. An account unlocks the <strong style={{ color: '#c4bef8' }}>Workspace</strong> (saved searches, bookmarked papers, custom collections) and the <strong style={{ color: '#c4bef8' }}>Analyze</strong> feature for submitting new papers to the pipeline.
          </Prose>
        </QA>
      </Section>

      {/* ---- Trust & Limitations ---- */}
      <Section title="Trust & Limitations">
        <QA question="How accurate are the AI extractions?">
          <Prose>
            AI extraction is imperfect. Entity recognition misses some entities and occasionally misidentifies others. Claim extraction captures the major assertions but may miss nuance. Mechanism identification is the most challenging — biological mechanisms are complex and context-dependent.
          </Prose>
          <Prose>
            The system compensates by using confidence scores, multiple validation layers, and honest labeling. When the system isn't sure about an extraction, it says so. Researchers should always verify specific claims against the original papers.
          </Prose>
        </QA>

        <QA question="Should I trust the Intelligence Briefs?">
          <Prose>
            Intelligence Briefs are analytical tools, not editorial judgments. They surface patterns, missed connections, and methodological observations that the graph reveals. They are <strong style={{ color: '#c4bef8' }}>not peer review</strong> and should not be treated as such.
          </Prose>
          <Prose>
            Use them as a starting point for deeper investigation, not as a final word. The value is in the connections and patterns they surface — the scientific evaluation of those patterns is yours to make.
          </Prose>
        </QA>

        <QA question="What are the system's biggest limitations?">
          <Prose>
            <strong style={{ color: '#c4bef8' }}>Open-access only:</strong> The system can only process papers available through open-access repositories. Paywalled papers in traditional journals are not included, which creates gaps in coverage.<br /><br />
            <strong style={{ color: '#c4bef8' }}>Seed domain focus:</strong> The current graph is concentrated on neuroscience and related fields. Cross-domain connections are growing but coverage is uneven.<br /><br />
            <strong style={{ color: '#c4bef8' }}>AI limitations:</strong> Entity normalization sometimes fails (treating the same entity under different names as separate entities). Mechanism extraction can miss subtle or implicit causal relationships.<br /><br />
            <strong style={{ color: '#c4bef8' }}>Recency:</strong> There is a processing lag between a paper's publication and its appearance in the graph. Very recent papers may not yet be connected.
          </Prose>
        </QA>
      </Section>

      {/* Footer */}
      <div style={{ textAlign: 'center', paddingBottom: '48px', color: '#6b7280', fontSize: '13px', lineHeight: '2' }}>
        <div style={{ marginBottom: '8px' }}>
          Have more questions? Read the full <Link to="/about" style={{ color: '#7c6af7', textDecoration: 'none' }}>About page</Link> for the complete story.
        </div>
        <div>
          <a href="https://thedecodedhuman.com" style={{ color: '#7c6af7', textDecoration: 'none' }}>thedecodedhuman.com</a>
        </div>
      </div>
    </div>
  )
}
