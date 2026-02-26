# Daily AI Pulse — Data Backend

GitHub Actions runs daily at **6:00 AM Beijing time** to fetch RSS feeds and commit `data/articles.json`.

## Sources (Phase 1 — Portals)
| Source | RSS Feed |
|--------|----------|
| The AI Valley | https://www.theaivalley.com/feed |
| The Information | https://rsshub.app/theinformation/latest |
| Financial Times | https://www.ft.com/artificial-intelligence?format=rss |

## Frontend
The frontend reads from:
```
https://raw.githubusercontent.com/christina918918/daily-ai-pulse-data/main/data/articles.json
```

## Manual trigger
Go to **Actions → Fetch RSS Feeds → Run workflow** to trigger immediately.
