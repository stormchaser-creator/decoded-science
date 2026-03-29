import { useEffect } from 'react'

const SITE_NAME = 'The Decoded Human'
const BASE_URL = 'https://thedecodedhuman.com'
const DEFAULT_OG_IMAGE = `${BASE_URL}/og-image.png`

function setMeta(attr, key, content) {
  let el = document.querySelector(`meta[${attr}="${key}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

function setLink(rel, href) {
  let el = document.querySelector(`link[rel="${rel}"]`)
  if (!el) {
    el = document.createElement('link')
    el.setAttribute('rel', rel)
    document.head.appendChild(el)
  }
  el.setAttribute('href', href)
}

function setJsonLd(id, data) {
  let el = document.getElementById(id)
  if (!el) {
    el = document.createElement('script')
    el.id = id
    el.type = 'application/ld+json'
    document.head.appendChild(el)
  }
  el.textContent = JSON.stringify(data)
}

function removeJsonLd(id) {
  document.getElementById(id)?.remove()
}

export default function SEO({
  title,
  description,
  path = '/',
  type = 'website',
  image = DEFAULT_OG_IMAGE,
  noindex = false,
  schema = null,
}) {
  const fullTitle = title ? `${title} | ${SITE_NAME}` : `${SITE_NAME} — AI-Powered Literature Connectome`
  const canonicalUrl = `${BASE_URL}${path}`

  useEffect(() => {
    document.title = fullTitle

    setMeta('name', 'description', description)
    setLink('canonical', canonicalUrl)

    if (noindex) {
      setMeta('name', 'robots', 'noindex, nofollow')
    } else {
      document.querySelector('meta[name="robots"]')?.remove()
    }

    setMeta('property', 'og:type', type)
    setMeta('property', 'og:url', canonicalUrl)
    setMeta('property', 'og:title', fullTitle)
    setMeta('property', 'og:description', description)
    setMeta('property', 'og:image', image)
    setMeta('property', 'og:site_name', SITE_NAME)

    setMeta('name', 'twitter:card', 'summary_large_image')
    setMeta('name', 'twitter:title', fullTitle)
    setMeta('name', 'twitter:description', description)
    setMeta('name', 'twitter:image', image)

    if (schema) {
      setJsonLd('seo-jsonld', schema)
    } else {
      removeJsonLd('seo-jsonld')
    }
  }, [fullTitle, description, canonicalUrl, type, image, noindex, schema])

  return null
}
