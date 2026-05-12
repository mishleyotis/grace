"""grace-sheets — Tier 2: Drive Map + Drive doc reader + Onboarding Tracker."""

# Hardcoded canonical IDs (per the design)
DRIVE_MAP_SPREADSHEET_ID = "19VQxsUb7pnnxTWP0vQzLLjIZWKU3k382lOEVYSnyiKE"
TRACKER_SPREADSHEET_ID = "197CSSit_xi872N8oF3_uhV-LYxvRQwA42rfkknLCgEc"
ZENNSOURCE_DRIVE_ID = "0AGq-3ZBpQU5MUk9PVA"

# Sheets API chunked-read ranges
DRIVE_MAP_CHUNKS: tuple[str, ...] = ("A1:M150", "A151:M300", "A301:M400")
