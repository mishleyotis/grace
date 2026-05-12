# MCP tool map (16 tools across 4 services)

## grace-site-mirror (Tier 1, 5 tools)

| Tool | Signature |
|------|-----------|
| `site_mirror_get_section` | `(name: str)` |
| `site_mirror_search` | `(query: str, limit: int = 10)` |
| `site_mirror_get_url_index` | `()` |
| `site_mirror_get_nav_map` | `()` |
| `site_mirror_get_page_links` | `(page_name: str)` |

## grace-sheets (Tier 2 + tracker, 8 tools)

| Tool | Signature |
|------|-----------|
| `drive_map_read_chunk` | `(chunk_index: int)` |
| `drive_map_search` | `(query: str, limit: int = 10)` |
| `drive_doc_read` | `(file_id: str, max_chars: int = 30000)` |
| `drive_doc_read_section` | `(file_id: str, section_query: str, context_paragraphs: int = 2)` |
| `tracker_get_trainee_tab` | `(trainee_email: str)` |
| `tracker_create_trainee_tab` | `(trainee_email: str, full_name: str = "", cohort: str = "", start_date: str = "")` |
| `tracker_record_lesson_progress` | `(trainee_email: str, lesson_id: str, lesson_name: str, status: str = "completed", notes: str = "")` |
| `tracker_record_quiz_result` | `(trainee_email: str, module: str, score: int, max_score: int, passed: bool = None, notes: str = "")` |

## grace-slack (Tier 3, 2 tools)

| Tool | Signature |
|------|-----------|
| `slack_search_pmo` | `(query: str, days_back: int = 365, limit: int = 20, authoritative_only: bool = True)` |
| `slack_get_thread` | `(thread_ts: str, limit: int = 100)` |

## grace-orchestrator (composer, 1 tool)

| Tool | Signature |
|------|-----------|
| `pmo_retrieve_grounding_bundle` | `(query: str, practice_area: str = "", sender_email: str = "", slack_authoritative_only: bool = True, per_tier_limit: int = 10)` |

## Tool selection cheat sheet

| Situation | Tool |
|-----------|------|
| Default broad PMO question | `pmo_retrieve_grounding_bundle` |
| User asked "how does X work?" and Tier 2 returned a candidate | `drive_doc_read` on the candidate |
| User asks about a specific section of a doc | `drive_doc_read_section` |
| User names a specific Site Mirror page | `site_mirror_get_section` |
| User names a specific Drive document | `drive_doc_read` |
| User asks about a Slack discussion | `slack_search_pmo` then `slack_get_thread` |
| Onboarding intent | `tracker_get_trainee_tab` → maybe `tracker_create_trainee_tab` → `drive_doc_read` on the checklist |
| Quiz intent | `tracker_get_trainee_tab` → `drive_map_search` → `drive_doc_read` → grade → `tracker_record_quiz_result` |
