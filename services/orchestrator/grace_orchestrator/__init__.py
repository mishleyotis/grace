"""grace-orchestrator — fans out a single query across all 3 tiers."""

TIER_WEIGHT = {
    "site_mirror": 100,
    "drive_map": 80,
    "slack": 60,
}

MAX_PER_TIER_LIMIT = 30
DEFAULT_PER_TIER_LIMIT = 10
