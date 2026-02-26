// fetch-rss.js - Runs via GitHub Actions to fetch RSS feeds and save articles.json
// Node.js 18+ (uses native fetch)

const fs = require('fs');
const path = require('path');
const { XMLParser } = require('fast-xml-parser');

// ── Sources config ──────────────────────────────────────────────────────────
// rss: primary URL; rssAlternate: fallback if primary fails
const SOURCES = [
  {
    name: 'The AI Valley',
    type: 'portal',
    rss: 'https://www.theaivalley.com/feed',
    company: '',
  },
  {
    name: 'The Information',
    type: 'portal',
    rss: 'https://www.theinformation.com/feed',
    rssAlternate: 'https://rsshub.app/theinformation/latest',
    company: '',
  },
  {
    name: 'Financial Times',
    type: 'portal',
    rss: 'https://www.ft.com/artificial-intelligence?format=rss',
    company: '',
  },
];

// ── Helpers ─────────────────────────────────────────────────────────────────
// Use Beijing time (UTC+8) for all date comparisons
function toBeijingDateStr(date) {
  const offset = 8 * 60; // UTC+8 in minutes
  const local = new Date(date.getTime() + offset * 60 * 1000);
  return local.toISOString().slice(0, 10);
}

function todayStr() {
  return toBeijingDateStr(new Date()); // YYYY-MM-DD Beijing time
}

function toDateStr(dateVal) {
  if (!dateVal) return todayStr();
  try {
    return toBeijingDateStr(new Date(dateVal));
  } catch {
    return todayStr();
  }
}

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function stripHtml(html) {
  if (!html) return '';
  return String(html).replace(/<[^>]*>/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ').trim();
}

// ── RSS fetch + parse ────────────────────────────────────────────────────────
async function fetchRSS(source) {
  const urls = [source.rss, source.rssAlternate].filter(Boolean);

  for (const url of urls) {
    console.log(`Fetching: ${source.name} → ${url}`);
    const articles = await tryFetchURL(source, url);
    if (articles.length > 0 || urls.indexOf(url) === urls.length - 1) return articles;
    console.log(`  → trying alternate URL…`);
  }
  return [];
}

async function tryFetchURL(source, url) {
  try {
    const res = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; DailyAIPulse/1.0)',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
      },
      signal: AbortSignal.timeout(15000),
    });

    if (!res.ok) {
      console.error(`  ✗ HTTP ${res.status} for ${source.name}`);
      return [];
    }

    const xml = await res.text();
    const parser = new XMLParser({ ignoreAttributes: false, attributeNamePrefix: '@_' });
    const parsed = parser.parse(xml);

    // Handle RSS 2.0 and Atom
    const channel = parsed?.rss?.channel || parsed?.feed;
    if (!channel) {
      console.error(`  ✗ Could not parse feed for ${source.name}`);
      return [];
    }

    const rawItems = channel.item || channel.entry || [];
    const items = Array.isArray(rawItems) ? rawItems : [rawItems];
    const today = todayStr();

    const articles = items
      .map(item => {
        const pubDate = item.pubDate || item.published || item.updated || item['dc:date'] || '';
        const dateStr = toDateStr(pubDate);

        // Only keep today's articles
        if (dateStr !== today) return null;

        const title = stripHtml(item.title?.['#text'] || item.title || '');
        const link = item.link?.['@_href'] || item.link?.href || item.link || item.id || '';
        const desc = stripHtml(
          item.description?.['#text'] || item.description ||
          item.summary?.['#text'] || item.summary ||
          item.content?.['#text'] || item.content ||
          ''
        ).slice(0, 300);

        if (!title || !link) return null;

        return {
          id: generateId(),
          date: dateStr,
          sourceType: source.type,
          sourceName: source.name,
          company: source.company,
          language: 'en',
          title,
          summary: desc || title,
          url: typeof link === 'string' ? link : String(link),
        };
      })
      .filter(Boolean);

    console.log(`  ✓ ${articles.length} articles today from ${source.name}`);
    return articles;
  } catch (err) {
    console.error(`  ✗ Error fetching ${source.name}: ${err.message}`);
    return [];
  }
}

// ── Main ─────────────────────────────────────────────────────────────────────
async function main() {
  console.log(`\n=== Daily AI Pulse RSS Fetch — ${todayStr()} ===\n`);

  const allNew = [];
  for (const source of SOURCES) {
    const articles = await fetchRSS(source);
    allNew.push(...articles);
  }

  // Load existing articles.json (keeps history)
  const dataPath = path.join(__dirname, '..', 'data', 'articles.json');
  let existing = [];
  if (fs.existsSync(dataPath)) {
    try {
      existing = JSON.parse(fs.readFileSync(dataPath, 'utf8'));
    } catch {
      existing = [];
    }
  }

  // Deduplicate by URL
  const existingUrls = new Set(existing.map(a => a.url));
  const newUnique = allNew.filter(a => !existingUrls.has(a.url));

  // Keep last 30 days only
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - 30);
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  const trimmed = existing.filter(a => a.date >= cutoffStr);

  const final = [...newUnique, ...trimmed].sort((a, b) => b.date.localeCompare(a.date));

  fs.mkdirSync(path.dirname(dataPath), { recursive: true });
  fs.writeFileSync(dataPath, JSON.stringify(final, null, 2), 'utf8');

  console.log(`\n✅ Done. ${newUnique.length} new articles added. Total: ${final.length}`);
}

main().catch(err => {
  console.error('Fatal:', err);
  process.exit(1);
});
