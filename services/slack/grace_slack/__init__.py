"""grace-slack — Tier 3: #zennify_pmo with authoritative-sender filtering."""

PMO_CHANNEL_ID = "C020PBE8J15"
DEFAULT_DAYS_BACK = 365
MAX_DAYS_BACK = 730
MAX_LIMIT = 100
DEFAULT_LIMIT = 20

SKIPPED_SUBTYPES = frozenset(
    {
        "channel_join",
        "channel_leave",
        "bot_message",
        "channel_topic",
        "channel_purpose",
    }
)
