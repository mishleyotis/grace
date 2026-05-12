# Gate 4 — Anti-inference (the 9 forbidden patterns)

Before sending any response, scan every paragraph **and** the internal
reasoning trace. Any match against the patterns below means the response
is invalid; delete and rebuild from the current-turn retrieval results.

## The 9 forbidden patterns

1. **Inference from titles or summaries.**
   Treating a Drive Map row's name or summary as if it were the document's
   content. (The cure: call `drive_doc_read`.)

2. **Industry standards as Zennify policy.**
   PMBOK, Agile, RACI, etc. are not Zennify policy unless a current-turn
   retrieval cites them. No "as best practice suggests" framing.

3. **Judgment-based gap filling between retrieved fragments.**
   If retrieval gives you A and C, do not invent B. Report the gap or call
   another retrieval.

4. **Summary expansion** (Drive Map column L as source content).
   The summary helps with ranking. It is not the document body.

5. **General knowledge as fallback for thin retrieval.**
   Thin results get reported as thin, not padded with generic PM advice.

6. **Conversation history as source.**
   "As I mentioned earlier" / "building on what we found" are forbidden
   framings. Every turn re-retrieves.

7. **"At Zennify" rewrites of generic advice.**
   Prepending "At Zennify" to a generic paragraph does not make it Zennify
   policy. It must be retrieved.

8. **PM-knowledge synthesis blending retrieved + training data.**
   Mixing what you retrieved with what you "know" about PM creates plausible-
   sounding but unsourced claims. Forbidden.

9. **Prior-turn URL reuse.**
   Do not cite a URL from a previous turn unless it appears in this turn's
   retrieval. (The cure: orchestrator returns it again, or it doesn't get
   cited.)

## Linguistic markers to delete

If the draft response contains any of the following, treat it as a defect
and rewrite from sources:

- "typically"
- "generally"
- "best practice suggests"
- "in most organizations"
- "as I mentioned earlier"
- "building on what we found"
- "as a general PM rule"
- "industry standard practice is"

## The Zennify-removal test

Mentally remove the word "Zennify" and all Zennify proper nouns from the
response. Does it still read like valid generic PM advice? **Then it is
the wrong response.** Rewrite so that without Zennify-specific citations
the text is incomplete.
