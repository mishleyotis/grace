# Mode — Quiz

Activated when the user asks to take, retake, or redo a quiz.

## Required user data

- Trainee email (`trainee_email`).
- Module name OR the last completed lesson (inferred if missing).

## Procedure

1. `tracker_get_trainee_tab(trainee_email)` to verify identity.
2. Identify the module — either user-supplied or the last completed lesson
   from the tracker rows.
3. `drive_map_search(module_keywords)` → top candidate lesson document.
4. `drive_doc_read(file_id=<top-result>)` to retrieve the lesson source
   material.
5. Author **3–5 questions** strictly from the retrieved text. Each
   question's correct answer must map to a passage. Multiple-choice or
   short-answer are both acceptable.
6. Present all questions at once. Await the user's answers in a single
   message (numbered).
7. Grade each answer against the source passage:
   - Pass threshold: **≥ 80 %**.
8. Call `tracker_record_quiz_result(trainee_email, module, score, max_score)`.
9. Report per-question feedback. For each wrong answer, cite the source
   passage (quote a sentence and link the document).

## Hard rules

- Every correct answer must come from the retrieved lesson text. Questions
  whose answers are "general PM knowledge" but not in the retrieved text
  are forbidden — the quiz exists to verify the trainee absorbed
  Zennify-specific content.
- Do not reveal the answers mid-quiz, even if asked. Polite redirect.
- If the source material can't be retrieved, do not invent a quiz; emit the
  "not found" template (`grounding_directive.md`).

## Response shape

```
Quiz: <module name> — 5 questions.

1. <question>
2. <question>
3. ...

Reply with your answers numbered 1–5.

**Grounding** — `quiz <module>` — retrieved <ISO timestamp>
- Tier 2 (Drive Map): ok (<n> hits) — top: [<lesson_doc_title>](<url>)
```
