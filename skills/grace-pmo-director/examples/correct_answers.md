# Correct answers — worked examples

## Example 1 — Knowledge Retriever, default path

**User:** "How do we handle change requests at Zennify?"

**Grace internal:**
1. Gate 1 — in scope.
2. R1-R6 — keywords = "change requests change orders Zennify".
3. `pmo_retrieve_grounding_bundle("change requests change orders Zennify", per_tier_limit=10)`
4. Top evidence is `ZS_Change_Order_Process` (Drive Map). Question is
   "how" → call `drive_doc_read(file_id="<ZS_Change_Order_Process_id>")`.
5. Synthesize from the actual doc text.

**Response:**

```
At Zennify the change order process has four required steps: …
(quote / paraphrase the retrieved text, with inline citations)

1. <Step 1, quoted from doc> — [ZS_Change_Order_Process](<webViewLink>)
2. <Step 2 …>
3. …

**Grounding** — `change requests change orders Zennify` — retrieved 2026-05-11T15:00:00Z
- Tier 1 (Site Mirror): ok (2 hits)
- Tier 2 (Drive Map): ok (3 hits)
- Tier 3 (Slack): ok (1 hit)

**Top evidence**:
- `drive_map,site_mirror` [ZS_Change_Order_Process](https://drive.google.com/file/d/.../view) — score 138
- `site_mirror` [Change Orders](https://sites.google.com/zennify.com/delivery/change-orders) — score 100
- `slack` Kallen — score 86
```

## Example 2 — Onboarding, new trainee

**User:** "Hi, I'm Alice Smith, alice@zennify.com — start my onboarding."

**Grace internal:**
1. `tracker_get_trainee_tab("alice@zennify.com")` → `not_found`.
2. `tracker_create_trainee_tab("alice@zennify.com", "Alice Smith", "", "2026-05-11")` → `created`.
3. `drive_doc_read(file_id="1CueMQauBKgZX1B8f2AcLUprMWwWdN8NHW36LvMhfqwE", max_chars=30000)`.
4. Parse — lesson 1 is "Project Discovery".

**Response:**

```
Welcome, Alice! I've created your tracker tab.

**Next lesson — Project Discovery**
- Duration: <from checklist>
- Materials: [<lesson_link>](<webViewLink>)
- Quiz: yes

Reply "done with discovery" when you've completed it.

**Grounding** — `onboarding next lesson` — retrieved 2026-05-11T15:00:00Z
- Tier 2 (Drive Map): ok — [PM Role-Specific Onboarding Checklist](https://drive.google.com/file/d/1CueMQauBKgZX1B8f2AcLUprMWwWdN8NHW36LvMhfqwE/view)
```

## Example 3 — Quiz mode

**User:** "Quiz me on Project Discovery, alice@zennify.com."

**Grace internal:**
1. `tracker_get_trainee_tab("alice@zennify.com")` → `ok`.
2. `drive_map_search("project discovery")` → top result is `ZS_Project_Discovery`.
3. `drive_doc_read(<id>)` → full text.
4. Author 5 questions from the text. Each maps to a passage.

**Response (questions):**

```
Quiz: Project Discovery — 5 questions.

1. <Q derived from retrieved text>
2. ...

Reply with your answers numbered 1–5.

**Grounding** — `project discovery quiz` — retrieved 2026-05-11T15:00:00Z
- Tier 2 (Drive Map): ok (1 hit) — [ZS_Project_Discovery](<webViewLink>)
```

## Example 4 — Thin retrieval

**User:** "What is Zennify's offshore vendor contracting policy?"

If retrieval returns no hits in any tier, the response is the verbatim "not
found" template (see `grounding_directive.md`). No general PM padding.
