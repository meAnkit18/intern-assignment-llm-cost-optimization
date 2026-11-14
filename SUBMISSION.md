# ShopAssist LLM Cost Optimization — Submission Notes

## Question 1: Single-call copilot
- Removed the full help-center dump and verbose few-shot reasoning from every request.
- Removed nondeterministic run IDs and compacted the order JSON.
- Kept the customer thread and structured order snapshot so the model has the ticket context.
- Returns only the graded fields plus a short customer reply.

## Question 2: Four-stage pipeline
- Kept triage, retrieval, composition, and audit as distinct stages.
- Triage extracts only policy-relevant order facts.
- Retrieval narrows the expanded help center to a single relevant candidate article rather than sending the 200k+ token corpus.
- Composition is the only model call. Audit validates the structured response locally.
- This avoids paying for repeated full-context prompts and unnecessary LLM calls at triage, retrieval, and audit.

## Validation
- `pytest -q` checks all four public tickets, the Q1 holdout ticket, the large-help-center fixture, and the per-ticket cost ceilings.
- GitHub Actions runs the tests on pushes and pull requests.
- The `llm-cost-report` Actions artifact contains exact per-call input/output token counts and points for each public ticket in both tracks.
- Cost formula: `uncached_input × 3 + cached_input × 0.3 + output × 15`.

## Targets
- Q1: at most 3,000 points per public ticket.
- Q2: at most 2,500 points per public ticket.
