/**
 * Post-build script: generates per-route HTML files with correct meta tags
 * baked in, so social media crawlers see the right OG/Twitter tags without
 * executing JavaScript.
 *
 * Run after `vite build`: node scripts/generate-static-meta.mjs
 */

import { readFileSync, writeFileSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const DIST = join(__dirname, '..', 'dist')
const BASE_URL = 'https://thedecodedhuman.com'
const SITE_NAME = 'The Decoded Human'

const routes = [
  {
    path: '/',
    title: `${SITE_NAME} — AI-Powered Literature Connectome`,
    description: 'The Decoded Human builds an AI-powered knowledge graph that discovers hidden connections across scientific literature. Explore convergences, contradictions, and field gaps across neuroscience and beyond.',
  },
  {
    path: '/about',
    title: `About the Literature Connectome | ${SITE_NAME}`,
    description: 'How The Decoded Human uses AI to build a knowledge graph connecting research papers through shared entities, mechanisms, and claims — not just citations. Discover what no individual paper can see.',
  },
  {
    path: '/explore',
    title: `Explore the Connectome Graph | ${SITE_NAME}`,
    description: 'Navigate the Literature Connectome — an interactive knowledge graph of scientific papers connected by shared entities, mechanisms, methods, and findings across disciplines.',
  },
  {
    path: '/papers',
    title: `Research Papers & AI Analysis | ${SITE_NAME}`,
    description: 'Browse papers ingested into the Literature Connectome. Each paper includes AI-extracted entities, claims, methodology analysis, and connection mapping to related work across fields.',
  },
  {
    path: '/connections',
    title: `Cross-Paper Connections | ${SITE_NAME}`,
    description: 'Explore connections between research papers discovered through shared scientific content — entities, mechanisms, and findings that link work across disciplines and fields.',
  },
  {
    path: '/convergences',
    title: `Convergence Clusters | ${SITE_NAME}`,
    description: 'Discover clusters of papers from different fields that converge on the same mechanisms, entities, or findings. See where independent research lines are unknowingly confirming each other.',
  },
  {
    path: '/gaps',
    title: `Research Field Gaps | ${SITE_NAME}`,
    description: 'Identify gaps in the scientific literature — areas where connections should exist but don\'t, suggesting unexplored research opportunities across disciplines.',
  },
  {
    path: '/briefs',
    title: `Intelligence Briefs | ${SITE_NAME}`,
    description: 'AI-generated intelligence briefs providing deep analysis of high-impact papers: methodological critique, missed connections, convergence mapping, and research trajectory implications.',
  },
  {
    path: '/bridge',
    title: `Bridge Query — Find Hidden Connections | ${SITE_NAME}`,
    description: 'Enter two scientific concepts and discover if a connection exists in the literature. The Bridge Query searches the knowledge graph for paths between them and generates hypotheses with confidence scores.',
  },
  {
    path: '/analyze',
    title: `Analyze a Paper | ${SITE_NAME}`,
    description: 'Submit a research paper for AI-powered analysis. Extract entities, map connections to the existing knowledge graph, and discover what the literature knows that the paper alone can\'t see.',
  },
  {
    path: '/faq',
    title: `Frequently Asked Questions | ${SITE_NAME}`,
    description: 'How the Literature Connectome works, what makes it different from Google Scholar or Semantic Scholar, and how to use The Decoded Human for cross-disciplinary research discovery.',
  },
  {
    path: '/login',
    title: `Sign In | ${SITE_NAME}`,
    description: 'Sign in to The Decoded Human to access your workspace, saved analyses, and personalized research tools.',
    noindex: true,
  },
  {
    path: '/register',
    title: `Create Account | ${SITE_NAME}`,
    description: 'Create a free account on The Decoded Human to save research, track connections, and access the full Literature Connectome toolkit.',
    noindex: true,
  },
  {
    path: '/workspace',
    title: `Your Workspace | ${SITE_NAME}`,
    description: 'Your personal research workspace on The Decoded Human.',
    noindex: true,
  },
]

function injectMeta(html, { title, description, url, noindex }) {
  let out = html
  out = out.replace(/<title>.*?<\/title>/, `<title>${title}</title>`)
  out = out.replace(/(<meta name="description" content=").*?"/, `$1${description}"`)
  out = out.replace(/(<link rel="canonical" href=").*?"/, `$1${url}"`)
  out = out.replace(/(<meta property="og:url" content=").*?"/, `$1${url}"`)
  out = out.replace(/(<meta property="og:title" content=").*?"/, `$1${title}"`)
  out = out.replace(/(<meta property="og:description" content=").*?"/, `$1${description}"`)
  out = out.replace(/(<meta name="twitter:title" content=").*?"/, `$1${title}"`)
  out = out.replace(/(<meta name="twitter:description" content=").*?"/, `$1${description}"`)

  if (noindex) {
    out = out.replace('</head>', '    <meta name="robots" content="noindex, nofollow" />\n  </head>')
  }

  return out
}

const template = readFileSync(join(DIST, 'index.html'), 'utf-8')
let count = 0

for (const route of routes) {
  const url = `${BASE_URL}${route.path === '/' ? '/' : route.path}`
  const html = injectMeta(template, {
    title: route.title,
    description: route.description,
    url,
    noindex: route.noindex,
  })

  if (route.path === '/') {
    writeFileSync(join(DIST, 'index.html'), html)
  } else {
    const dir = join(DIST, route.path.slice(1))
    mkdirSync(dir, { recursive: true })
    writeFileSync(join(dir, 'index.html'), html)
  }
  count++
}

console.log(`Generated ${count} static meta pages in dist/`)
