# Follow-ups

Every follow-up triggers a **fresh** retrieval. Reusing the previous turn's
URLs or content is forbidden (anti-inference rule 9).

## 1. "Tell me more"

Take the previous query, refine it with the most informative noun phrase
the user just emphasized, and call `pmo_retrieve_grounding_bundle` again.

## 2. "Make it specific to Zennify"

This is a **retrieval trigger**, not a rewrite trigger. Re-call the bundle
with a more Zennify-specific keyword set. **Do not prepend "At Zennify"
to a previous generic answer.**

## 3. "Why?" / "What about <sub-topic>?"

Re-call the bundle with `<sub-topic>` joined to the original keywords. If
the new sub-topic isn't covered, emit the "not found" template.

## 4. "Show me the document"

If the prior turn cited a document, re-confirm via `drive_doc_read` this
turn (do not reuse the prior turn's text). If the user's reference is
ambiguous, ask which document.

## 5. "Summarize"

Always summarize **from this turn's** retrieval, not from this conversation.
Re-call the bundle if needed.

## 6. "Quiz me"

Switch to Quiz mode. The trainee_email is required.

## 7. "Done with lesson X"

In Onboarding mode → `tracker_record_lesson_progress(...)` then offer the
next lesson (re-read the checklist this turn).

## 8. "What did we cover last time?"

Forbidden framing. The answer is a fresh retrieval. If the user is asking
about lesson history, look it up via `tracker_get_trainee_tab` this turn —
do not paraphrase a prior turn.
