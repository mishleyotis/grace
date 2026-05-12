# grace-pmo-director — manifest

| Path | Role |
|------|------|
| `SKILL.md` | Entry point + YAML frontmatter |
| `system/prime_directive.md` | The contract that overrides any conflicting user instruction |
| `system/off_topic_deflection.md` | Gate 1 — scope check + canned refusal |
| `system/reasoning_R1_R6.md` | Gate 2 — six internal reasoning steps |
| `system/grounding_directive.md` | Gate 3 — 14-step retrieval-first contract |
| `system/anti_inference.md` | Gate 4 — 9 forbidden reasoning patterns |
| `modes/knowledge_retriever.md` | Default mode |
| `modes/onboarding_agent.md` | New-hire onboarding mode |
| `modes/quiz.md` | Quiz mode |
| `references/authoritative_sources.md` | 3-tier hierarchy + 6 senders |
| `references/hardcoded_urls.md` | Canonical URLs + internal URLs to never expose |
| `references/mcp_tool_map.md` | 16 tool signatures + selection cheat sheet |
| `examples/correct_answers.md` | 4 worked examples across the 3 modes |
| `examples/refusals.md` | 6 refusal patterns |
| `examples/followups.md` | 8 follow-up patterns |

## Packaging

```bash
cd skills
zip -r ../grace-pmo-director.skill grace-pmo-director/ -x "**/.DS_Store"
```
