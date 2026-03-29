/**
 * Cloudflare Pages Function: intercepts /papers/:id requests from social media
 * crawlers and returns HTML with correct per-paper OG/Twitter meta tags.
 * Human visitors pass through to the SPA.
 */

const BOT_PATTERN = /facebookexternalhit|Twitterbot|LinkedInBot|Slackbot|WhatsApp|Discordbot|TelegramBot|Googlebot|bingbot|yandex|Applebot/i

const BASE_URL = 'https://thedecodedhuman.com'
const SITE_NAME = 'The Decoded Human'

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export async function onRequest(context) {
  const ua = context.request.headers.get('user-agent') || ''

  // Pass through for human visitors
  if (!BOT_PATTERN.test(ua)) {
    return context.next()
  }

  const paperId = context.params.id
  const paperUrl = `${BASE_URL}/papers/${paperId}`

  // Fetch paper metadata from API
  const apiBase = context.env.API_URL || 'https://thedecodedhuman.com/api'
  let title = `Paper Analysis | ${SITE_NAME}`
  let description = 'Deep AI analysis including extracted entities, methodological critique, missed connections, and convergence cluster mapping.'

  try {
    const res = await fetch(`${apiBase}/papers/${paperId}`, {
      headers: { 'Accept': 'application/json' },
      cf: { cacheTtl: 3600 },
    })
    if (res.ok) {
      const paper = await res.json()
      if (paper.title) {
        title = `AI Analysis: ${paper.title} | ${SITE_NAME}`
      }
      if (paper.abstract) {
        description = paper.abstract.length > 155
          ? paper.abstract.substring(0, 155) + '…'
          : paper.abstract
      }
    }
  } catch {
    // Fall through with generic meta on API failure
  }

  // Get the base HTML from static assets
  const assetResponse = await context.env.ASSETS.fetch(new Request(`${BASE_URL}/`))
  let html = await assetResponse.text()

  // Inject paper-specific meta tags
  const safeTitle = escapeHtml(title)
  const safeDesc = escapeHtml(description)

  html = html.replace(/<title>.*?<\/title>/, `<title>${safeTitle}</title>`)
  html = html.replace(/(<meta name="description" content=").*?"/, `$1${safeDesc}"`)
  html = html.replace(/(<link rel="canonical" href=").*?"/, `$1${paperUrl}"`)
  html = html.replace(/(<meta property="og:type" content=").*?"/, `$1article"`)
  html = html.replace(/(<meta property="og:url" content=").*?"/, `$1${paperUrl}"`)
  html = html.replace(/(<meta property="og:title" content=").*?"/, `$1${safeTitle}"`)
  html = html.replace(/(<meta property="og:description" content=").*?"/, `$1${safeDesc}"`)
  html = html.replace(/(<meta name="twitter:title" content=").*?"/, `$1${safeTitle}"`)
  html = html.replace(/(<meta name="twitter:description" content=").*?"/, `$1${safeDesc}"`)

  return new Response(html, {
    headers: {
      'Content-Type': 'text/html;charset=UTF-8',
      'Cache-Control': 'public, s-maxage=3600',
    },
  })
}
