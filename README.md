# WCOA Backend (IBM SDK, fully wired)

Production-oriented FastAPI backend for the Working Capital Optimization Agent (WCOA).

## What is wired

- `POST /datasets/create` for direct upload flow
- `POST /datasets/register` for dataset registration and optional SAS ingest
- `POST /datasets/process` to canonicalize uploaded Excel into minimized JSON
- `POST /chat` as the main WCOA execution endpoint
- IBM Cloud Object Storage for transient encrypted storage
- PostgreSQL for metadata and audit logs (no sensitive content)
- `ibm-watsonx-ai` SDK with `ModelInference`
- Explicit WCOA prompt builder under `app/prompts/wcoa_prompt.py`
- Deterministic finance tool layer under `app/tools/`

## Tool layer included

`app/tools/`
- `discount_tool.py`
- `bnpl_tool.py`
- `npv_tool.py`
- `cashflow_tool.py`
- `supplier_scoring_tool.py`

These tools are called by `app/services/evaluator.py`, and the resulting tool outputs are passed into the deterministic context that is given to Granite.

## Internal execution flow

`/chat`
→ load canonical dataset
→ run deterministic tool layer
→ aggregate evaluation + scoring
→ build WCOA prompt/messages
→ call watsonx.ai
→ return structured JSON + deterministic traces

## Notes

- Keep your working `.env` from the earlier setup.
- The database schema and storage structure were kept aligned with the existing project so earlier DB/COS progress is not broken.
- Raw uploads are deleted after canonicalization. Canonical minimized data remains TTL-bound.
