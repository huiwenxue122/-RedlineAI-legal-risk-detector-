# ContractSentinel

**Agentic Legal Risk Review System for Contract Escalation**

ContractSentinel is a LegalTech AI system that models contract review as a policy-driven reasoning workflow rather than a simple chatbot or summarization tool.

The system parses contracts into a graph-aware legal structure, runs a multi-agent reasoning pipeline, and produces a structured risk memo with evidence chains to support human legal review.

The goal is not to replace lawyers, but to help them identify risk, justify findings, and decide when escalation is required.

---

## System Architecture

![System Architecture](pics/mermaid-diagram.png)

ContractSentinel is built around three layers:

- **Structural Layer** – converts contracts into a structured legal graph
- **Reasoning Layer** – performs policy-driven multi-agent review
- **Interface Layer** – presents evidence and escalation recommendations

---

## Overview

Most AI contract tools focus on:

- summarization
- clause extraction
- legal Q&A

However, real contract review involves three harder problems:

### 1. Contracts are not linear

Risk often depends on:

- earlier definitions
- referenced clauses
- exceptions elsewhere in the agreement

**Example:** Section 8.2 – Termination *subject to* Section 4.1 – Limitation of Liability. Understanding this relationship requires cross-clause reasoning.

### 2. Risk is policy-dependent

A clause is risky only relative to:

- market standards
- company legal policy
- client preferences

ContractSentinel therefore evaluates contracts using a **Review Playbook**. Example rules:

- unlimited liability → High risk
- unilateral termination → High risk
- confidentiality > 5 years → Medium risk

### 3. Review is an escalation workflow

In real legal workflows:

- some issues are acceptable
- some require revision
- some require human legal review

ContractSentinel models this escalation process explicitly.

---

## Multi-Agent Reasoning Workflow

The reasoning layer uses LangGraph orchestration with three agents.

### Scanner Agent

Identifies candidate issues using the review playbook.

- **Example detections:** unlimited liability, broad data usage rights, unilateral termination, excessive confidentiality terms
- **Output:** flagged clause, triggered rule, supporting evidence

### Critic Agent

Evaluates whether the Scanner's claim is justified. It checks:

- linked clauses
- definitions
- cross-references
- contextual legal language

This step reduces shallow or unsupported findings.

### Evaluator Agent

Produces the final decision:

- **Acceptable**
- **Suggest Revision**
- **Escalate for Human Review**

**Decision factors:** policy severity, clause ambiguity, cross-clause dependency, evidence confidence.

---

## Example Output

The system generates a **Structured Risk Memo**. Example:

```json
{
  "clause": "The receiving party shall be liable for all damages without limitation.",
  "risk_level": "High",
  "rule_triggered": "Unlimited Liability",
  "reason": "Liability is not capped and may expose the party to unlimited damages.",
  "fallback_language": "Liability shall not exceed the total fees paid under this agreement.",
  "escalation": "Suggest Revision",
  "citation": {
    "section": "Section 7.3",
    "page": 12
  }
}
```

In the UI, each issue is presented as an evidence-based review card containing:

- clause text
- policy rule triggered
- reasoning
- fallback language
- escalation recommendation

---

## Tech Stack

| Area | Technologies |
|------|--------------|
| **Document Parsing** | PyMuPDF (PDF parsing), layout-aware text extraction |
| **Knowledge Graph** | Neo4j, LLM entity extraction, clause / definition / reference relationships |
| **Reasoning** | LangGraph orchestration, LLM agents (Scanner / Critic / Evaluator), RAG + graph context retrieval |
| **Backend** | FastAPI, Python |
| **Frontend** | Next.js 14 (App Router), React, TypeScript, Tailwind |
| **Evaluation** | Benchmark / metrics / baselines (Phase 6, optional for MVP) |

---

## Getting started

### 1. Clone and install

```bash
cd ContractSentinel
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment variables

Copy `.env.example` to `.env` and set:

- **OPENAI_API_KEY** — required for extraction and review (LLM).
- **NEO4J_URI**, **NEO4J_USER**, **NEO4J_PASSWORD** — required for graph ingest and review (Neo4j).

See `app/config.py` for all options. Without Neo4j, the pipeline still runs but ingest is skipped; review needs the graph.

### 3. Run backend

```bash
uvicorn app.main:app --reload
```

API: http://127.0.0.1:8000. Docs: http://127.0.0.1:8000/docs.

### 4. Run frontend

```bash
cd frontend && npm install && npm run dev
```

UI: http://localhost:3000. Use “Use sample contract” then “Start review” for the full demo.

### 5. Run tests

- **Unit tests** (no Neo4j/OpenAI needed for most; some use mocks):  
  `python -m pytest tests/unit -v`
- **Integration test** (requires Neo4j + OPENAI_API_KEY; ~3 min):  
  `python -m pytest tests/integration -v`  
  If env is not set, the integration test is skipped.

More commands: **[docs/commands.md](docs/commands.md)**. Module roles and data flow: **[docs/architecture.md](docs/architecture.md)**, **[docs/internal/todo-list.md](docs/internal/todo-list.md)**.

---

## Evaluation

To validate system behavior, the project includes a small contract review benchmark.

- **Dataset:** NDA contracts, MSA contracts. Annotated with: risky clauses, escalation labels, expected citations.
- **Metrics:** risk clause recall, precision on flagged clauses, cross-reference reasoning success, citation accuracy, escalation accuracy, hallucination rate.
- **Baseline comparison:**

| Method | Description |
|--------|-------------|
| Chunk RAG | traditional chunk retrieval |
| Graph RAG | retrieval with graph context |
| Multi-Agent | scanner + critic + evaluator |

---

## Progress / Milestones

Development is tracked in phases; each phase is documented with **what was done**, **main problems encountered**, and **how they were solved**.

| Phase | Status | Summary |
|-------|--------|---------|
| **Phase 0** | Done | Project skeleton, config, schemas (Contract, Clause, Playbook, RiskMemo). |
| **Phase 1** | Done | PDF parsing (PyMuPDF), rule-based clause segmentation, LLM extraction, cross-references, Neo4j ingest & query. End-to-end: PDF → graph. |
| **Phase 2** | Done | Playbook loading, graph-augmented retrieval (clause text + graph context per clause). |
| **Phase 3** | Done | Scanner, Critic, Evaluator; full-contract scan; LangGraph orchestration; StructuredRiskMemo. |
| **Phase 4** | Done | API: health, contracts (upload/demo), review; CORS and exception handling. |
| **Phase 5** | Done | Next.js frontend: two-column layout, RiskCard + EvidenceChain, i18n, full upload→review flow. |
| **Phase 6** | Skipped | Evaluation / benchmark / baselines (optional for MVP). |
| **Phase 7** | Done | Unit tests; integration test (PDF→review→StructuredRiskMemo). |

**Notable issues resolved:**

- **Scanner always returning 0 findings** — Root cause was sometimes empty `clause_text` (clause not in graph or no text stored). We added a diagnostic (synthetic “must-hit” clause) to confirm the Scanner works, and debug output to inspect inputs. We now distinguish “no data” (empty text) vs “rule not matched” (text present but no playbook match).
- **Shell error when passing contract ID** — Contract IDs with parentheses (e.g. `EX-10.4(a)`) must be quoted in zsh to avoid `number expected`.
- **Findings written back to graph** — Full-contract scan now creates `Rule` nodes and `Clause -[:TRIGGERS {evidence}]-> Rule` edges so the Critic can read them directly.

Full detail: **[docs/PROGRESS.md](docs/PROGRESS.md)**. Commands: **[docs/commands.md](docs/commands.md)**.

---

## Repository Structure

```
contractsentinel/
│
├── app/
│   ├── api/
│   ├── agents/
│   ├── parsing/
│   ├── extraction/
│   ├── graph/
│   ├── retrieval/
│   ├── evaluation/
│   └── schemas/
│
├── frontend/
│
├── data/
│   ├── sample_contracts/
│   ├── playbooks/
│   └── benchmark/
│
├── notebooks/
├── tests/
└── README.md
```
