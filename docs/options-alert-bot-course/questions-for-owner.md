# Questions For Owner

## Must-Answer Questions

- Should `.env.save` be deleted, ignored, or kept privately outside the repo before any student distribution?
- Have any credentials in local environment or backup files been rotated?
- Should any deploy keys or private key folders be removed from the teaching copy?
- Are the current uncommitted research, email, runtime, dashboard, and test files part of the official student-facing version?
- Should students ever run live API/service calls in class, or should all demos use placeholders and mocks?
- Should API-backed OpenAI summaries remain out of scope for students, with the course using the local/deterministic fallback only?

## Nice-To-Have Questions

- Do you want the course to include screenshots of the dashboard?
- Do you want class demos to use a prepared fake SQLite database?
- Do you want a printable PDF version of the course materials later?
- Should the final project be graded with a rubric?

## Course-Polish Questions

- Do you prefer the course title "Build And Understand A SPY/QQQ/IWM Alert-Only Options Bot With Codex" or a more beginner-friendly title?
- Should the class mention options concepts only lightly, or include a short glossary?
- Should the class include a 10-minute "how to read an alert" worksheet?
- Should the instructor scripts be shortened for a live workshop format?

## Trading/Risk Questions

- Should student materials include any example option premium assumptions, or should they avoid contract-level examples entirely?
- Should the SPY VWAP reclaim long block be taught as a specific current repo safety gate?
- Should the course mention the Phase-1 small-account assumptions from prior replay discussions, or keep sizing completely out of scope?
- What exact wording do you want for "not financial advice" in public-facing materials?

## Technical Setup Questions

- Which Python version should be recommended as the default for students?
- Should students install from `requirements.txt` only, or should `pyproject.toml` installation be taught?
- Should macOS launchd setup be taught, mentioned only as optional, or omitted?
- Should dashboard launch be live in class or walkthrough-only?
- Should Telegram test be skipped unless students have their own bot token?

## Prompt-History Questions

- Do you have the original master prompt that created the first MVP?
- Do you want exact original chat exports included if they exist outside the repo?
- Should reconstructed prompts be rewritten in your voice?
- Should the acceptance and A+ precision prompts be copied fully into the course bundle or referenced from existing docs?

## Distribution Questions

- Will this folder be distributed alone or together with the full repo?
- Should student copies include `data/` samples, or should runtime data be excluded?
- Should logs be excluded from student materials?
- Should `.github/` issue templates be included after threshold consistency is checked?
