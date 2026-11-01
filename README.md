# SlabSense

**An evidence-grounded AI assistant for Tamil Nadu electricity tariffs and regulations.**

## Problem

Electricity tariffs, subsidy provisions, and billing rules in Tamil Nadu are published across multiple TNERC orders, government subsidy orders, and regulatory codes. Junior engineers handling consumer complaints must manually search these documents to explain bill calculations and identify the provisions applicable to a particular billing period. Online answers may rely on outdated tariff rules, leading to incorrect explanations. SlabSense is designed to retrieve relevant regulatory provisions, consider their effective dates, and provide answers linked to supporting source documents and pages.

## Who it is for

- Junior engineers at TNPDCL section offices who answer consumer billing complaints.
- Developers and maintainers of electricity tariff calculators who need to verify tariff-rate changes against official regulatory orders.

## Signature feature

The **Bill-Period Time Machine** identifies the regulatory provisions applicable to a selected billing period and presents the relevant tariff slabs, eligible free units, subsidy provisions, and supporting citations.

## Hardest problem (my interview story)

The hardest problem is ensuring that every answer uses the correct version of the tariff rules for the period in question. A newer order must not automatically replace an earlier order for a historical billing period. SlabSense must track order metadata, effective dates, amendments, and relevant subsidy provisions, then retrieve evidence that supports its answer. When the available documents cannot establish an answer, the system must clearly report the limitation instead of inventing a tariff rate or legal requirement.

## Dataset

| Source | Link | Documents | Pages | Licence / terms |
|---|---|---:|---:|---|
| TNERC tariff orders and regulatory documents | [TNERC Tariff Orders](https://tnerc.tn.gov.in/website/TariffOrders.aspx?type=TO) | To be inventoried | To be counted | Verify applicable source terms |
| Government subsidy orders and letters | Official government sources to be catalogued | To be inventoried | To be counted | Verify applicable source terms |

The target dataset includes tariff orders, applicable subsidy orders, electricity supply and distribution codes with amendments, Grid Code 2026, and relevant TNERC press releases. The projected scale is 250+ documents and 3,000+ pages; these are collection targets, not verified totals.

## 10 real questions

See [docs/QUESTIONS.md](docs/QUESTIONS.md).

## Run locally

Create and activate a virtual environment.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Set `GEMINI_API_KEY` in `.env`, then start the API:

```bash
uvicorn app.main:app --reload
```

Check the health endpoint at [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health). Interactive API documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | API health check |
| `POST` | `/chat` | Generate a structured AI chat response |
| `POST` | `/chat/stream` | Stream response text as Server-Sent Events (SSE) |
| `GET` | `/usage` | Return aggregate usage, model breakdown, and recent requests |

### Chat request

Both chat endpoints accept a JSON body with a `message` field:

```json
{
  "message": "Explain electricity tariff slabs briefly."
}
```

Example non-streaming request:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Explain electricity tariff slabs briefly."}'
```

### Streaming response

The `POST /chat/stream` endpoint responds with `Content-Type: text/event-stream`. It emits:

- `delta` — an incremental text chunk.
- `completed` — the completed response and usage metadata.
- `done` — the end-of-stream marker.
- `error` — a stream error after the response has started.

Example request (the `-N` option disables curl output buffering):

```bash
curl -N -X POST http://127.0.0.1:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"Explain electricity tariff slabs briefly."}'
```

### Usage summary

```bash
curl "http://127.0.0.1:8000/usage?recent_limit=20"
```

Usage records include model and token information and an estimated cost where pricing is available. The estimate is not a billing statement.

## Run with Docker Compose

The Compose stack runs the FastAPI service and PostgreSQL with pgvector. It binds the API to `127.0.0.1:8000` and PostgreSQL to `127.0.0.1:5433`.

1. Copy the example environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Set `GEMINI_API_KEY` and a strong, private `POSTGRES_PASSWORD` in `.env`. Do not commit `.env` or share its values.

3. Build and start the services:

   ```bash
   docker compose up -d --build
   ```

4. Check service health and API availability:

   ```bash
   docker compose ps
   curl http://127.0.0.1:8000/health
   ```

View API logs with `docker compose logs -f api`. Stopping the stack with `docker compose down` preserves the named PostgreSQL volume. Do not use `docker compose down -v` unless you intentionally want to delete that database volume and its data.

## Evaluation target

The target is at least 98% version accuracy on a 150-question date-specific test set. This is a goal to validate experimentally, not a measured result.

## Live link

Production deployment is pending. The local and Docker URLs above are not public endpoints; the production API URL will be added here after deployment and verification.

## Acknowledgements

The initial repository structure was adapted from
[genai-starter-repo](https://github.com/govindchandak/genai-starter-repo).
