# Authoritative sources

## Tier 1 — ZennSource Site Mirror

Snapshot of `sites.google.com/zennify.com/delivery/...` exposed via a Google
Apps Script web app. Each page is mirrored as a section in a single Google
Doc; the Apps Script exposes a JSON API.

- Canonical citation URL pattern: `https://sites.google.com/zennify.com/delivery/<page>`
- Tools: see `mcp_tool_map.md` (`site_mirror_*`)

## Tier 2 — Drive Map + Onboarding Tracker + ZennSource Drive

- **Drive Map sheet** — id `19VQxsUb7pnnxTWP0vQzLLjIZWKU3k382lOEVYSnyiKE`,
  361 rows × 13 columns, read in 3 chunks: `A1:M150`, `A151:M300`, `A301:M400`.
- **Onboarding Tracker** — id `197CSSit_xi872N8oF3_uhV-LYxvRQwA42rfkknLCgEc`,
  one tab per trainee, named by lowercased email.
- **ZennSource Drive** — shared drive `0AGq-3ZBpQU5MUk9PVA`. All
  PM documents indexed by the Drive Map live here.

ZS_-prefixed documents are the Source of Truth — they get a +100 ranking
bonus.

## Tier 3 — Slack `#zennify_pmo`

- Channel id: `C020PBE8J15`
- History window: last 365 days (max 730).
- **Authoritative senders** — the only voices that count as policy:

| # | Name |
|---|------|
| 1 | Kallen |
| 2 | Mike Theiler |
| 3 | Bryan Babb |
| 4 | Stephanie Brooks |
| 5 | Michael Rouleau |
| 6 | Tom Hedgecoth |

Slack defaults to `authoritative_only=True`. Non-authoritative messages may
be cited for **context** but never as **policy**.

## Tier authority order

```
TIER_WEIGHT = {
    "site_mirror": 100,   ← canonical
    "drive_map":    80,   ← supporting
    "slack":        60,   ← recent context
}
```

A ZS_ Drive Map document with a strong inner-search match can outrank a
plain Site Mirror snippet — that is by design (concurrence of signals).
Slack alone never overrides Tier 1 / Tier 2.
