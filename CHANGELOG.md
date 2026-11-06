# Agent Studio v2.2 — Retailer-First Search

- Official retailer category/sitemap discovery before a public RSS search when recognised.
- Dedicated super-king bed category discovery for the Bensons for Beds request.
- Wider but bounded same-site anchor crawl (up to 12 pages, two link levels).
- No false failure when public RSS is irrelevant but official links were inspected.
- Report size ambiguity; do not present a default bed frame price as confirmed super king.
- Keeps the original purple interface and AI App Server integration, no external API key.
- No changes to existing AI App Server engine, database, users or settings.

# Agent Studio v2.1 — Relevant Website Research

- Upgrades built-in no-key web search to **rank search results** instead of accepting unrelated listings.
- Opens eligible public HTML pages and follows relevant **same-site anchor links**, one level deep.
- Extracts structured and labelled product prices with product name, exact page URL and source type.
- Separates verified on-page price evidence from unverified search snippets, and flags missing evidence.
- Streams live website search/open/follow/extraction activity into the existing purple Studio monitor.
- Corrects shopping query generation so retailer names like Bensons for Beds are kept intact.
- Retries a shorter query once when a key-free search result set is irrelevant.
- Adds SSRF defenses, public DNS pinning, robots checks, fetch-size limits and bounded crawling.
- Preserves the AI App Server, admin editor at `/admin/studio`, existing user database, custom tools and purple UI.
- Repackages everything in **one full installer**, never an incremental patch.

---
# Agent Studio v2.0 — Complete AI App Server installer

- Fixed the actual v1.9 failure: the Studio API routes were missing even though admin routes appeared. Register every `/studio/*` route directly on the existing FastAPI app, without a separate APIRouter.
- Preflight verifies both GET `/studio/api/studio/status` and POST `/studio/api/studio/run/events` plus `/admin/studio` before announcing success.
- Existing source, settings and SQLite data remain untouched; previous Studio code is backed up and restored on preflight failure.
- Original purple interface retained. The editor remains inside `/admin/studio`.
- No separate patch is required. Extract this complete package and run INSTALL AND RUN.bat.

**Caution:** Live startup on the user's Windows machine, Ollama and MCP access have not been verified here.
