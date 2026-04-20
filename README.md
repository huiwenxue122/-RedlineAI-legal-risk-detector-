# RedlineAI

**AI Contract Risk Review for SaaS Companies**

**Demo Presentation:** **[(https://youtu.be/N8oIo9SzWBE)](https://youtu.be/N8oIo9SzWBE)**

**Project Presentation:** **[Google Drive](https://drive.google.com/file/d/1iCuXRGiC6RnLPyQMvN24fN3yDGiyxVn7/view?usp=sharing)**

**Live demo:** **[https://contract-sentinel.vercel.app/](https://contract-sentinel.vercel.app/)** — upload a contract or use the sample to run the full review in the browser.

> ⚠️ The backend is hosted on Render free tier and may cold-start after inactivity. If the first request fails, wait a few seconds and try again.

---

## What it does

RedlineAI helps small SaaS companies (5–50 people, no in-house legal) review customer contracts before signing.

**The problem:** founders, sales leads, and ops teams sign MSAs and order forms every week. They have no dedicated legal counsel, but signing the wrong clause — an uncapped liability exposure, a one-sided indemnity, a 90-day payment term — creates real financial and operational risk.

**RedlineAI flags the clauses that can hurt you**, explains the risk in plain English, and suggests what to say to the customer's legal team.

The system models contract review as a **policy-driven reasoning workflow** — not summarization, not Q&A. It parses contracts into a graph-aware legal structure, runs a three-agent reasoning pipeline, and produces a structured risk memo with evidence chains.

---

## System Architecture

![System Architecture](pics/mermaid-diagram.png)

RedlineAI is built around three layers:

- **Structural Layer** – converts contracts into a structured legal graph
- **Reasoning Layer** – performs policy-driven multi-agent review
- **Interface Layer** – presents evidence and escalation recommendations

---

## Why not just use a chatbot?

Most AI contract tools focus on summarization, clause extraction, or ad hoc Q&A. Real contract review is harder:

**1. Contracts are not linear**
Risk often depends on earlier definitions, referenced clauses, and exceptions elsewhere in the agreement. A termination clause might say "subject to Section 4.1" — you need to read Section 4.1 to know if the risk is real.

**2. Risk is policy-dependent**
A clause is risky only relative to your company's acceptable terms. RedlineAI uses a **Review Playbook** — a structured set of rules tuned for SaaS vendor contracts:

| Category | What we flag |
|----------|-------------|
| **Liability** | Uncapped liability, asymmetric liability cap |
| **Indemnity** | One-sided indemnity, overbroad indemnity scope |
| **Payment Terms** | Net 60 / Net 90, weak late-payment recourse |
| **Termination** | Lock-in / minimum commitment, no vendor exit right |
| **Auto-renewal** | Hidden renewal, notice period ≥ 90 days |

**3. Review is an escalation workflow**
Not every issue has the same response. Some clauses are fine to sign. Some need a push-back email. Some need a lawyer. RedlineAI models this explicitly.

---

## Multi-Agent Reasoning Workflow

The reasoning layer uses **LangGraph** to orchestrate three agents in a proper directed graph:

```
START → scanner → critic → evaluator → (more findings?) → critic
                ↑                    → (next clause?) → scanner
                └────────────────────────────────────────────────┘
```

### Scanner Agent

Identifies candidate risks using the playbook rules.

- **Keyword pre-filter:** runs before any LLM call — if no playbook keyword matches the clause text, the clause is skipped with no API call. In practice this filters ~70–80% of clauses before they reach the LLM.
- **Output:** flagged clause, triggered rule id, evidence summary
- **Uses:** `report_findings` tool (OpenAI function calling — schema-enforced output)

### Critic Agent

Validates whether the Scanner's finding is actually supported.

- **Dynamic cross-reference lookup:** when a clause says "subject to Section 4.2", the Critic calls `get_clause("Section 4.2")` to fetch and read that section from Neo4j before deciding. It does not assume what cross-referenced clauses say.
- **Output:** justified (true/false), reason, confidence
- **Uses:** `get_clause` tool (Neo4j query) + `submit_verdict` tool (structured output)

### Evaluator Agent

Produces the final decision for non-lawyers.

- **Escalation:** Acceptable / Suggest Revision / Escalate for Human Review
- **Reason:** plain English — what the risk is and why it matters in practice
- **Fallback language:** a short clause revision or email line the vendor can send to the customer's legal team
- **Uses:** `submit_escalation` tool (enum-constrained output)

---

## Example Output

```json
{
  "clause": "Vendor's aggregate liability shall not exceed fees paid in the prior one (1) month.",
  "risk_level": "High",
  "rule_triggered": "S002",
  "reason": "The liability cap is set at one month of fees — if something goes wrong, the customer could claim losses far exceeding what you'd owe them, leaving you exposed. This is well below market standard (typically 12 months of fees).",
  "fallback_language": "Can we align the liability cap to 12 months of fees paid rather than one month? Happy to discuss.",
  "escalation": "Suggest Revision",
  "citation": { "section": "Section 9.1", "page": null }
}
```

---

## Tech Stack

| Area | Technologies |
|------|--------------|
| **Document Parsing** | PyMuPDF, layout-aware text extraction, multi-pattern clause segmenter (7 heading formats auto-detected) |
| **Knowledge Graph** | Neo4j (Aura), LLM entity extraction, clause / definition / cross-reference relationships |
| **Reasoning** | LangGraph (3-node directed graph), OpenAI function calling (tool use), RAG + graph context retrieval |
| **Backend** | FastAPI, Python |
| **Frontend** | Next.js 14 (App Router), React, TypeScript, Tailwind |

---

## Getting Started

### 1. Clone and install

```bash
git clone https://github.com/huiwenxue122/-RedlineAI-legal-risk-detector-.git
cd -RedlineAI-legal-risk-detector-
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment variables

Copy `.env.example` to `.env` and set:

- **NEO4J_URI**, **NEO4J_USER**, **NEO4J_PASSWORD** — required for graph ingest and review. The app will not start if any of these are missing.
- **OPENAI_API_KEY** — required for extraction and review.

For the frontend: `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000`). See `frontend/.env.example`.

### 3. Run backend

```bash
uvicorn app.main:app --reload
```

API: http://127.0.0.1:8000 · Docs: http://127.0.0.1:8000/docs

### 4. Run frontend

```bash
cd frontend && npm install && npm run dev
```

UI: http://localhost:3000

### 5. Run tests

```bash
# Unit tests (no Neo4j / OpenAI required for most)
python -m pytest tests/unit -v

# Integration test (requires Neo4j + OPENAI_API_KEY, ~3 min)
python -m pytest tests/integration -v
```

---

## Deployment

- **Frontend:** Vercel — set `NEXT_PUBLIC_API_URL` at build time
- **Backend:** Render (Web Service) — set all four env vars in the Render dashboard
- **Graph:** Neo4j Aura (free tier works for demo)

Step-by-step: [docs/deploy-frontend.md](docs/deploy-frontend.md)

---

## Evaluation Design

RedlineAI is evaluated across three levels:

**Component-level**
- Scanner: Precision and Recall on labeled clauses (legal recall prioritized — a missed liability clause costs more than a false positive)
- Critic: false-positive filter rate; verdict accuracy with vs. without `get_clause` tool
- Evaluator: escalation agreement with human expert labels; fallback language quality (LLM-as-judge)

**End-to-end**
- Small benchmark built from [CUAD](https://www.atticusprojectai.org/cuad/) (510 expert-annotated commercial contracts, CC BY 4.0) and SEC EDGAR SaaS agreements
- Metrics: risk clause recall, escalation accuracy, cross-reference reasoning success, hallucination rate

**Ablation study**

| Configuration | What it measures |
|---------------|-----------------|
| Keyword-only baseline | Value of LLM over rule matching |
| + Scanner LLM | LLM detection quality |
| + Critic (no tool) | Value of validation layer |
| + get_clause tool | Value of dynamic cross-reference lookup |
| Full pipeline | End-to-end system quality |

---

## Repository Structure

```
RedlineAI/
│
├── app/
│   ├── api/              # FastAPI routes (health, contracts, review)
│   ├── agents/           # Scanner, Critic, Evaluator + LangGraph orchestration
│   ├── parsing/          # PDF parsing (PyMuPDF)
│   ├── extraction/       # Clause segmenter, LLM entity extraction, cross-refs
│   ├── graph/            # Neo4j client, ingest, query
│   ├── retrieval/        # RAG + graph context retrieval
│   └── schemas/          # Contract, Clause, Playbook, RiskMemo
│
├── frontend/             # Next.js 14 review UI
│
├── data/
│   ├── playbooks/        # saas_customer.yaml (active), default.yaml (general)
│   ├── sample_contracts/
│   └── benchmark/
│
├── tests/
│   ├── unit/
│   └── integration/
│
└── docs/
```
