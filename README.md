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

## Run it

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

Start the API:

```bash
uvicorn app.main:app --reload
```

Check the health endpoint at [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health). Interactive API documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## Evaluation target

The target is at least 98% version accuracy on a 150-question date-specific test set. This is a goal to validate experimentally, not a measured result.

## Live link

To be added after deployment.

## Acknowledgements

The initial repository structure was adapted from
[genai-starter-repo](https://github.com/govindchandak/genai-starter-repo).