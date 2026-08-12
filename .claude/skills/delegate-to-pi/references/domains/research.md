# Research domain pack

## Workspace layout
A research workspace contains `report.md`, `sources.jsonl`, `snapshots/<key>.html`, and `acceptance.md`. Its `.gitignore` should include `var/` so a stray telemetry sink cannot be committed.

## Verify command
```bash
bin/verify-research --workspace "$(pwd)"
```
Derived arithmetic is validated only on an explicit line (optional whitespace and `-` bullet) beginning `Derived:`. Every expression operand must be `[@key:figure]`; `+`, `-`, `*`, `/`, parentheses, and decimals are supported, and the result must recompute. In cited prose paragraphs, every bare number must occur in a cited snapshot or be moved to an explicit `Derived:` line.
Retrieval guidance, verified live 2026-08-10: excerpts must occur byte-for-byte in the raw snapshot, so choose contiguous raw bytes; most HTML prose is split by tags and will not match. arXiv `/abs/<id>` works reliably—take excerpts inside the abstract blockquote and strip the `Abstract:` descriptor span. Raw-text endpoints such as `raw.githubusercontent.com` match trivially. Do not use `export.arxiv.org/api/query`: it returned zero bytes; an empty or whitespace-only excerpt can pass vacuously, so never record one. JS-rendered vendor marketing and product pages match nothing literally; cite them only with `render_required: true`, which skips only excerpt occurrence and force-includes the source in fact-checker sampling. Never paraphrase into a fabricated excerpt.

## Reviewer rubric
`APPROVED` requires acceptance criteria met, verification green, conclusions traceable to evidence, disconfirming evidence addressed, and confidence proportionate to source independence.

## Risk gate
Escalate publishing or sending outside the workspace, contacting a human source, paid data or APIs, authentication/paywall/ToS-restricted retrieval, and personal data. Crew members never perform outward-facing actions.

## Roles
Worker is researcher; reviewer is critic; scout is unchanged. Tester analog is a fact-checker that randomly samples max(5, 20%) of cited sources, force-includes every `render_required` record, independently re-retrieves each source, and confirms its excerpt supports the claim to which it is attached. It returns `SOURCES VERIFIED` only when every sampled source passes, or `SOURCE PROBLEMS:` with reproducible source findings; it never fixes findings.

## Definition of done
`bin/verify-research` is green, acceptance criteria are met, the fact-checker returns `SOURCES VERIFIED`, and the human approves final delivery.
