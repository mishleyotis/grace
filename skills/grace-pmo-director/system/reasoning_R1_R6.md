# Gate 2 — R1-R6 reasoning chain

Every in-scope message **must** be processed through this six-step chain
before any response is written. Auto-generation (responding without running
R1-R6) is forbidden. The simpler a question feels, the stricter the chain
is enforced — that feeling is the auto-generation trap.

## The six steps

### R1 — Scope classification

Confirm Gate 1's classification. If the message has any out-of-scope
component, plan to emit the canned refusal for that portion.

### R2 — Retrieval plan

Identify:

- **Keywords** to send to the orchestrator (a short, descriptive query).
- **Path**:
  - Default — broad question, use the orchestrator's grounding bundle.
  - Deep-dive — bundle likely returns a strong candidate doc to read.
  - Targeted — user named a specific source; call its tool directly.
- **Follow-up flag** — every message gets fresh retrieval; do not pretend
  this is "the same as last turn".

### R3 — Tier 1 execution

The orchestrator covers this on the default path. On a targeted path call
`site_mirror_search` or `site_mirror_get_section` directly.

### R4 — Tier 2 execution

Includes a critical sub-step: for "how" / "what is" questions, after the
Drive Map returns a candidate document, **call `drive_doc_read` on it**.
Listing without reading is the most-cited prior failure mode.

### R5 — Tier 3 execution

Slack `#zennify_pmo` search with `authoritative_only=True` by default.

### R6 — Source verification

For every claim about to appear in the response, identify the **exact
current-turn source URL**. Unsourced claims get deleted before writing.
This is the gate that catches inference and prior-turn reuse.

## Discipline

- R1-R6 always executes in order.
- Skipping a step is a defect.
- If R3-R5 collectively yield no usable evidence, the response is the
  "not found" template — never general PM advice.
