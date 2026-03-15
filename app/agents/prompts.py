"""
Agent prompts: Scanner (Task 9), and later Critic / Evaluator.
Placeholders: {clause_ref}, {clause_text}, {graph_context}, {rules_text}. Literal braces: {{ }}.
"""
SCANNER_SYSTEM = """You are a contract risk scanner. Given a clause and a list of review rules, identify which rules (if any) are potentially triggered by this clause. For each match, output the rule id, a short evidence summary, and the clause reference. Return only valid JSON, no commentary."""

SCANNER_USER_TEMPLATE = """Clause reference: {clause_ref}

Clause text:
{clause_text}

Graph context (definitions, obligations, cross-references for this clause):
{graph_context}

Review rules to check:
{rules_text}

For each rule that appears to be triggered by this clause, output one finding with: "clause_ref" (the clause reference above), "rule_triggered" (rule id, e.g. R001), "evidence_summary" (1-2 sentences citing the relevant language). If no rules are triggered, output an empty list.

Return JSON in this shape only:
{{ "findings": [
  {{ "clause_ref": "...", "rule_triggered": "R001", "evidence_summary": "..." }},
  ...
] }}"""
