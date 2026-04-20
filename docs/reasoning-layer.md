# RedlineAI 推理层技术文档

---

## 概览

推理层是系统的核心，负责把一份合同变成结构化风险报告。整体流程：

```
合同文本 (PDF)
    ↓ parsing + segmentation
条款列表 [Section 1.1, Section 2.3, ...]
    ↓ LangGraph 3-node graph
每条条款 → Scanner → Critic → Evaluator
    ↓
StructuredRiskMemo [{clause, risk_level, escalation, reason, fallback_language}]
```

推理层由三个文件构成：

| 文件 | 职责 |
|------|------|
| `app/agents/graph.py` | LangGraph 图结构、状态机、路由逻辑 |
| `app/agents/scanner.py` | Scanner Agent — 识别风险 |
| `app/agents/critic.py` | Critic Agent — 验证风险是否成立 |
| `app/agents/evaluator.py` | Evaluator Agent — 决定升级建议和修改语言 |
| `app/agents/prompts.py` | 三个 Agent 的 system / user prompt 模板 |
| `app/agents/playbook_loader.py` | 加载 YAML playbook → Rule 对象列表 |

---

## 一、LangGraph 状态机（graph.py）

### 1.1 图结构

```
START
  ↓
[scanner_node] ──── 找到 findings ────→ [critic_node]
     ↑                                        ↓
     │                               [evaluator_node]
     │                                        │
     │←── 这个 clause 的 findings 处理完 ───────┤
     │                                        │
     └────────────── 还有 findings ────────────┘
                                             ↓
                                           END（所有 clause 处理完）
```

用 LangGraph 的 `StateGraph` 实现，三个节点通过**条件路由**连接：

- `scanner` 有 findings → 去 `critic`
- `scanner` 无 findings → 回 `scanner`（加载下一条 clause）
- `scanner` 无更多 clause → `END`
- `critic` → 永远去 `evaluator`
- `evaluator` 当前 clause 还有剩余 findings → 回 `critic`
- `evaluator` clause 处理完 → 回 `scanner`（加载下一条）
- `evaluator` 所有 clause 处理完 → `END`

### 1.2 共享状态 ReviewState

```python
class ReviewState(TypedDict):
    contract_id: str
    clause_ids: List[str]          # 从 Neo4j 查出来的所有 clause ID
    rules_list: List[Dict]         # 序列化的 playbook 规则

    items: List[Dict]              # append-only，最终的风险报告条目

    clause_index: int              # 当前处理到第几个 clause
    clause_ctx: Dict               # 当前 clause 的文本 + 图上下文
    findings: List[Dict]           # 当前 clause 的 Scanner 输出
    finding_index: int             # 当前处理到第几个 finding

    current_finding: Dict          # 正在 Critic/Evaluator 处理的 finding
    critic_result: Dict            # Critic 的输出，传给 Evaluator
```

**关键设计：** `items` 字段用 `Annotated[List, operator.add]` 声明，LangGraph 会自动做列表追加而不是覆盖。其他字段每次节点返回时直接替换。

### 1.3 路由函数

```python
# scanner 执行后
def _route_after_scanner(state):
    if state["clause_index"] >= len(state["clause_ids"]):
        return "__end__"   # 没有更多 clause
    if state["findings"]:
        return "critic"    # 有 findings，去验证
    return "scanner"       # 无 findings，继续下一条

# evaluator 执行后
def _route_after_evaluator(state):
    if state["finding_index"] < len(state["findings"]):
        return "critic"    # 当前 clause 还有 findings 没处理
    if state["clause_index"] >= len(state["clause_ids"]):
        return "__end__"   # 全部处理完
    return "scanner"       # 进入下一条 clause
```

---

## 二、Scanner Agent（scanner.py）

### 2.1 职责

扫描**单条**条款文本，对照 playbook 规则，输出触发了哪些规则。

### 2.2 Keyword Pre-filter（关键词预筛选）

**这是 Scanner 的第一道关卡，在调用 LLM 之前执行。**

```python
def _keyword_filter(clause_text: str, rules: List[Rule]) -> List[Rule]:
    text_lower = clause_text.lower()
    matched = []
    for rule in rules:
        if not rule.keywords:          # 没有 keywords 的规则直接放行
            matched.append(rule)
            continue
        if any(kw.lower() in text_lower for kw in rule.keywords):
            matched.append(rule)       # 至少一个 keyword 命中才放行
    return matched
```

**位置：** `app/agents/scanner.py` → `_keyword_filter()` 函数，`scan_clause()` 内第一步调用。

**逻辑：**
1. 把条款文本转小写
2. 逐条规则检查，只要有一个 keyword 出现在文本里，这条规则就进入候选
3. 没有任何规则命中 → 直接返回 `[]`，**不发任何 API 请求**
4. 有命中规则 → 只把命中规则传给 LLM，未命中规则不出现在 prompt 里

**作用：** 实测过滤掉约 70-80% 的条款，大幅减少 OpenAI API 调用次数。

**Keywords 在哪里定义：** `data/playbooks/saas_customer.yaml`，每条规则的 `keywords` 字段：

```yaml
- rule_id: S001
  description: Unlimited or uncapped vendor liability
  keywords:
    - "liability"
    - "liable"
    - "consequential damages"
    - ...
```

### 2.3 Tool Calling — report_findings

通过关键词筛选后，向 OpenAI 发起 function calling 请求：

```python
REPORT_FINDINGS_TOOL = {
    "type": "function",
    "function": {
        "name": "report_findings",
        "parameters": {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "clause_ref":       {"type": "string"},
                            "rule_triggered":   {"type": "string"},
                            "evidence_summary": {"type": "string"},
                        },
                        "required": ["clause_ref", "rule_triggered", "evidence_summary"]
                    }
                }
            },
            "required": ["findings"]
        }
    }
}
```

调用方式：

```python
response = client.chat.completions.create(
    model=settings.openai_model,
    messages=[system_msg, user_msg],
    tools=[REPORT_FINDINGS_TOOL],
    tool_choice={"type": "function", "function": {"name": "report_findings"}},
    temperature=0.2,
)
data = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
findings = data["findings"]
```

**为什么用 tool calling 而不是 JSON mode：**
- `tool_choice="required"` 强制 LLM 必须调用这个 function，不会返回纯文本
- schema 里的 `required` 字段由 API 层面保证，不需要自己解析和验证
- 历史版本用的是 JSON mode + 正则提取，容易出 parse error

### 2.4 输入 prompt

```
System: 你是一个合同风险扫描器，为5-50人的SaaS公司审查客户合同...
User:
  - clause_ref: Section 9.4
  - clause_text: <条款原文>
  - graph_context: <Neo4j 查出来的 definitions/cross-refs>
  - rules_text: <只包含通过 keyword filter 的规则>
```

### 2.5 输出

```python
[
    {
        "clause_ref": "Section 9.4",
        "rule_triggered": "S001",
        "evidence_summary": "Clause exposes vendor to unlimited liability for all losses..."
    }
]
```

---

## 三、Critic Agent（critic.py）

### 3.1 职责

验证 Scanner 的 finding 是否真的成立。Scanner 是宽松扫描，Critic 是严格验证。

核心问题：**这条条款真的对供应商有害吗？还是有其他条款抵消了这个风险？**

### 3.2 Tool Calling — get_clause + submit_verdict

Critic 有**两个 tools**：

```
get_clause(section_id)   — 按需查询 Neo4j，拉取合同中另一条款的原文
submit_verdict(...)      — 提交最终判断，终止循环
```

**get_clause 的定义：**

```python
GET_CLAUSE_TOOL = {
    "function": {
        "name": "get_clause",
        "description": "Fetch the full text of a clause by its section identifier. "
                       "Call this when the clause references another section and you "
                       "need to read it to verify the risk.",
        "parameters": {
            "properties": {
                "section_id": {"type": "string"}  # e.g. "Section 4.2"
            }
        }
    }
}
```

**submit_verdict 的定义：**

```python
SUBMIT_VERDICT_TOOL = {
    "function": {
        "name": "submit_verdict",
        "parameters": {
            "properties": {
                "justified":  {"type": "boolean"},
                "reason":     {"type": "string"},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]}
            },
            "required": ["justified", "reason", "confidence"]
        }
    }
}
```

### 3.3 Tool-calling 循环

这是 Critic 最重要的设计——**多轮工具调用循环**：

```python
tools = [GET_CLAUSE_TOOL, SUBMIT_VERDICT_TOOL]
# 没有 contract_id 时只给 submit_verdict（无法查图）
if contract_id is None:
    tools = [SUBMIT_VERDICT_TOOL]

for _ in range(MAX_TOOL_ITERATIONS):   # 最多循环 4 次
    response = client.chat.completions.create(
        messages=messages,
        tools=tools,
        tool_choice="required",        # 强制每次必须调用工具
    )
    msg = response.choices[0].message
    messages.append(msg)               # 把 LLM 的 tool call 加入对话历史

    verdict_data = None
    for tc in (msg.tool_calls or []):
        if tc.function.name == "submit_verdict":
            verdict_data = json.loads(tc.function.arguments)
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": "Verdict recorded."})

        elif tc.function.name == "get_clause" and contract_id:
            args = json.loads(tc.function.arguments)
            fetched = _fetch_clause_text(contract_id, args["section_id"])
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": fetched})   # 把查到的条款文本还给 LLM

    if verdict_data is not None:
        break   # 收到 submit_verdict 就退出循环
```

**典型执行路径（cross-reference 场景）：**

```
Round 1:
  LLM 看到条款写 "subject to Section 4.2"
  → 调用 get_clause("Section 4.2")
  → 系统查 Neo4j，返回 Section 4.2 原文

Round 2:
  LLM 读完 Section 4.2，发现它限制了责任范围
  → 调用 submit_verdict(justified=false, reason="Section 4.2 caps liability at...", confidence="high")
  → 循环终止
```

**为什么需要这个循环：** 合同条款互相引用很常见，如果不去看 Section 4.2，Critic 可能误判一个实际上已经被限制的风险。

### 3.4 Neo4j 查询

```python
def _fetch_clause_text(contract_id: str, section_id: str) -> str:
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            "MATCH (c:Clause {contract_id: $cid}) "
            "WHERE c.section_id = $sid "
            "RETURN c.text AS text LIMIT 1",
            cid=contract_id, sid=section_id,
        )
        record = result.single()
        if record and record.get("text"):
            return f"[{section_id}]\n{record['text']}"
    return f"(Section '{section_id}' not found in this contract.)"
```

### 3.5 输出

```python
{
    "justified": True,
    "reason": "The liability clause has no monetary cap and carve-outs are broad.",
    "confidence": "high"
}
```

---

## 四、Evaluator Agent（evaluator.py）

### 4.1 职责

接收 Scanner finding + Critic verdict，输出**最终行动建议**：这个风险怎么处理？

### 4.2 Tool Calling — submit_escalation

```python
SUBMIT_ESCALATION_TOOL = {
    "function": {
        "name": "submit_escalation",
        "parameters": {
            "properties": {
                "escalation": {
                    "type": "string",
                    "enum": ["Acceptable",
                             "Suggest Revision",
                             "Escalate for Human Review"]
                },
                "reason": {"type": "string"},
                "fallback_language": {"type": ["string", "null"]}
            },
            "required": ["escalation", "reason", "fallback_language"]
        }
    }
}
```

**escalation 的三个值：**

| 值 | 含义 |
|----|------|
| `Acceptable` | 风险低或市场标准，可以直接签 |
| `Suggest Revision` | 有风险，应向客户法务提出修改要求 |
| `Escalate for Human Review` | 签之前必须让律师或高级决策人审查 |

**enum 约束由 API schema 强制**，LLM 不可能输出这三个值以外的内容。

### 4.3 调用方式（单次，非循环）

Evaluator 只调一次 LLM，不需要循环：

```python
response = client.chat.completions.create(
    model=settings.openai_model,
    messages=[system_msg, user_msg],
    tools=[SUBMIT_ESCALATION_TOOL],
    tool_choice={"type": "function", "function": {"name": "submit_escalation"}},
    temperature=0.2,
)
data = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
```

### 4.4 输出

```python
{
    "escalation": "Suggest Revision",
    "reason": "The liability cap is set at one month of fees. If a data incident occurs, "
              "your customer could claim losses far exceeding this, leaving you exposed.",
    "fallback_language": "Can we align the liability cap to 12 months of fees paid? "
                         "Happy to discuss alternatives."
}
```

---

## 五、Prompt 设计（prompts.py）

所有 prompt 都嵌入了相同的 ICP 上下文（5–50 人 SaaS 公司，无内部法务）：

### Scanner system prompt 核心

```
You are a contract risk scanner for a small SaaS company reviewing a customer
contract before signing. The company is the vendor — the one providing the
software or service. The team is 5–50 people with no in-house legal counsel.

Flag a clause only when there is a clear, concrete match to a rule.
Do not flag standard boilerplate that poses no realistic risk.
```

### Critic system prompt 核心

```
You are a contract review critic. Be skeptical. Ask: does this clause actually
create the harm the scanner identified, or does the surrounding context reduce
or eliminate it?

You have a tool: get_clause(section_id). If the clause references another
section, call get_clause to read that section before deciding.
Do not assume what a cross-referenced clause says — look it up.
```

### Evaluator system prompt 核心

```
Choose one escalation:
  "Acceptable" — risk is low or market-standard; fine to sign as-is.
  "Suggest Revision" — clause is risky; vendor should push back.
  "Escalate for Human Review" — do not sign until a lawyer reviews this.

Your "reason" must be in plain English: what is the concrete risk to this
company, and why does it matter in practice.

Your "fallback_language" should be a short replacement clause OR a 1–2
sentence email line — practical negotiation language, not verbose legal prose.
```

---

## 六、数据流全图

```
PDF 上传
  ↓
PyMuPDF 解析 → 全文文本
  ↓
clause_segmenter.py → 按 heading 切分 → [Clause 对象列表]
  ↓
Neo4j ingest → 写入 Clause 节点 + CrossReference 关系
  ↓
run_review(contract_id) 调用
  ↓
_get_clause_ids() → 从 Neo4j 查出所有 clause ID

━━━ LangGraph loop ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  对每个 clause_id：
    scanner_node:
      get_context_for_clause()  ← 从 Neo4j 查 clause text + definitions + cross-refs
      keyword_filter()          ← 无 keyword 命中 → 跳过（0 API 调用）
      OpenAI tool call          ← report_findings
      → findings: [{clause_ref, rule_triggered, evidence_summary}]

    对每个 finding：
      critic_node:
        OpenAI tool call loop   ← get_clause() × N 次（查 cross-ref）
                                ← submit_verdict()（终止循环）
        → {justified, reason, confidence}

      evaluator_node:
        OpenAI tool call        ← submit_escalation()
        → {escalation, reason, fallback_language}
        → 追加到 items[]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

StructuredRiskMemo → API → 前端展示
```

---

## 七、关键设计决策汇总

| 决策 | 原因 |
|------|------|
| **Keyword filter 放在 LLM 之前** | 70-80% 的条款无关，直接跳过省 API 费用 |
| **Scanner 用 tool calling 而不是 JSON mode** | schema 强制，不需要自己解析 JSON，不会出 parse error |
| **Critic 用工具调用循环** | 合同有 cross-reference，不查就无法准确判断风险 |
| **Critic 有 MAX_TOOL_ITERATIONS=4 上限** | 防止 LLM 无限循环调用 get_clause |
| **tool_choice="required"（Critic）** | 强制每轮必须调用工具，不会返回纯文本导致循环提前终止 |
| **Evaluator 只调一次（非循环）** | 不需要查图，输入信息已完整 |
| **enum 约束在 escalation 字段** | 防止 LLM 输出 "Escalate" 等变体，前端不需要做 normalize |
| **temperature=0.2（三个 agent）** | 低温确保输出稳定，合同审查不需要创意 |
| **LangGraph StateGraph** | 状态在节点间共享，路由逻辑清晰，容易 debug 和扩展 |

---

## 八、相关文件索引

```
app/agents/
├── graph.py            ← LangGraph 图结构（看这里理解整体流程）
├── scanner.py          ← keyword_filter + report_findings tool
├── critic.py           ← get_clause + submit_verdict tool + 循环
├── evaluator.py        ← submit_escalation tool
├── prompts.py          ← 所有 prompt 模板
└── playbook_loader.py  ← 加载 saas_customer.yaml

data/playbooks/
└── saas_customer.yaml  ← 10 条规则，含 keywords + criteria

app/retrieval/          ← get_context_for_clause（给 Scanner 提供图上下文）
app/graph/
├── client.py           ← Neo4j driver
├── ingest.py           ← 写入 Clause 节点
└── query.py            ← 查询 clause + neighborhood
```
