// fetch-rss.js - Runs via GitHub Actions to fetch RSS feeds and save articles.json
// Node.js 18+ (uses native fetch)

const fs = require('fs');
const path = require('path');
const { XMLParser } = require('fast-xml-parser');

// ── AI Summarization (optional — only if ANTHROPIC_API_KEY is set) ───────────
let Anthropic;
try { Anthropic = require('@anthropic-ai/sdk'); } catch { Anthropic = null; }

const anthropicOpts = { apiKey: process.env.ANTHROPIC_API_KEY || 'anything' };
if (process.env.ANTHROPIC_BASE_URL) anthropicOpts.baseURL = process.env.ANTHROPIC_BASE_URL;
const AI_MODEL = process.env.AI_MODEL || 'claude-opus-4-6';

const anthropic = (Anthropic && process.env.ANTHROPIC_API_KEY)
  ? new Anthropic(anthropicOpts)
  : null;

async function aiSummarize(title, rawDesc, language) {
  if (!anthropic || !rawDesc || rawDesc.length <= 120) return rawDesc;
  try {
    const lang = language === 'zh' ? '中文' : 'English';
    const msg = await anthropic.messages.create({
      model: AI_MODEL,
      max_tokens: 80,
      messages: [{
        role: 'user',
        content: `Summarize in 1 sentence, max 100 chars, in ${lang}. No quotes.\nTitle: ${title}\nText: ${rawDesc.slice(0, 400)}`,
      }],
    });
    return msg.content[0].text.trim();
  } catch (e) {
    return rawDesc; // fallback to original on error
  }
}

// ── Sources config ──────────────────────────────────────────────────────────
// rss: primary URL; rssAlternate: fallback if primary fails
const SOURCES = [
  // ── Portals (English) ────────────────────────────────────────────────────
  { name: 'The AI Valley',    type: 'portal', language: 'en', company: '',
    rss: 'https://www.theaivalley.com/feed' },
  { name: 'The Information',  type: 'portal', language: 'en', company: '',
    rss: 'https://www.theinformation.com/feed',
    rssAlternate: 'https://rsshub.app/theinformation/latest' },
  { name: 'Financial Times',  type: 'portal', language: 'en', company: '',
    rss: 'https://www.ft.com/artificial-intelligence?format=rss' },

  // ── Company Official Blogs ────────────────────────────────────────────────
  { name: 'OpenAI',           type: 'company', language: 'en', company: 'OpenAI',
    rss: 'https://openai.com/news/rss.xml' },
  { name: 'Anthropic',        type: 'company', language: 'en', company: 'Anthropic',
    rss: 'https://rsshub.app/anthropic/news' },
  { name: 'Google Gemini',    type: 'company', language: 'en', company: 'Google Gemini',
    rss: 'https://blog.google/technology/ai/rss/' },
  { name: 'Meta AI',          type: 'company', language: 'en', company: 'Meta',
    rss: 'https://rsshub.app/meta/ai/blog' },
  { name: 'DeepSeek',         type: 'company', language: 'en', company: 'Deepseek',
    rss: 'https://github.com/deepseek-ai.atom' },
  { name: 'Kimi / Moonshot',  type: 'company', language: 'zh', company: 'Kimi',
    rss: 'https://github.com/MoonshotAI.atom' },
  { name: 'MiniMax',          type: 'company', language: 'zh', company: 'Minimax',
    rss: 'https://github.com/MiniMax-AI.atom' },
  { name: 'Zhipu AI',         type: 'company', language: 'zh', company: 'Zhipu',
    rss: 'https://github.com/zai-org.atom' },
  { name: 'ByteDance Seed',   type: 'company', language: 'en', company: 'ByteDance Seed',
    rss: 'https://github.com/ByteDance-Seed.atom' },
  { name: 'Alibaba Qwen',     type: 'company', language: 'zh', company: 'Alibaba Tongyi',
    rss: 'https://qwenlm.github.io/zh/blog/index.xml' },
  { name: 'Tencent Hunyuan',  type: 'company', language: 'zh', company: 'Tencent Hunyuan',
    rss: 'https://rsshub.app/wechat/official/腾讯混元大模型' },

  // ── Twitter / X KOLs (via RSSHub) ─────────────────────────────────────────
  { name: '@sama',            type: 'twitter', language: 'en', company: 'OpenAI',
    rss: 'https://rsshub.app/twitter/user/sama' },
  { name: '@karpathy',        type: 'twitter', language: 'en', company: '',
    rss: 'https://rsshub.app/twitter/user/karpathy' },
  { name: '@demishassabis',   type: 'twitter', language: 'en', company: 'Google Gemini',
    rss: 'https://rsshub.app/twitter/user/demishassabis' },
  { name: '@AndrewYNg',       type: 'twitter', language: 'en', company: '',
    rss: 'https://rsshub.app/twitter/user/AndrewYNg' },
  { name: '@emollick',        type: 'twitter', language: 'en', company: '',
    rss: 'https://rsshub.app/twitter/user/emollick' },
  { name: '@swyx',            type: 'twitter', language: 'en', company: '',
    rss: 'https://rsshub.app/twitter/user/swyx' },
  { name: '@gdb',             type: 'twitter', language: 'en', company: 'OpenAI',
    rss: 'https://rsshub.app/twitter/user/gdb' },
  { name: '@elonmusk',        type: 'twitter', language: 'en', company: '',
    rss: 'https://rsshub.app/twitter/user/elonmusk' },
  { name: '@NatFriedman',     type: 'twitter', language: 'en', company: '',
    rss: 'https://rsshub.app/twitter/user/NatFriedman' },
  { name: '@ycombinator',     type: 'twitter', language: 'en', company: '',
    rss: 'https://rsshub.app/twitter/user/ycombinator' },

  // ── WeChat / Chinese Media ────────────────────────────────────────────────
  { name: '白鲸出海',          type: 'wechat', language: 'zh', company: '',
    rss: 'https://www.baijing.cn/rss' },
  { name: 'Founder Park',     type: 'wechat', language: 'zh', company: '',
    rss: 'https://www.founderpark.cn/rss' },
  { name: '华尔街见闻',        type: 'wechat', language: 'zh', company: '',
    rss: 'https://wallstreetcn.com/rss.xml',
    rssAlternate: 'https://rsshub.app/wechat/official/华尔街见闻' },
  { name: '海外独角兽',        type: 'wechat', language: 'zh', company: '',
    rss: 'https://rsshub.app/wechat/official/海外独角兽' },
  { name: '虎嗅APP',           type: 'wechat', language: 'zh', company: '',
    rss: 'https://www.huxiu.com/rss/0.xml' },
  { name: '机器之心',          type: 'wechat', language: 'zh', company: '',
    rss: 'https://rsshub.app/wechat/official/机器之心' },
  { name: '量子位',            type: 'wechat', language: 'zh', company: '',
    rss: 'https://rsshub.app/wechat/official/量子位' },
  { name: '人民日报',          type: 'wechat', language: 'zh', company: '',
    rss: 'https://rsshub.app/wechat/official/人民日报' },
  { name: '十字路口 Crossing', type: 'wechat', language: 'zh', company: '',
    rss: 'https://rsshub.app/wechat/official/十字路口Crossing' },
  { name: '投资实习所',        type: 'wechat', language: 'zh', company: '',
    rss: 'https://rsshub.app/wechat/official/投资实习所' },
  { name: '晚点 LatePost',     type: 'wechat', language: 'zh', company: '',
    rss: 'https://rsshub.app/wechat/official/晚点LatePost' },
  { name: '央视新闻',          type: 'wechat', language: 'zh', company: '',
    rss: 'https://rsshub.app/wechat/official/央视新闻' },
  { name: '42章经',            type: 'wechat', language: 'zh', company: '',
    rss: 'https://rsshub.app/wechat/official/四十二章经' },
  { name: '36氪',              type: 'wechat', language: 'zh', company: '',
    rss: 'https://36kr.com/feed' },
  { name: '新智元',            type: 'wechat', language: 'zh', company: '',
    rss: 'https://www.aitime.cn/rss.xml' },
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

function dateOffset(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return toBeijingDateStr(d);
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

        // Keep articles from the past 7 days
        const cutoff = dateOffset(-7);
        if (dateStr < cutoff || dateStr > today) return null;

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
          language: source.language || 'en',
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

  // AI summarization for new articles (if ANTHROPIC_API_KEY is set)
  if (anthropic && newUnique.length > 0) {
    console.log(`\nSummarizing ${newUnique.length} new articles with Claude Haiku…`);
    for (const article of newUnique) {
      article.summary = await aiSummarize(article.title, article.summary, article.language);
    }
  }

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
