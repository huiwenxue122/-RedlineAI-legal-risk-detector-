# ContractSentinel — Progress & Milestones

This document records what was done in each phase, **main problems encountered**, **how they were solved**, and **results**. It supports both复盘 and sharing the development process with others.

---

## Phase 0: Project skeleton and data models

### Done

- **Project layout and config**: `app/` package, `app/config.py` (`get_settings()`, `.env`), `requirements.txt`; `__init__.py` for `parsing`, `extraction`, `graph`, `retrieval`, `agents`, `schemas`, `api`, `evaluation`.
- **Schemas**: `app/schemas/contract.py` (Clause, Definition, Party, Obligation, CrossReference, Contract), `app/schemas/playbook.py` (Rule, RiskLevel), `app/schemas/risk_memo.py`, `app/schemas/api_models.py`.

### Result

- `import app` works; `get_settings()` reads NEO4J_*, OPENAI_API_KEY, openai_model; dependencies install via `pip install -r requirements.txt`.

---

## Phase 1: Structural layer

### Task 3: PDF parsing (Marker)

- **Done**: `app/parsing/` — Marker turns PDF into layout-aware text blocks; public API `parse_pdf(path) -> (full_text, blocks)`.
- **Result**: Sample PDF (e.g. `EX-10.4(a).pdf`) parses to full text and per-page blocks.

### Task 4: Legal entity and relation extraction (LLM)

- **Done**: `app/extraction/prompts.py`, `app/extraction/entities.py` (`extract_contract` — single LLM call for clauses, definitions, parties, obligations, cross_references); `app/extraction/clause_segmenter.py` (rule-based segmentation by Section X.Y); `app/extraction/cross_references.py` (rule-based cross-ref parsing → CrossReference list).
- **Flow**: Pipeline uses “rule-based segmentation first”: `segment_clauses(full_text)` yields clauses; if present, they override LLM clauses; then cross-references are extracted over clauses.
- **Result**: Output matches `schemas.contract` and is ready for ingest.

### Task 5: Neo4j graph storage and query

- **Done**: `app/graph/client.py`, `app/graph/models.py` (node/edge constants), `app/graph/ingest.py` (Contract → Clause, Definition, Party, Obligation; HAS_CLAUSE, DEFINES, HAS_OBLIGATION, HAS_PARTY, REFERENCES), `app/graph/query.py` (`get_clause_neighborhood`: clause text, section_id, references_in/out, definitions, obligations).
- **Result**: Extraction can be written to Neo4j; clauses queryable by contract_id and clause_id.

### Task 6: Structural pipeline end-to-end

- **Done**: `scripts/run_structural_pipeline.py` (PDF → parse → segment_clauses → extract_contract → extract_cross_references → ingest_contract); `scripts/verify_extraction.py` (LLM-only extraction and export to `out/contract_<stem>.json`).
- **Result**: One command runs PDF → rule-based segments → LLM extraction → cross-refs → Neo4j; the graph contains clauses and reference links.

---

## Phase 2: Reasoning layer — retrieval and playbook

### Task 7: Playbook configuration and loading

- **Done**: `data/playbooks/default.yaml` (rules R001–R00x: unlimited liability, unilateral termination, broad indemnification, data usage, IP transfer, unilateral amendment, etc., with keywords, criteria, risk_level); `app/agents/playbook_loader.py` (YAML → List[Rule]).
- **Result**: Scanner loads a list of rules from the playbook.

### Task 8: Graph-augmented retrieval (RAG + graph context)

- **Done**: `app/retrieval/graph_context.py` (`build_graph_context`: definitions, obligations, references from `get_clause_neighborhood` → one text block); `app/retrieval/rag.py` (`get_context_for_clause`: returns `clause_text`, `section_id`, `graph_context`, `snippets`); `scripts/run_retrieval_demo.py` (random or specified contract_id/clause_id, prints clause_text, graph_context, snippets).
- **Result**: Given contract_id and clause_id, the system returns clause text and graph context for the Scanner.

---

## Phase 3: Reasoning layer — Scanner agent and full-contract scan

### Task 9: Scanner agent

- **Done**: `app/agents/prompts.py` (SCANNER_SYSTEM, SCANNER_USER_TEMPLATE); `app/agents/scanner.py` (`scan_clause(clause_text, clause_ref, rules, graph_context)`, OpenAI JSON mode, parses findings, accepts `rule_triggered`/`rule_id`, `evidence_summary`/`evidence`); `scripts/run_scanner_demo.py` (gets clause from graph via get_context_for_clause → scan_clause, prints findings).

#### Issue 1: Scanner always returned 0 findings on random sections

- **Symptom**: Running the Scanner on several sections always showed Findings: 0 (none).
- **Possible causes**: Bug in Scanner, rules not matching the contract, or empty `clause_text` passed to the model.
- **Diagnostics**:
  - **Diagnostic 1**: A hand-crafted “must-hit” clause (e.g. “indemnify, defend, and hold harmless” + “without limitation”) was passed to `scan_clause`. **Result**: It correctly triggered R003 and R001 → Scanner logic and parsing are fine.
  - **Diagnostic 2**: With `CONTRACT_SENTINEL_DEBUG_SCANNER=1`, the script prints `rules_text`, `clause_text`, and `graph_context` sent to the model. For a given section_9_1 run, **CLAUSE was empty** and graph context was the default message → the issue was **missing input data**, not the Scanner.

#### Issue 2: Empty clause_text in run_scanner_demo

- **Root cause**: Some clauses do not exist in Neo4j or their Clause node has no `text`. The structural pipeline uses **rule-based segmentation**; if the PDF does not contain a “Section 9.1” style heading, there is no section_9_1 in the graph, so `get_context_for_clause` returns empty `clause_text`.
- **Fix**: In `run_scanner_demo.py`, use `ctx.get("clause_text")` and print a **Warning** when it is empty (“clause may not exist in graph or has no text”). Document that Findings: 0 can be due to (1) **missing data** (empty clause_text) or (2) **rule not matched** (clause has text but does not match playbook).

#### Issue 3: Shell error “zsh: number expected” when passing contract ID

- **Symptom**: `python scripts/run_scanner_demo.py EX-10.4(a) section_9_1` failed in zsh.
- **Cause**: The parentheses in the contract ID `(a)` are special in zsh.
- **Fix**: Quote the contract ID: `python scripts/run_scanner_demo.py "EX-10.4(a)" section_9_1`. All examples in `docs/commands.md` were updated to use quoted contract IDs.

#### Issue 4: Sections with non-empty clause_text still returned 0 findings

- **Symptom**: e.g. section_5_1 had non-empty clause_text and graph_context in debug output but Findings: 0.
- **Conclusion**: That clause (e.g. Company Data definitions) does not contain the playbook keywords (indemnify, terminate, unlimited liability, etc.) → **rule not matched**, not a bug. This is distinct from “0 due to empty clause_text.”
- **Implementation**: Added `run_scanner_verifications.py`: category 1 uses a clause with text (e.g. section_5_1) to confirm “has text but 0 = rule not matched”; category 2 uses a clause missing from the graph to confirm “empty text = no data in graph.” Documented “current state summary” and “confirmed / not yet confirmed” in the docs.

### Full-contract scan and write-back to Neo4j

- **Done**:
  - `scripts/scan_all_clauses.py`: iterates over all clauses in the graph, runs `scan_clause` for each with non-empty text, aggregates (Clause, Rule, Risk Level, Evidence); prints a table and writes `out/scan_<contract_id>.tsv`.
  - **Write-back to Neo4j**: Creates `Rule` nodes (id, risk_level, description) and `Clause -[:TRIGGERS {evidence?}]-> Rule` edges; existing TRIGGERS for the contract are removed before each run so the Critic can read up-to-date findings.
- **Graph model**: `app/graph/models.py` extended with `LABEL_RULE` and `REL_TRIGGERS`.
- **Result**: One command scans the full contract and produces a Clause | Rule | Risk Level table and TSV; the graph stores which clauses trigger which rules for the Critic.

### Task 10: Critic agent

- **Done**: `app/agents/prompts.py` (CRITIC_SYSTEM, CRITIC_USER_TEMPLATE); `app/agents/critic.py` (`evaluate_finding(finding, clause_text, graph_context, rule_description)`). Calls the LLM with the scanner finding (clause_ref, rule_triggered, evidence_summary), full clause text, and graph context; returns `{ "justified": bool, "reason": str }`.
- **Demo**: `scripts/run_critic_demo.py` — runs Scanner on a clause, then runs Critic on each finding and prints justified/reason.
- **Result**: Downstream Evaluator can use Critic output to filter or weight findings.

### Task 11: Evaluator agent

- **Done**: `app/agents/prompts.py` (EVALUATOR_SYSTEM, EVALUATOR_USER_TEMPLATE); `app/agents/evaluator.py` (`evaluate_escalation(finding, critic_result, risk_level, clause_text)`). Takes Scanner finding + Critic result + rule risk level; returns `{ "escalation": "Acceptable" | "Suggest Revision" | "Escalate for Human Review", "fallback_language": str | None, "reason": str }`.
- **Demo**: `scripts/run_evaluator_demo.py` — runs Scanner → Critic → Evaluator on one clause and prints escalation, fallback_language, reason per finding.
- **Result**: Output aligns with risk_memo for API/frontend; ready for LangGraph orchestration (Task 12).

### Task 12: LangGraph multi-agent orchestration

- **Done**: `app/schemas/risk_memo.py` (Citation, RiskMemoItem, StructuredRiskMemo); `app/agents/graph.py` (ReviewState TypedDict, _process_node, build_review_graph, run_review). LangGraph StateGraph: one node "process" that either loads the next clause and runs Scanner or runs Critic + Evaluator on the next finding and appends a RiskMemoItem; conditional edge to self or END. `run_review(contract_id, clause_ids=None, rules=None, playbook_path=None)` returns StructuredRiskMemo.
- **Demo**: `scripts/run_review_graph_demo.py` — run_review then print items and JSON.
- **Result**: API/frontend can call run_review to get the full memo; pipeline is Scanner → Critic → Evaluator per clause.

---

## Current status summary

| Layer           | Status | Notes |
|-----------------|--------|--------|
| Structural      | ✅     | PDF → parse → rule-based segmentation + LLM extraction → cross-refs → Neo4j ingest; end-to-end working |
| Retrieval       | ✅     | Per-clause clause_text + graph_context; retrieval demo verified |
| Playbook        | ✅     | Multi-rule YAML load; used by Scanner |
| Scanner         | ✅     | Single-clause and full-contract scan; synthetic “must-hit” clause triggers findings; real-clause 0 explained by “empty text” vs “rule not matched” |
| Full-contract scan | ✅  | scan_all_clauses outputs TSV and writes TRIGGERS to Neo4j |
| Critic          | ✅     | `evaluate_finding`; uses clause + graph context to output justified/reason |
| Evaluator       | ✅     | `evaluate_escalation`; outputs escalation, fallback_language, reason |
| LangGraph       | ✅     | build_review_graph + run_review; outputs StructuredRiskMemo |
| API             | ✅     | Health, contracts (upload/demo), review; CORS + exception handling |
| Frontend        | ✅     | Next.js layout, RiskCard + EvidenceChain, i18n, full upload→review flow |
| Phase 6 (Evaluation) | ⏸️  | Skipped for now (benchmark / metrics / baselines not required for MVP) |
| Unit tests           | ✅  | tests/unit (parsing, extraction, graph, retrieval, agents); mocks for Neo4j/OpenAI |
| Integration test     | ✅  | tests/integration/test_review_pipeline.py (PDF→review→StructuredRiskMemo; skip if no Neo4j/OpenAI) |
| Deployment           | ✅  | Backend on Render; frontend on Vercel; Neo4j env-only (no silent fallback); see Phase 8 |

---

## Phase 4: Interface layer — API

### Task 13: API dependencies and health check

- **Done**: `app/api/deps.py` (`check_neo4j()`, `check_llm()`); `app/api/routes/health.py` — `GET /health` returns `{ status, neo4j, llm, ... }`, 503 when degraded.
- **Result**: One endpoint to verify Neo4j and LLM availability before running pipelines.

### Task 14: Contract upload and parse API

- **Done**: `app/pipeline/run_structural.py` (shared `run_structural_pipeline(path_or_bytes, contract_id)` used by script and API); `app/api/routes/contracts.py` — `POST /contracts/upload` (multipart PDF → pipeline → contract_id, status), `POST /contracts/demo` (same pipeline on built-in sample `EX-10.4(a).pdf`). Sample-based flow kept for MVP demo.
- **Note**: Rule-based segmenter is tuned for “Section X.Y” numbering; other PDFs still run but may get fewer rule-based clauses (LLM-only fallback). Documented in `docs/architecture.md` (Extraction pipeline scope).
- **Result**: Upload or demo returns `contract_id`; pipeline runs in thread pool to avoid blocking.

### Task 15: Review trigger and risk memo API

- **Done**: `app/api/routes/review.py` — `POST /review` (body: contract_id, optional playbook_id), `GET /review?contract_id=...&playbook_id=...`; both call `run_review(contract_id, playbook_path)` and return `StructuredRiskMemo`.
- **Result**: Frontend can trigger review and get risk items (clause, risk_level, rule_triggered, reason, escalation, citation, evidence_summary, etc.).

### Task 16: FastAPI app mount and startup

- **Done**: `app/main.py` — CORS middleware (`allow_origins=["*"]`), global exception handler (500 with JSON; `HTTPException` re-raised), routers for health, contracts, review. `uvicorn app.main:app --reload` runs the API.
- **Result**: Single entry point; `/health`, `/contracts/upload`, `/contracts/demo`, `/review` (GET/POST) available.

---

## Phase 5: Interface layer — Frontend

### Task 17: Frontend init and layout

- **Done**: Next.js 14 (App Router) under `frontend/` — package.json, tsconfig, next.config, Tailwind, PostCSS; `app/layout.tsx`, `app/page.tsx`. Two-column layout: left = contract/clause area, right = risk cards. Bilingual (zh/en) via `LocaleContext` + `LanguageSwitcher`; locale stored in localStorage.
- **Result**: `cd frontend && npm install && npm run dev` → http://localhost:3000 with left/right panels and language toggle.

### Task 18: Risk card and evidence chain components

- **Done**: `frontend/app/types/risk.ts` (RiskMemoItem, StructuredRiskMemo, Citation); `frontend/app/components/RiskCard.tsx` (displays clause, rule_triggered, risk_level, reason, fallback_language, escalation, citation, evidence_summary, justified, confidence; level styling; expandable evidence); `frontend/app/components/EvidenceChain.tsx` (shows citation + evidence_summary from API; no separate “referenced clauses/definitions” API yet). All labels wired to i18n.
- **Result**: Risk cards and evidence block render from `StructuredRiskMemo`; evidence uses existing API fields only.

### Task 19: Frontend–backend integration and review flow

- **Done**: `frontend/lib/api.ts` (uploadContract, demoContract, runReview; base URL from `NEXT_PUBLIC_API_URL`); page state (contractId, memo, uploading, reviewing, error, selectedClauseRef). Flow: upload PDF or “Use sample” → get contract_id → “Start review” → GET /review → render memo.items as RiskCards. Left panel: before contract = upload/demo UI; after contract = “Start review” button; after review = list of clause blocks (from memo, deduped by clause_ref). Clicking a risk card scrolls to and highlights the corresponding clause block on the left (smooth scroll + highlight).
- **Result**: Full flow works: upload or demo → parse (wait) → start review → review (wait) → left shows clauses, right shows risk cards; click card → left scrolls to and highlights that clause.

---

## Concrete process (current MVP flow)

1. **Backend**: `uvicorn app.main:app --reload` (default http://127.0.0.1:8000). Optional: set NEO4J_*, OPENAI_API_KEY in `.env`.
2. **Frontend**: `cd frontend && npm run dev` (default http://localhost:3000). Optional: `NEXT_PUBLIC_API_URL=http://localhost:8000`.
3. **User**: Open frontend → “Upload PDF” or “Use sample contract” → wait for parsing → “Start review” → wait for review → left panel shows clauses (from memo), right panel shows risk cards.
4. **User**: Click a risk card → left panel scrolls to and highlights the clause for that finding (by clause_ref / citation).
5. **API sequence**: POST /contracts/demo (or /contracts/upload) → GET /review?contract_id=EX-10.4(a) (or POST /review with body). Health: GET /health.

---

## Phase 7: Tests and documentation

### Task 23: Unit tests

- **Done**: `tests/unit/test_parsing.py`, `test_extraction.py`, `test_graph.py`, `test_retrieval.py`, `test_agents.py`; `tests/conftest.py` (fixtures: minimal PDF, sample text/clauses, mock Neo4j). Parsing: parse_pdf, strip_repeated_headers_footers. Extraction: segment_clauses, extract_cross_references, is_plausible_subsection_start. Graph: ingest_contract and get_clause_neighborhood with mocked driver. Retrieval: get_context_for_clause, build_graph_context with mocked get_clause_neighborhood. Agents: scan_clause, evaluate_finding, evaluate_escalation with mocked OpenAI.
- **Result**: `pytest tests/unit -v` runs 20 tests; no Neo4j/OpenAI required (mocks used).

### Task 24: Integration test

- **Done**: `tests/integration/test_review_pipeline.py` — uses sample PDF, runs run_structural_pipeline then run_review, asserts StructuredRiskMemo schema and item fields (clause, risk_level, rule_triggered, reason, escalation). Skips if NEO4J_PASSWORD or OPENAI_API_KEY not set; skips if ingest was skipped. Marked `@pytest.mark.integration`. `pytest.ini` registers the marker.
- **Result**: `pytest tests/integration -v` runs one test (~3 min with real Neo4j + OpenAI). E2E (Playwright/Cypress) left optional.

### Task 25: README and documentation

- **Done**: README.md updated with Getting started (install, env vars, run backend/frontend, run unit and integration tests); Tech stack (PyMuPDF, Next.js 14); Progress table (Phases 0–7, Phase 6 skipped). docs/commands.md already had unit and integration test commands.
- **Result**: New members can follow README to run the project and run tests; full phase detail in docs/PROGRESS.md.

---

## Script and command quick reference

- **Structural pipeline**: `python scripts/run_structural_pipeline.py "data/sample_contracts/EX-10.4(a).pdf"`
- **Graph retrieval**: `python scripts/run_retrieval_demo.py "EX-10.4(a)" section_1_1`
- **Scanner (single clause)**: `python scripts/run_scanner_demo.py "EX-10.4(a)" section_5_1`
- **Scanner (full contract)**: `python scripts/scan_all_clauses.py "EX-10.4(a)"`
- **Diagnostics**: `python scripts/run_scanner_diagnostic.py`; `python scripts/run_scanner_verifications.py "EX-10.4(a)"`
- **Critic (Task 10)**: `python scripts/run_critic_demo.py "EX-10.4(a)" section_5_1`
- **Evaluator (Task 11)**: `python scripts/run_evaluator_demo.py "EX-10.4(a)" section_7_2` (Scanner → Critic → Evaluator)
- **LangGraph (Task 12)**: `python scripts/run_review_graph_demo.py "EX-10.4(a)"` or `--clauses section_5_1 section_7_2`
- **API**: `uvicorn app.main:app --reload` → http://127.0.0.1:8000; `GET /health`, `POST /contracts/demo`, `GET /review?contract_id=EX-10.4(a)`
- **Frontend**: `cd frontend && npm run dev` → http://localhost:3000
- **Unit tests**: `python -m pytest tests/unit -v`
- **Integration test**: `python -m pytest tests/integration -v` (requires Neo4j + OPENAI_API_KEY)

More commands: [commands.md](commands.md).

---

## Phase 8: Production deployment and config hardening

### Task 26: Neo4j config fully environment-driven

- **Done**:
  - **app/config.py**: Removed hardcoded Neo4j defaults (`bolt://localhost:7687`, `neo4j`, `""`). Neo4j fields now default to empty string and a `@model_validator(mode="after")` (`require_neo4j_env`) validates that `neo4j_uri`, `neo4j_user`, `neo4j_password` are all non-empty; if any is missing, raises `ValueError` listing the missing env var names (e.g. `NEO4J_URI`, `NEO4J_PASSWORD`). Pydantic Settings still use `SettingsConfigDict(env_file=".env", ...)`; env names `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` map to fields.
  - **app/graph/client.py**: `get_driver()` uses only `get_settings().neo4j_uri/user/password`; removed redundant inline password check (validation at settings load is sufficient).
  - **tests/integration/test_review_pipeline.py**: `_integration_ready()` now checks `os.environ.get("NEO4J_URI")`, `NEO4J_USER`, `NEO4J_PASSWORD`, `OPENAI_API_KEY` to decide skip, so `get_settings()` is not called when Neo4j is not configured (avoids validation error in CI).
  - **.env.example** (repo root): Placeholders for `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `OPENAI_API_KEY`. **frontend/.env.example**: Placeholder for `NEXT_PUBLIC_API_URL`.
- **Result**: No silent fallback to localhost or empty password; app fails at startup with a clear error if Neo4j env vars are missing. Local dev uses `.env`; Render uses Render environment variables.

### Task 27: Backend deployed on Render

- **Done**: Backend API deployed as a Web Service on Render. Environment variables set in Render: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `OPENAI_API_KEY` (no secrets in code).
- **Issue**: Initial deploy returned `500` with `Neo.ClientError.Security.Unauthorized` — Neo4j authentication failure. Cause: incorrect or outdated credentials in Render (e.g. wrong URI format for Aura, or password reset in Aura not reflected in Render). Resolved by re-copying URI/user/password from Neo4j Aura “Connect” and updating Render env, then redeploying.
- **Debug**: Temporary startup logs in `app/main.py` printed `neo4j_uri`, `neo4j_user`, `neo4j_password_len` to verify what the server actually loaded; removed after confirming.

### Task 28: Frontend deployed on Vercel

- **Done**: Frontend (Next.js) deployed on Vercel. Project uses Root Directory `frontend`. Environment variable `NEXT_PUBLIC_API_URL` set to the Render backend URL (e.g. `https://contractsentinel.onrender.com`). Redeploy required after setting the var so the value is inlined at build time.
- **Issue**: After first deploy, “Use sample” / demo showed “fail to fetch” in risk memo area. Causes: (1) `NEXT_PUBLIC_API_URL` not set or not applied (build had baked-in `http://localhost:8000`); (2) or Render free-tier cold start (first request times out). Fix: Set `NEXT_PUBLIC_API_URL` in Vercel and redeploy (without cache); if cold start, retry after ~1 minute or wake backend with GET /health first.
- **Result**: Single frontend URL (e.g. `https://xxx.vercel.app`) gives full product; backend on Render; CORS already `allow_origins=["*"]`.

### Task 29: Frontend build fix (RiskCard TypeScript)

- **Done**: `frontend/app/components/RiskCard.tsx` — `riskLevelLabel(level, t)` caused type error: `t` from `useLocale()` expects specific translation keys, but parameter was typed as `(k: string) => string`. Fixed by narrowing to `t: (k: "riskLevelHigh" | "riskLevelLow" | "riskLevelMedium") => string`.
- **Result**: `npm run build` passes; frontend deploys successfully.

### Deployment process (production)

1. **Backend (Render)**: Create Web Service, connect repo, set Root Directory if monorepo; set env vars `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `OPENAI_API_KEY`. Build: `pip install -r requirements.txt`; Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
2. **Frontend (Vercel)**: Import repo, Root Directory `frontend`. Set `NEXT_PUBLIC_API_URL` to backend URL (no trailing slash). Deploy (redeploy after changing env so Next.js inlines the value).
3. **Neo4j (Aura)**: Use “Connect” for URI/user/password; Aura Free has no separate user management — those credentials are the only DB user. If password is reset in Aura, update Render env and redeploy.
4. **Docs**: `docs/deploy-frontend.md` describes Vercel and Render frontend deployment options; `frontend/.env.example` and root `.env.example` list required vars.
