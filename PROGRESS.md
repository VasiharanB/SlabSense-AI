# Progress

Commit after every class. Tag every Friday: `git tag week-N && git push origin week-N`.

## Week 1 (tag week-1 by Fri 23 Oct)
- [x] Repo created from the Examate template
- [x] Repository registered on the form
- [x] README top section filled from my project card
- [x] /health runs locally
- [x] docs/QUESTIONS.md: 10 real questions
- [x] 50+ pages collected, DATASET.md filled, sample in data/sample/
- [x] Tag week-1 pushed

## Week 2 (tag week-2 by Fri 30 Oct)
- [x] POST /chat calls an LLM and returns structured JSON
- [x] Streaming, timeouts, retry and a fallback model
- [x] Cost log + GET /usage
- [x] Docker Compose (API + Postgres/pgvector) runs
- [x] CI green on Python 3.12 and 3.14, including Docker Compose validation and image build
- [x] Production deployment live; Swagger and POST /chat returned 200 OK, with the successful request persisted in Supabase and the live API link documented in README
- [ ] Tag week-2 pushed

## Week 3 (tag week-3 by Fri 6 Nov)
- [ ] Parser keeps page numbers and headings
- [ ] 500+ pages chunked, embedded and stored in pgvector
- [ ] POST /ask answers with [document, page] citations
- [ ] docs/EVAL_v0.md with my 10 questions scored
- [ ] Tag week-3 pushed

## Daily log
| Date | What I did today | Commit |
|---|---|---|
| 2026-10-25 | Confirmed repository registration, verified local /health, documented five PDFs totalling 639 physical pages, committed three sample PDFs, confirmed 10 evaluation questions, and pushed the week-1 tag. | 8b0954e, 99f8f8c |
| 2026-11-01 | Implemented and tested Gemini SSE streaming, verified local Ruff and 20 tests, passed CI on Python 3.12 and 3.14, deployed the API to Render Free, confirmed POST /chat returned 200 OK, and matched its request ID to a persisted Supabase usage record. Live deployment documented; the week-2 tag still needs to be pushed. | f96c038, 6ce0ece |
