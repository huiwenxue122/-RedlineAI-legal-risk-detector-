# ContractSentinel 开发任务列表

基于 README.md 与架构设计整理，按依赖顺序排列。每个任务包含：任务名称、要创建的文件、功能说明、输入输出。

---

## Phase 0：项目骨架与数据模型

### 任务 1：项目目录与依赖

| 项 | 内容 |
|----|------|
| **任务名称** | 项目目录与依赖 |
| **要创建的文件** | `app/__init__.py`、`app/main.py`（空或最小 FastAPI）、`app/config.py`、`requirements.txt`；各子包 `__init__.py`：`app/api/`、`app/schemas/`、`app/parsing/`、`app/extraction/`、`app/graph/`、`app/retrieval/`、`app/agents/`、`app/evaluation/`；`app/api/routes/` 目录 |
| **功能说明** | 搭建 Python 包结构，集中配置（Neo4j URI、LLM API key、模型名等），支持 `.env`；声明依赖（Marker、neo4j、LangGraph、FastAPI、openai 等）。 |
| **输入** | 无（或环境变量）。 |
| **输出** | 可 `import app` 的包结构；`config` 可提供 `get_settings()` 等；`pip install -r requirements.txt` 可安装依赖。 |

---

### 任务 2：合同与图谱数据模型（schemas）

| 项 | 内容 |
|----|------|
| **任务名称** | 合同与图谱数据模型（schemas） |
| **要创建的文件** | `app/schemas/__init__.py`、`app/schemas/contract.py`、`app/schemas/risk_memo.py`、`app/schemas/playbook.py`、`app/schemas/api_models.py` |
| **功能说明** | 定义 Pydantic 模型：合同结构（Definition、Clause、Party、Obligation、CrossReference、Contract）；风险备忘录（Citation、RiskLevel、Escalation、RiskMemoItem、StructuredRiskMemo）；Playbook 规则与风险等级枚举；API 请求/响应 DTO（上传响应、审查请求/响应）。 |
| **输入** | 无（纯类型定义）。 |
| **输出** | 可从 `app.schemas` 导入的模型，供 parsing、extraction、graph、agents、api 使用。 |

---

## Phase 1：结构层

### 任务 3：PDF 解析（Marker）

| 项 | 内容 |
|----|------|
| **任务名称** | PDF 解析（Marker） |
| **要创建的文件** | `app/parsing/__init__.py`、`app/parsing/pdf.py`、`app/parsing/blocks.py`（可选） |
| **功能说明** | 使用 Marker 将 PDF 转为版式感知的文本块；定义块类型（如 TextBlock：text、page、bbox 等）；对外提供 `parse_pdf(path_or_bytes) -> List[TextBlock]`（或带页码的文档结构）。 |
| **输入** | PDF 文件路径或 bytes。 |
| **输出** | 文本块列表，每块含内容、页码、可选版式信息，供 extraction 消费。 |

---

### 任务 4：法律实体与关系抽取（LLM）

| 项 | 内容 |
|----|------|
| **任务名称** | 法律实体与关系抽取（LLM） |
| **要创建的文件** | `app/extraction/__init__.py`、`app/extraction/prompts.py`、`app/extraction/entities.py`、`app/extraction/normalizer.py` |
| **功能说明** | 根据 parsing 输出的文本块，用 LLM 抽取定义、条款、当事方、义务、交叉引用；prompts 定义抽取指令与输出格式（如 JSON schema）；normalizer 统一 section id、引用格式等；输出与 schemas.contract 对齐。 |
| **输入** | `List[TextBlock]` 或拼接后的合同文本；可选 contract_id。 |
| **输出** | 结构化抽取结果（Definitions、Clauses、Parties、Obligations、CrossReferences），与 `schemas.contract` 一致，供 graph.ingest 使用。 |

---

### 任务 5：Neo4j 图存储与查询

| 项 | 内容 |
|----|------|
| **任务名称** | Neo4j 图存储与查询 |
| **要创建的文件** | `app/graph/__init__.py`、`app/graph/client.py`、`app/graph/models.py`、`app/graph/ingest.py`、`app/graph/query.py` |
| **功能说明** | client：Neo4j 连接与会话管理；models：节点/边类型与 schemas 对齐；ingest：将 extraction 结果写入图（节点：Clause、Definition、Party、Obligation；边：REFERENCES、DEFINES、OBLIGATION_OF 等）；query：按 clause_id/contract_id 取邻域、定义、引用链，返回图上下文结构。 |
| **输入** | **ingest**：extraction 输出 + contract_id。**query**：contract_id、clause_id（或 node_id）、可选深度/条数限制。 |
| **输出** | **ingest**：写入成功/失败或写入的节点与边数。**query**：邻域子图或序列化后的上下文（如相关条款文本、定义、引用列表）。 |

---

### 任务 6：结构层端到端串联

| 项 | 内容 |
|----|------|
| **任务名称** | 结构层端到端串联 |
| **要创建的文件** | `notebooks/01_pdf_to_graph.ipynb` 或 `scripts/run_structural_pipeline.py` |
| **功能说明** | 串联 PDF → parsing → extraction → graph.ingest；用 data/sample_contracts 中 1～2 份 PDF 跑通，验证图谱中可查到条款与引用关系。 |
| **输入** | 样本 PDF 路径。 |
| **输出** | 图中存在对应 contract 的节点与边；可人工或脚本查询验证。 |

---

## Phase 2：推理层 — 检索与 Playbook

### 任务 7：审查手册配置与加载

| 项 | 内容 |
|----|------|
| **任务名称** | 审查手册配置与加载 |
| **要创建的文件** | `data/playbooks/default.yaml`、`app/agents/playbook_loader.py`（或放在 `app/schemas`/单独模块） |
| **功能说明** | 在 default.yaml 中定义规则（id、描述、风险等级、匹配条件或关键词）；playbook_loader 读取并转为 schemas.playbook 中的结构，供 Scanner 使用。 |
| **输入** | Playbook 文件路径或已加载的配置。 |
| **输出** | 规则列表（Rule 或等价的 Pydantic 模型），含 rule_id、description、risk_level、criteria 等。 |

---

### 任务 8：图增强检索（RAG + Graph Context）

| 项 | 内容 |
|----|------|
| **任务名称** | 图增强检索（RAG + Graph Context） |
| **要创建的文件** | `app/retrieval/__init__.py`、`app/retrieval/graph_context.py`、`app/retrieval/chunking.py`（可选）、`app/retrieval/rag.py` |
| **功能说明** | graph_context：调用 graph.query 获取指定条款的定义与引用邻域，组装成一段「图上下文」文本；chunking：按条款/页分块（若做向量检索）；rag：对外接口，给定 contract_id、clause_id（或 query），返回「该条款文本 + 图上下文」或「多段相关文本 + 图上下文」。 |
| **输入** | contract_id；clause_id 或 query 文本；可选 top_k、深度。 |
| **输出** | 结构化的检索结果：`{ "clause_text": str, "graph_context": str, "snippets": [...] }` 或类似，供 agents 使用。 |
| **说明** | **snippets** currently contains only reference-based snippets (outgoing/incoming REFERENCES). For clauses without references, snippets may be empty even when graph_context includes definitions or obligations. |

---

## Phase 3：推理层 — 多智能体

### 任务 9：Scanner Agent

| 项 | 内容 |
|----|------|
| **任务名称** | Scanner Agent |
| **要创建的文件** | `app/agents/__init__.py`、`app/agents/prompts.py`（Scanner 部分）、`app/agents/scanner.py` |
| **功能说明** | 根据 Playbook 规则与条款文本（及可选图上下文），识别候选风险；输出每条候选：条款引用、触发的规则、初步证据描述。 |
| **输入** | 条款文本、图上下文（可选）、Playbook 规则列表。 |
| **输出** | 候选问题列表：`[{ "clause_ref": str, "rule_triggered": str, "evidence_summary": str }, ...]`，与后续 Critic/Evaluator 的输入格式对齐。 |

---

### 任务 10：Critic Agent

| 项 | 内容 |
|----|------|
| **任务名称** | Critic Agent |
| **要创建的文件** | `app/agents/prompts.py`（Critic 部分）、`app/agents/critic.py` |
| **功能说明** | 对 Scanner 的每条候选，结合条款原文、图上下文、交叉引用与定义，判断发现是否成立；输出支持/不支持及理由。 |
| **输入** | Scanner 单条输出、条款全文、图上下文。 |
| **输出** | `{ "justified": bool, "reason": str }` 或带置信度，供 Evaluator 使用。 |

---

### 任务 11：Evaluator Agent

| 项 | 内容 |
|----|------|
| **任务名称** | Evaluator Agent |
| **要创建的文件** | `app/agents/prompts.py`（Evaluator 部分）、`app/agents/evaluator.py` |
| **功能说明** | 根据 Critic 结论、策略严重度、条款歧义等，做出最终决策：Acceptable / Suggest Revision / Escalate for Human Review；可选输出 fallback_language（建议替代表述）。 |
| **输入** | Scanner 候选、Critic 结论、条款与上下文摘要。 |
| **输出** | `{ "escalation": Enum, "fallback_language": str | None, "reason": str }`，与 risk_memo 的 escalation、fallback_language 对齐。 |

---

### 任务 12：LangGraph 多智能体编排

| 项 | 内容 |
|----|------|
| **任务名称** | LangGraph 多智能体编排 |
| **要创建的文件** | `app/agents/graph.py` |
| **功能说明** | 用 LangGraph 定义图：对合同内每条条款（或经检索得到的候选条款）依次执行 Scanner → Critic → Evaluator；聚合结果为 StructuredRiskMemo（列表 of RiskMemoItem，每项含 clause、risk_level、rule_triggered、reason、fallback_language、escalation、citation）。 |
| **输入** | contract_id；可选 clause_ids 或「全部条款」；Playbook。 |
| **输出** | `StructuredRiskMemo`（与 schemas.risk_memo 一致），供 API 与前端展示。 |

---

## Phase 4：接口层 — API

### 任务 13：API 依赖与健康检查

| 项 | 内容 |
|----|------|
| **任务名称** | API 依赖与健康检查 |
| **要创建的文件** | `app/api/__init__.py`、`app/api/deps.py`、`app/api/routes/health.py` |
| **功能说明** | deps：公共依赖（如 get_neo4j、get_llm_client、get_graph_client）；health 路由：检查 Neo4j 与 LLM 可用性，返回 200/503。 |
| **输入** | 无（GET /health）。 |
| **输出** | JSON：`{ "status": "ok" | "degraded", "neo4j": bool, "llm": bool }` 或类似。 |

---

### 任务 14：合同上传与解析 API

| 项 | 内容 |
|----|------|
| **任务名称** | 合同上传与解析 API |
| **要创建的文件** | `app/api/routes/contracts.py` |
| **功能说明** | 接收 PDF 上传，调用 parsing → extraction → graph.ingest；返回 contract_id 与状态（解析中/成功/失败）；可异步或同步。 |
| **输入** | POST multipart：PDF 文件；可选 filename。 |
| **输出** | `{ "contract_id": str, "status": str }`；失败时返回错误信息。 |

---

### 任务 15：审查触发与风险备忘录 API

| 项 | 内容 |
|----|------|
| **任务名称** | 审查触发与风险备忘录 API |
| **要创建的文件** | `app/api/routes/review.py` |
| **功能说明** | 接收 contract_id，调用 agents 编排（LangGraph）与 retrieval；返回 StructuredRiskMemo JSON。 |
| **输入** | POST/GET：`contract_id`；可选 playbook_id。 |
| **输出** | `StructuredRiskMemo`（见 README 示例 JSON 结构），即风险项列表，每项含 clause、risk_level、rule_triggered、reason、fallback_language、escalation、citation。 |

---

### 任务 16：FastAPI 应用挂载与启动

| 项 | 内容 |
|----|------|
| **任务名称** | FastAPI 应用挂载与启动 |
| **要创建的文件** | `app/main.py`（完善） |
| **功能说明** | 挂载 routes（health、contracts、review）；配置 CORS、异常处理；提供 `uvicorn app.main:app` 可启动的入口。 |
| **输入** | HTTP 请求。 |
| **输出** | 可运行的 FastAPI 应用，对外提供 /health、上传、/review 等端点。 |

---

## Phase 5：接口层 — 前端

### 任务 17：前端项目初始化与布局

| 项 | 内容 |
|----|------|
| **任务名称** | 前端项目初始化与布局 |
| **要创建的文件** | `frontend/` 下 Next.js 项目（package.json、next.config、tsconfig 等）；`frontend/app/page.tsx`、`frontend/app/layout.tsx`；布局组件：左侧合同展示区、右侧卡片区。 |
| **功能说明** | 初始化 React/Next.js，实现证据导向审查布局：左侧占位合同/条款展示，右侧占位风险卡片列表。 |
| **输入** | 无。 |
| **输出** | 可 `npm run dev` 的页面，左右分栏布局。 |

---

### 任务 18：风险卡片与证据链组件

| 项 | 内容 |
|----|------|
| **任务名称** | 风险卡片与证据链组件 |
| **要创建的文件** | `frontend/components/RiskCard.tsx`、`frontend/components/EvidenceChain.tsx`（可选） |
| **功能说明** | RiskCard：展示单条风险（clause、rule_triggered、reason、fallback_language、escalation、citation）；EvidenceChain：展示引用到的条款/定义等证据链。 |
| **输入** | 单条 RiskMemoItem 或等效 props。 |
| **输出** | 渲染后的卡片与可展开的证据链。 |

---

### 任务 19：前后端对接与审查流程

| 项 | 内容 |
|----|------|
| **任务名称** | 前后端对接与审查流程 |
| **要创建的文件** | `frontend/lib/api.ts`（或 services）；上传与审查的页面逻辑；根据 citation 高亮/定位左侧条款。 |
| **功能说明** | 调用后端：上传 PDF → 轮询或等待解析完成 → 请求 /review → 将返回的 StructuredRiskMemo 渲染为右侧卡片列表；左侧根据 citation 高亮或滚动到对应条款。 |
| **输入** | 用户上传的 PDF；用户点击「开始审查」。 |
| **输出** | 左侧合同 + 右侧风险卡片列表；点击卡片可定位到对应条款。 |

---

## Phase 6：评估与基线

### 任务 20：基准数据与加载

| 项 | 内容 |
|----|------|
| **任务名称** | 基准数据与加载 |
| **要创建的文件** | `data/benchmark/contracts/`（占位或样本）、`data/benchmark/annotations.jsonl`（或 .json）；`app/evaluation/__init__.py`、`app/evaluation/dataset.py` |
| **功能说明** | 定义标注格式（合同 id、风险条款、期望升级、期望引用等）；dataset 加载 annotations 与合同元数据，返回标准化的 benchmark 样本列表。 |
| **输入** | 标注文件路径。 |
| **输出** | 结构化列表：`[{ "contract_id", "gold_risks", "gold_escalation", "gold_citations" }, ...]`。 |

---

### 任务 21：评估 Runner 与指标

| 项 | 内容 |
|----|------|
| **任务名称** | 评估 Runner 与指标 |
| **要创建的文件** | `app/evaluation/runner.py`、`app/evaluation/metrics.py` |
| **功能说明** | runner：对每条 benchmark 样本调用审查流水线（或 API），收集预测的 RiskMemo；metrics：计算风险条款召回率、标记精确率、引用准确率、升级准确率、简单幻觉率等。 |
| **输入** | **runner**：benchmark 样本列表。**metrics**：金标与预测的 RiskMemo 列表。 |
| **输出** | **runner**：每条样本的预测 RiskMemo。**metrics**：各指标标量或 per-sample 结果。 |

---

### 任务 22：基线对比（Chunk RAG / Graph RAG / Multi-Agent）

| 项 | 内容 |
|----|------|
| **任务名称** | 基线对比（Chunk RAG / Graph RAG / Multi-Agent） |
| **要创建的文件** | `app/evaluation/baselines.py`、`notebooks/02_evaluation.ipynb` 或脚本 |
| **功能说明** | 实现或配置三种模式：仅 Chunk RAG；Graph RAG（图上下文）+ 单轮 LLM；完整 Multi-Agent（Scanner+Critic+Evaluator）。在同一 benchmark 上跑 runner，用 metrics 汇总，输出对比表或图表。 |
| **输入** | benchmark 数据集。 |
| **输出** | 各基线及多智能体的指标表（如 README 中 Method vs Description 的扩展版：Method、Recall、Precision、Citation Acc、Escalation Acc 等）。 |

---

## Phase 7：测试与文档

### 任务 23：单元测试

| 项 | 内容 |
|----|------|
| **任务名称** | 单元测试 |
| **要创建的文件** | `tests/unit/test_parsing.py`、`tests/unit/test_extraction.py`、`tests/unit/test_graph.py`、`tests/unit/test_retrieval.py`、`tests/unit/test_agents.py`（或按模块拆分） |
| **功能说明** | 对 parsing、extraction、graph（ingest/query）、retrieval、agents 的关键函数做单测；使用 fixture 或 mock Neo4j/LLM 以保持可重复。 |
| **输入** | 各模块的输入 fixture（如样本 PDF、样本文本、样本图数据）。 |
| **输出** | pytest 可运行的测试，断言输出格式与关键行为。 |

---

### 任务 24：集成测试与 E2E

| 项 | 内容 |
|----|------|
| **任务名称** | 集成测试与 E2E |
| **要创建的文件** | `tests/integration/test_review_pipeline.py`；可选 E2E：Playwright 或 Cypress 测试前端上传→审查流程 |
| **功能说明** | 集成测试：用一份小合同跑通 PDF → 解析 → 图 → 审查 → StructuredRiskMemo，断言返回结构符合 schema。E2E（可选）：浏览器内上传 PDF、触发审查、检查卡片出现。 |
| **输入** | 固定的小 PDF 或 contract_id。 |
| **输出** | 集成测试通过；E2E 通过（若实现）。 |

---

### 任务 25：README 与文档更新

| 项 | 内容 |
|----|------|
| **任务名称** | README 与文档更新 |
| **要创建的文件** | 更新 `README.md`；可选 `docs/setup.md`、`docs/api.md` |
| **功能说明** | README 补充：安装步骤、环境变量、如何运行后端/前端、如何运行评估；文档中说明各模块职责与数据流（可引用 development-plan、todo-list）。 |
| **输入** | 无。 |
| **输出** | 新成员可按 README 跑通项目并理解架构。 |

---

## 任务顺序依赖简图

```
1 项目骨架
2 schemas
     ↓
3 parsing → 4 extraction → 5 graph → 6 结构层 E2E
     ↓
7 playbook  8 retrieval
     ↓
9 Scanner → 10 Critic → 11 Evaluator → 12 LangGraph
     ↓
13 deps+health  14 contracts API  15 review API  16 main
     ↓
17 前端布局  18 风险卡片  19 前后端对接
     ↓
20 benchmark 数据  21 runner+metrics  22 baselines
     ↓
23 单测  24 集成/E2E  25 文档
```

以上任务按顺序执行即可在最小返工下完成 ContractSentinel 从骨架到可演示、可评估的闭环。
