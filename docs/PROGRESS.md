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
| LangGraph       | ⏳     | Not implemented |
| API / Frontend  | ⏳     | Stub only; review flow not wired |

---

## Script and command quick reference

- **Structural pipeline**: `python scripts/run_structural_pipeline.py "data/sample_contracts/EX-10.4(a).pdf"`
- **Graph retrieval**: `python scripts/run_retrieval_demo.py "EX-10.4(a)" section_1_1`
- **Scanner (single clause)**: `python scripts/run_scanner_demo.py "EX-10.4(a)" section_5_1`
- **Scanner (full contract)**: `python scripts/scan_all_clauses.py "EX-10.4(a)"`
- **Diagnostics**: `python scripts/run_scanner_diagnostic.py`; `python scripts/run_scanner_verifications.py "EX-10.4(a)"`
- **Critic (Task 10)**: `python scripts/run_critic_demo.py "EX-10.4(a)" section_5_1`
- **Evaluator (Task 11)**: `python scripts/run_evaluator_demo.py "EX-10.4(a)" section_7_2` (Scanner → Critic → Evaluator)

More commands: [commands.md](commands.md).
