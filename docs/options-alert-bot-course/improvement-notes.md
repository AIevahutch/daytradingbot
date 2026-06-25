# Improvement Notes

## Purpose

This file records issues, gaps, and recommendations found while creating the course package.

No code was changed. No bugs were fixed. No trading logic was modified.

## Bugs Or Issues Found

Recommended improvement:

- Audit secret handling before sharing the repo. The working tree showed an untracked `.env.save` file in `git status --short`. This documentation task did not open it. The owner should inspect it privately, rotate exposed credentials if needed, and ensure it is not distributed.

Recommended improvement:

- Audit deploy/private key handling before sharing the repo. If a `.deploy_keys/` folder or other private-key material exists locally, keep it out of course packages and public repos.

Recommended improvement:

- Audit validation threshold wording. A prior read-only safety review reported an issue-template reference to threshold `85`, while current README/config docs use `80`. The owner should decide whether older references should be updated later.

Recommended improvement:

- Add a portable student-facing disclaimer block to any future public README or course export. The current repo has strong alert-only language, but the course benefits from one repeatable disclaimer.

Recommended improvement:

- Consider adding nearby "paper/replay only, not predictive" caveats around dashboard metrics such as win rate, profit factor, tactical win rate, and R metrics.

Recommended improvement:

- Consider softening demo alert wording for students. If current Telegram copy begins with action-oriented language, course narration should reframe it as "watch setup" or "management alert" language.

## Missing Tests

Unknown / needs owner answer:

- This documentation task did not run tests, so no current pass/fail test count is included.
- The existing test suite appears broad, but current dirty/uncommitted files should be validated before the course package is distributed as "current."

Potential future test coverage to verify:

- Research missing-source empty states.
- Dashboard optional table fallbacks.
- Telegram formatting with manual-review wording.
- Prompt/docs threshold consistency.
- Secret-file exclusion in packaged materials.

## Missing Docs

Recommended improvement:

- Add a short "public sharing checklist" for removing `.env`, `.env.save`, local databases, runtime logs, deploy keys, and private screenshots before distributing the repo.

Recommended improvement:

- Add a concise "what AI does and does not do" section to the main README if the research summary feature becomes student-facing.

Recommended improvement:

- Add a standalone architecture diagram image or Mermaid diagram if students need a visual handout later.

## Risk-Management Improvements

Recommended improvement only, not applied:

- Keep any future options examples generic and educational. Avoid specific contract, strike, broker action, or profit language.

Recommended improvement only, not applied:

- Keep research as a blocker/penalty only. Do not let research or AI create alerts without a rule-based chart setup.

Recommended improvement only, not applied:

- Continue treating SPY VWAP reclaim long caution as review-controlled, not an automatic broad SPY ban.

## Code Clarity Improvements

Recommended improvement only, not applied:

- If this bot becomes a student template, consider adding a docs-only module map with links to the exact files for each class session.

Recommended improvement only, not applied:

- Add read-only diagram comments or docstrings only if the owner wants the source to become teaching-first. This task intentionally did not edit source files.

## Course Improvements

Recommended improvement:

- Prepare sanitized screenshots of the dashboard for students if live Streamlit is not used in class.

Recommended improvement:

- Prepare mock Telegram alert examples with clearly educational wording.

Recommended improvement:

- Prepare fixture replay rows for the class activity so students do not need live market data.

## Questions For The Project Owner

See `questions-for-owner.md` for the full list.
