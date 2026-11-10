# Diagnostic Model Smoke Test

- Test time: 2026-09-23 19:13:40 -04:00 (America/Indianapolis)
- Model: `gpt-5.6-sol`
- Reasoning effort: `medium`
- LangSmith tracing: disabled
- Client automatic retries: `0`
- Attempts: one execution of the diagnostic prototype; no retry was required

No API key, authorization header, or complete request payload is stored in this report.

## Diagnostic questions

Command, run from the repository root:

```powershell
.\.venv\Scripts\python.exe .\examples\diagnostic_questions.py
```

Result: **PASS** (exit code 0)

- Exactly three questions were returned.
- Every item contained `question`, `purpose`, `resume_evidence`, and `needs_confirmation`.
- Pydantic validation passed, including the exactly-three-items constraint.
- The existing evidence validator passed.
- Both non-empty `resume_evidence` values were exact substrings of the fictional resume.
- The third question used empty evidence and explicitly requested confirmation because testing automated workflows was not stated in the resume.
- Manual review found no obvious invented candidate fact. The questions ask for detail or confirmation rather than asserting unsupported experience. This smoke test is not an exhaustive content-quality evaluation.
- API-reported usage: 453 input tokens, 233 output tokens, 686 total tokens.

Short output summary: the questions covered Python ticket automation and its measured impact, SQL support-trend reporting and stakeholder communication, and the unconfirmed gap around testing automated workflows.

## Configuration and verification changes

- Set `ChatOpenAI` reasoning effort to `medium`.
- Reduced client automatic retries from 2 to 0 to bound paid requests.
- Forced LangSmith tracing off at runtime for the diagnostic prototype.
- Added credential-free API usage summaries when usage metadata is returned.

## Not verified

- Other prompts, models, providers, accounts, and network conditions were not tested.
- LangSmith tracing was intentionally not tested.
- No real resume, real job description, production workflow, long conversation, concurrency, or failure-recovery scenario was tested.
