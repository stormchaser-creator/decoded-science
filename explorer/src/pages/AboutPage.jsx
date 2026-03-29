import React from 'react'
import { s, useIsMobile } from '../shared.js'
import SEO from '../components/SEO.jsx'

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

function H3({ children }) {
  return (
    <h3 style={{ fontSize: '15px', fontWeight: '700', color: '#e0e0e8', margin: '20px 0 8px' }}>
      {children}
    </h3>
  )
}

function StepCard({ number, title, children }) {
  return (
    <div style={{ ...s.card, padding: '20px', marginBottom: '12px' }}>
      <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
        <div style={{ fontSize: '22px', fontWeight: '800', color: '#7c6af7', flexShrink: 0, lineHeight: 1 }}>{number}</div>
        <div>
          <div style={{ fontSize: '14px', fontWeight: '700', color: '#c4bef8', marginBottom: '6px' }}>{title}</div>
          <div style={{ fontSize: '13px', color: '#6b7280', lineHeight: '1.7' }}>{children}</div>
        </div>
      </div>
    </div>
  )
}

export default function AboutPage() {
  const isMobile = useIsMobile()
  const grid2 = { display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: '12px' }
  return (
    <div style={{ ...s.page, maxWidth: '780px', margin: '0 auto', padding: isMobile ? '16px' : '24px' }}>
      <SEO
        title="About the Literature Connectome"
        description="How The Decoded Human uses AI to build a knowledge graph connecting research papers through shared entities, mechanisms, and claims — not just citations. Discover what no individual paper can see."
        path="/about"
      />
      {/* Hero */}
      <div style={{ textAlign: 'center', paddingTop: '48px', marginBottom: '56px' }}>
        <div style={{ fontSize: '40px', marginBottom: '16px' }}>⬡</div>
        <h1 style={{ fontSize: '34px', fontWeight: '800', color: '#e0e0e8', margin: '0 0 12px', letterSpacing: '-1px' }}>
          The Decoded Human
        </h1>
        <p style={{ fontSize: '18px', fontWeight: '600', color: '#7c6af7', margin: '0 0 20px' }}>
          The Literature Connectome
        </p>
        <p style={{ fontSize: '15px', color: '#9991d0', lineHeight: '1.8', maxWidth: '560px', margin: '0 auto' }}>
          Scientific knowledge doesn't live in papers. It lives in the connections between them.
        </p>
      </div>

      {/* Opening */}
      <div style={{ ...s.card, padding: '28px', marginBottom: '48px', borderColor: '#2d2060' }}>
        <Prose>
          There are tens of millions of papers in PubMed. Each one averages about 30 citation links to other work. That's it — 30 connections in a universe of millions. A neuroscientist studying neuroinflammation may never encounter the immunology paper that shares her mechanism, the materials science work that explains her surface adhesion data, or the gastroenterology finding that converges on her conclusion from a completely different direction.
        </Prose>
        <Prose>
          These connections exist in the literature. They just haven't been built.
        </Prose>
      </div>

      <Section title="What This Is">
        <Prose>
          The Decoded Human is an AI-powered knowledge graph that discovers hidden connections across scientific literature. We ingest open-access research papers, extract their core scientific content — entities, claims, mechanisms, methods — and build a living network where every paper is connected not just by what it cites, but by what it <em style={{ color: '#c4bef8' }}>shares</em> with work its authors never knew existed.
        </Prose>
        <Prose>
          The result is a connectome: a structural map of how scientific knowledge actually relates across disciplines, methods, and findings. It grows continuously as new papers enter the system, new connections are discovered, and new analyses are generated.
        </Prose>
      </Section>

      <Section title="How This Is Different">
        <Prose>
          Good tools already exist for finding and exploring scientific papers. PubMed searches the literature. Google Scholar indexes it. Semantic Scholar ranks it. Connected Papers visualizes citation relationships. ResearchRabbit recommends related reading. Elicit and Consensus extract claims and assess evidence in response to specific questions.
        </Prose>
        <Prose>
          The Decoded Human does something none of them do. It builds a different kind of graph and asks a different kind of question.
        </Prose>

        <H3>A different graph</H3>
        <Prose>
          Citation-based tools connect papers through their reference lists — who cited whom. If two papers have never been cited alongside each other by a third paper, those tools cannot connect them. The Decoded Human connects papers through their <em style={{ color: '#c4bef8' }}>scientific content</em>. When two papers in different fields both study IL-6, they connect through the same entity node — whether or not either author has ever read the other's work. Entities, claims, mechanisms, and methods are first-class nodes in the graph alongside papers. This finds connections that are invisible to every citation-based system.
        </Prose>

        <H3>A different question</H3>
        <Prose>
          Recommendation tools answer: "What should I read next?" Question-answering tools answer: "Does the literature support this claim?" The Decoded Human answers a question nobody else is asking: <strong style={{ color: '#c4bef8' }}>What does the literature know that no individual paper can see?</strong>
        </Prose>
        <Prose>
          Convergence patterns across disciplines. Contradictions nobody has reconciled. Field gaps where research should exist but doesn't. Bridge connections between concepts that have never been studied together. These are properties of the network, not of any individual paper — and they only become visible when you build the network at scale and look at its structure.
        </Prose>

        <H3>A persistent intelligence layer</H3>
        <Prose>
          Most AI research tools are stateless — every query starts from scratch against an index. The Decoded Human builds and maintains a persistent knowledge graph that accumulates intelligence over time. Every paper that enters the system makes every other paper's analysis richer. The system doesn't just answer questions. It discovers things nobody asked about.
        </Prose>
      </Section>

      <Section title="What It Does for You">
        <div style={{ ...grid2 }}>
          {[
            { icon: '🔗', title: 'Find connections you couldn\'t find alone', desc: 'Search for a topic and see not just papers, but the network of relationships surrounding it. The system surfaces papers from other disciplines that share your mechanisms, entities, or findings — connections that don\'t appear in citation records.' },
            { icon: '🎯', title: 'See where evidence converges', desc: 'When multiple papers from independent labs in different disciplines arrive at compatible conclusions, that\'s a convergence signal — stronger evidence than any single paper. The connectome identifies these patterns automatically.' },
            { icon: '⚡', title: 'See where evidence conflicts', desc: 'Contradictions in the literature are just as valuable as agreements. The system flags papers that reach opposing conclusions on the same claim, whether or not they cite each other.' },
            { icon: '🧠', title: 'Get AI analysis of any paper\'s position', desc: 'Intelligence Briefs analyze what the graph reveals about a paper that wasn\'t visible at publication: missed connections, methodological context, what convergence clusters the paper belongs to, and what the findings imply for the broader research trajectory.' },
            { icon: '🌉', title: 'Ask questions the literature can\'t answer alone', desc: 'The Bridge Query lets you enter two concepts and ask: is there a connection? The system searches the graph for paths between them and generates a hypothesis with a confidence score and an honest assessment of the connection type.' },
            { icon: '🗺️', title: 'Discover what\'s missing', desc: 'Field Gaps are the questions nobody is answering. By analyzing the structure of the graph — where connections are dense and where they\'re absent — the system identifies research opportunities and intersections between disciplines that remain unexplored.' },
          ].map(({ icon, title, desc }) => (
            <div key={title} style={{ ...s.card, padding: '20px' }}>
              <div style={{ fontSize: '22px', marginBottom: '8px' }}>{icon}</div>
              <div style={{ fontSize: '13px', fontWeight: '700', color: '#c4bef8', marginBottom: '8px' }}>{title}</div>
              <div style={{ fontSize: '12px', color: '#6b7280', lineHeight: '1.7' }}>{desc}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="How It Works">
        <StepCard number="01" title="Ingest">
          We download full-text, open-access papers from PubMed Central, bioRxiv, and medRxiv — all legally available under Creative Commons licenses for text mining and reuse. Papers arrive as structured XML, preserving their sections, references, and metadata.
        </StepCard>
        <StepCard number="02" title="Extract">
          Each paper passes through an AI extraction pipeline. A biomedical NER model identifies entities — genes, proteins, drugs, diseases, cell types, organisms, anatomical structures. A language model extracts key scientific claims, biological mechanisms, statistical and experimental methods, and classifies the study design and discipline. Every paper receives a vector embedding for semantic similarity search.
        </StepCard>
        <StepCard number="03" title="Graph">
          The extracted content becomes nodes and edges in a knowledge graph. Papers, entities, claims, mechanisms, methods, and researchers are all first-class nodes. Entities and mechanisms are deduplicated across papers, so when two papers in different fields both study the same target, they connect through the same node.
        </StepCard>
        <StepCard number="04" title="Connect">
          Three discovery engines find connections that don't exist in the citation record: <strong style={{ color: '#c4bef8' }}>Graph traversal</strong> finds papers that share entities, mechanisms, or methods. <strong style={{ color: '#c4bef8' }}>Embedding similarity</strong> finds papers with semantically similar content that share no explicit graph nodes. <strong style={{ color: '#c4bef8' }}>AI validation</strong> verifies candidates and assigns confidence scores, novelty scores, and plain-language relationship descriptions.
        </StepCard>
        <StepCard number="05" title="Critique">
          For the highest-impact papers, the system generates an Intelligence Brief: a deep analysis of methodological strengths and weaknesses, missed connections the authors couldn't have seen, suggested additional analyses, and a forward-looking research trajectory.
        </StepCard>
        <StepCard number="06" title="Explore">
          Everything is available through the Connectome Explorer and through a public API for programmatic access. The live stats on the homepage reflect the current state of the graph as it grows.
        </StepCard>
      </Section>

      <Section title="What This Is Not">
        <div style={{ ...grid2 }}>
          {[
            { label: 'Not a search engine', desc: 'PubMed and Google Scholar search the literature. We build the network between papers that search can\'t see.' },
            { label: 'Not a recommendation engine', desc: 'ResearchRabbit recommends papers you might like. We discover structural relationships in the knowledge itself.' },
            { label: 'Not a question-answering tool', desc: 'Elicit and Consensus answer questions you ask. We discover patterns nobody asked about — convergences, contradictions, and field gaps.' },
            { label: 'Not a peer review replacement', desc: 'AI critiques are analytical tools, not editorial judgments. They identify patterns and surface connections. Human scientific judgment is irreplaceable.' },
            { label: 'Not making claims about the science', desc: 'When we report that two papers share a mechanism, we\'re reporting what the AI extracted and validated. Researchers should evaluate every connection with their own expertise.' },
            { label: 'All analysis is AI-generated', desc: 'Every Intelligence Brief, connection description, and bridge hypothesis is clearly identified as AI output. We don\'t present machine output as human review.' },
          ].map(({ label, desc }) => (
            <div key={label} style={{ ...s.card, padding: '16px', borderLeft: '3px solid #2d2060' }}>
              <div style={{ fontSize: '12px', fontWeight: '700', color: '#7c6af7', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{label}</div>
              <div style={{ fontSize: '12px', color: '#6b7280', lineHeight: '1.7' }}>{desc}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="The Seed Domain">
        <Prose>
          The connectome currently focuses on neuroscience, cerebrovascular disease, and neuroinflammation as its seed domain, expanding outward into neuroimmunology, the gut-brain axis, geroscience, and cross-domain mechanisms. This domain was chosen because it's where cross-disciplinary connections are most actively emerging and least systematically mapped.
        </Prose>
        <Prose>
          The architecture is domain-agnostic. The same pipeline that maps neuroinflammation can map oncology, cardiology, infectious disease, or any field with open-access literature. The seed domain is the proof of concept. The network grows from here.
        </Prose>
      </Section>

      <Section title="Open Science">
        <div style={{ ...s.card, padding: '24px' }}>
          {[
            { label: 'Data sources', value: 'PubMed Central Open Access Subset, bioRxiv, medRxiv — all under Creative Commons licenses' },
            { label: 'AI disclosure', value: 'Every extraction, connection, and critique is generated by AI and labeled as such' },
            { label: 'Confidence scoring', value: 'Every connection carries a confidence score and a novelty score. Every claim carries an evidence strength rating' },
            { label: 'Epistemic honesty', value: 'When the system doesn\'t find a connection, it says so. When a connection is speculative, it\'s labeled speculative. We would rather tell you we don\'t know than pretend we do' },
          ].map(({ label, value }) => (
            <div key={label} style={{ display: 'flex', gap: '16px', paddingBottom: '14px', marginBottom: '14px', borderBottom: '1px solid #1e1e2e', ':last-child': { borderBottom: 'none' } }}>
              <div style={{ fontSize: '12px', fontWeight: '700', color: '#4ade80', flexShrink: 0, width: '140px' }}>{label}</div>
              <div style={{ fontSize: '13px', color: '#9991d0', lineHeight: '1.6' }}>{value}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="The Larger Project">
        <div style={{ ...s.card, padding: '28px', borderColor: '#2d2060' }}>
          <Prose>
            The Decoded Human is the research intelligence arm of <strong style={{ color: '#c4bef8' }}>The Encoded Human Project</strong> — a platform integrating clinical neuroscience, depth psychology, and contemplative traditions to help people understand the layers through which their experience is encoded: biological, ancestral, developmental, relational, cultural, experiential, and chosen.
          </Prose>
          <Prose>
            The Encoded Human is the inward journey — understanding yourself. The Decoded Human is the outward journey — understanding the science. One project encodes. The other decodes. Same framework, opposite direction.
          </Prose>
          <Prose>
            Research arrives encoded in the limitations of its field, its methodology, its sample, and its authors' perspective. The connectome decodes it — revealing what becomes visible only when you can see the entire network at once.
          </Prose>
          <div style={{ marginTop: '20px', paddingTop: '20px', borderTop: '1px solid #1e1e2e' }}>
            <div style={{ fontSize: '13px', color: '#9991d0', lineHeight: '1.8' }}>
              The project is led by <strong style={{ color: '#e0e0e8' }}>Eric Whitney, DO</strong>, a board-certified neurosurgeon with clinical expertise in cerebrovascular disease. The AI systems are built on Claude (Anthropic) and multiple language models optimized for cost and reasoning quality.
            </div>
          </div>
        </div>
      </Section>

      {/* Footer links */}
      <div style={{ textAlign: 'center', paddingBottom: '48px', color: '#6b7280', fontSize: '13px', lineHeight: '2' }}>
        <div style={{ marginBottom: '4px' }}>
          <a href="https://thedecodedhuman.com" style={{ color: '#7c6af7', textDecoration: 'none' }}>thedecodedhuman.com</a>
        </div>
        <div>
          Part of <a href="https://theencodedhumanproject.com" style={{ color: '#7c6af7', textDecoration: 'none' }}>The Encoded Human Project</a>
        </div>
      </div>
    </div>
  )
}
