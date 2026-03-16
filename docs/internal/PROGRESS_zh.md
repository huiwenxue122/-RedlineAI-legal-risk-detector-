# ContractSentinel — Progress & Milestones（中文，仅供本人查阅）

本文档记录项目各阶段完成情况、遇到的主要问题与解决方法、以及结果。便于复盘与展示开发过程。

---

## Phase 0：项目骨架与数据模型

### 完成内容

- 项目目录与依赖：`app/` 包结构、`app/config.py`（含 `get_settings()`、`.env` 支持）、`requirements.txt`；子包 `parsing`、`extraction`、`graph`、`retrieval`、`agents`、`schemas`、`api`、`evaluation` 的 `__init__.py`。
- 数据模型：`app/schemas/contract.py`（Clause、Definition、Party、Obligation、CrossReference、Contract）、`app/schemas/playbook.py`（Rule、RiskLevel）、`app/schemas/risk_memo.py`、`app/schemas/api_models.py`。

### 结果

- 可 `import app`，`get_settings()` 可读取 NEO4J_*、OPENAI_API_KEY、openai_model 等；依赖可通过 `pip install -r requirements.txt` 安装。

---

## Phase 1：结构层

### 任务 3：PDF 解析（Marker）

- **完成**：`app/parsing/`，使用 Marker 将 PDF 转为版式感知文本块，对外 `parse_pdf(path) -> (full_text, blocks)`。
- **结果**：样本 PDF（如 `EX-10.4(a).pdf`）可解析出完整文本与分页块。

### 任务 4：法律实体与关系抽取（LLM）

- **完成**：`app/extraction/prompts.py`、`app/extraction/entities.py`（`extract_contract` 单次 LLM 调用抽取 clauses、definitions、parties、obligations、cross_references）；`app/extraction/clause_segmenter.py`（规则分段：按 Section X.Y 正则匹配）；`app/extraction/cross_references.py`（规则解析交叉引用，生成 CrossReference 列表）。
- **流程**：结构层管道采用「规则分段优先」：先 `segment_clauses(full_text)` 得到 rule-based clauses，再 LLM 抽取；若规则分段有结果，则用其覆盖 LLM 的 clauses，再对 clauses 做交叉引用抽取。
- **结果**：输出与 `schemas.contract` 一致，可供 ingest 使用。

### 任务 5：Neo4j 图存储与查询

- **完成**：`app/graph/client.py`、`app/graph/models.py`（节点/边常量）、`app/graph/ingest.py`（Contract → Clause、Definition、Party、Obligation 及 HAS_CLAUSE、DEFINES、HAS_OBLIGATION、HAS_PARTY、REFERENCES）、`app/graph/query.py`（`get_clause_neighborhood`：某 clause 的 text、section_id、references_in/out、definitions、obligations）。
- **结果**：抽取结果可写入 Neo4j；按 contract_id、clause_id 可查询条款邻域。

### 任务 6：结构层端到端串联

- **完成**：`scripts/run_structural_pipeline.py`（PDF → parse → segment_clauses → extract_contract → extract_cross_references → ingest_contract）；`scripts/verify_extraction.py`（仅 LLM 抽取并导出 `out/contract_<stem>.json`）。
- **结果**：一条命令跑通「PDF → 规则分段 → LLM 抽取 → 交叉引用 → Neo4j 写入」；图中可查到条款与引用关系。

---

## Phase 2：推理层 — 检索与 Playbook

### 任务 7：审查手册配置与加载

- **完成**：`data/playbooks/default.yaml`（多条规则：R001 无限责任、R002 单方终止、R003 宽泛赔偿、R004 数据使用、R005 IP 归属、R006 单方修订等，含 keywords、criteria、risk_level）；`app/agents/playbook_loader.py`（YAML → List[Rule]）。
- **结果**：Scanner 可加载 playbook 规则列表。

### 任务 8：图增强检索（RAG + Graph Context）

- **完成**：`app/retrieval/graph_context.py`（`build_graph_context`：从 get_clause_neighborhood 取 definitions、obligations、references 拼成一段文本）；`app/retrieval/rag.py`（`get_context_for_clause`：返回 `clause_text`、`section_id`、`graph_context`、`snippets`）；`scripts/run_retrieval_demo.py`（随机或指定 contract_id/clause_id 打印 clause_text、graph_context、snippets）。
- **结果**：给定 contract_id、clause_id，可拿到该条款全文与图上下文，供 Scanner 使用。

---

## Phase 3：推理层 — Scanner Agent 与全合同扫描

### 任务 9：Scanner Agent

- **完成**：`app/agents/prompts.py`（SCANNER_SYSTEM、SCANNER_USER_TEMPLATE）；`app/agents/scanner.py`（`scan_clause(...)`，调用 OpenAI JSON mode，解析 findings）；`scripts/run_scanner_demo.py`（从图取随机或指定 clause，调 get_context_for_clause → scan_clause，打印 findings）。

#### 主要问题 1：随机跑多个 section 时 Findings 始终为 0

- **排查**：诊断 1 人工必中条款能命中 R003/R001 → Scanner 正常。诊断 2 发现 CLAUSE 为空 → 问题在数据未传入。
- **主要问题 2**：部分 clause 在 Neo4j 不存在或未存 text，导致 clause_text 为空；demo 加 Warning，区分数据缺失 vs 规则未命中。
- **主要问题 3**：合同 ID 含括号导致 zsh 报错 → 加引号。
- **主要问题 4**：有 text 的 section 仍 0 → 属规则未命中；加验证脚本区分两类 0。

### 全合同扫描与写回 Neo4j

- **完成**：`scripts/scan_all_clauses.py`；Clause -[:TRIGGERS]-> Rule 写回图；图模型增加 LABEL_RULE、REL_TRIGGERS。

---

## Phase 4：接口层 — API

### 任务 13：API 依赖与健康检查

- **完成**：`app/api/deps.py`（`check_neo4j()`、`check_llm()`）；`app/api/routes/health.py` — `GET /health` 返回 `{ status, neo4j, llm, ... }`，degraded 时返回 503。
- **结果**：一个端点即可检查 Neo4j 与 LLM 是否可用。

### 任务 14：合同上传与解析 API

- **完成**：`app/pipeline/run_structural.py`（共享的 `run_structural_pipeline(path_or_bytes, contract_id)`，供脚本与 API 使用）；`app/api/routes/contracts.py` — `POST /contracts/upload`（multipart PDF → pipeline → contract_id、status），`POST /contracts/demo`（对内置样本 EX-10.4(a).pdf 跑同一 pipeline）。样本数据流保留，供 MVP 演示。
- **说明**：规则分段器针对「Section X.Y」编号优化；其他 PDF 仍可跑，但可能得到较少规则分段条款（退化为仅 LLM）。已在 `docs/architecture.md` 中记录（Extraction pipeline scope）。
- **结果**：上传或 demo 返回 contract_id；pipeline 在线程池中执行，避免阻塞。

### 任务 15：审查触发与风险备忘录 API

- **完成**：`app/api/routes/review.py` — `POST /review`（body：contract_id，可选 playbook_id），`GET /review?contract_id=...&playbook_id=...`；均调用 `run_review(contract_id, playbook_path)` 并返回 `StructuredRiskMemo`。
- **结果**：前端可触发审查并拿到风险项（clause、risk_level、rule_triggered、reason、escalation、citation、evidence_summary 等）。

### 任务 16：FastAPI 应用挂载与启动

- **完成**：`app/main.py` — CORS 中间件、全局异常处理（500 返回 JSON；HTTPException 原样抛出），挂载 health、contracts、review 路由。`uvicorn app.main:app --reload` 启动 API。
- **结果**：单一入口；`/health`、`/contracts/upload`、`/contracts/demo`、`/review`（GET/POST）可用。

---

## Phase 5：接口层 — 前端

### 任务 17：前端项目初始化与布局

- **完成**：在 `frontend/` 下搭建 Next.js 14（App Router）— package.json、tsconfig、next.config、Tailwind、PostCSS；`app/layout.tsx`、`app/page.tsx`。左右分栏：左侧合同/条款区，右侧风险卡片区。中英文双语：LocaleContext + LanguageSwitcher，语言选择存 localStorage。
- **结果**：`cd frontend && npm install && npm run dev` → http://localhost:3000，左右分栏 + 语言切换。

### 任务 18：风险卡片与证据链组件

- **完成**：`frontend/app/types/risk.ts`（RiskMemoItem、StructuredRiskMemo、Citation）；`frontend/app/components/RiskCard.tsx`（展示 clause、rule_triggered、risk_level、reason、fallback_language、escalation、citation、evidence_summary、justified、confidence；等级样式；可展开证据）；`frontend/app/components/EvidenceChain.tsx`（展示 API 的 citation + evidence_summary；暂无单独「引用条款/定义」接口）。文案接 i18n。
- **结果**：风险卡片与证据块由 `StructuredRiskMemo` 渲染；证据仅用现有 API 字段。

### 任务 19：前后端对接与审查流程

- **完成**：`frontend/lib/api.ts`（uploadContract、demoContract、runReview；base URL 用 `NEXT_PUBLIC_API_URL`）；页面状态（contractId、memo、uploading、reviewing、error、selectedClauseRef）。流程：上传 PDF 或「使用样本合同」→ 获得 contract_id →「开始审查」→ GET /review → 将 memo.items 渲染为 RiskCard。左侧：无合同时为上传/demo 区；有合同未审查时为「开始审查」按钮；审查后为条款列表（由 memo 按 clause_ref 去重）。点击风险卡片 → 左侧滚动并高亮对应条款块。
- **结果**：完整流程可用：上传或 demo → 解析（等待）→ 开始审查 → 审查（等待）→ 左侧显示条款、右侧显示风险卡片；点击卡片 → 左侧滚动并高亮该条款。

---

## 具体过程（当前 MVP 流程）

1. **后端**：`uvicorn app.main:app --reload`（默认 http://127.0.0.1:8000）。可选：在 `.env` 中配置 NEO4J_*、OPENAI_API_KEY。
2. **前端**：`cd frontend && npm run dev`（默认 http://localhost:3000）。可选：`NEXT_PUBLIC_API_URL=http://localhost:8000`。
3. **用户**：打开前端 →「上传 PDF」或「使用样本合同」→ 等待解析完成 →「开始审查」→ 等待审查完成 → 左侧显示条款（来自 memo），右侧显示风险卡片。
4. **用户**：点击某张风险卡片 → 左侧滚动并高亮该条对应的条款（按 clause_ref / citation）。
5. **API 顺序**：POST /contracts/demo（或 /contracts/upload）→ GET /review?contract_id=EX-10.4(a)（或 POST /review 带 body）。健康检查：GET /health。

---

## Phase 7：测试与文档

### 任务 23：单元测试

- **完成**：`tests/unit/` 下 test_parsing、test_extraction、test_graph、test_retrieval、test_agents；`tests/conftest.py`（fixture：最小 PDF、样本文本/条款、mock Neo4j）。覆盖 parse_pdf、strip_repeated_headers_footers、segment_clauses、extract_cross_references、ingest_contract、get_clause_neighborhood、get_context_for_clause、build_graph_context、scan_clause、evaluate_finding、evaluate_escalation（Neo4j/OpenAI 用 mock）。
- **结果**：`pytest tests/unit -v` 共 20 条单测，无需真实 Neo4j/OpenAI。

### 任务 24：集成测试

- **完成**：`tests/integration/test_review_pipeline.py` — 用样本 PDF 跑 run_structural_pipeline → run_review，断言返回 StructuredRiskMemo 及每项含 clause、risk_level、rule_triggered、reason、escalation。未配置 NEO4J_PASSWORD 或 OPENAI_API_KEY 时自动 skip。标记 `@pytest.mark.integration`，`pytest.ini` 注册。E2E（Playwright/Cypress）为可选。
- **结果**：`pytest tests/integration -v` 运行 1 条集成测试（约 3 分钟，需 Neo4j + OpenAI）。

### 任务 25：README 与文档更新

- **完成**：README.md 补充 Getting started（安装、环境变量、启动后端/前端、运行单测与集成测试）；Tech stack 更新为 PyMuPDF、Next.js 14；Progress 表更新为 Phase 0～7（Phase 6 暂不实施）。docs/commands.md 已含单测与集成测试命令。
- **结果**：新成员可按 README 跑通项目并执行测试；各阶段详情见 docs/PROGRESS.md。

---

## 当前状态小结

| 层级           | 状态 | 说明 |
|----------------|------|------|
| 结构层         | ✅   | PDF → 解析 → 规则分段 + LLM 抽取 → 交叉引用 → Neo4j 入库，端到端跑通 |
| 检索层         | ✅   | 按 clause 取 clause_text + graph_context |
| Playbook       | ✅   | 多规则 YAML 加载 |
| Scanner        | ✅   | 单条款/全合同扫描；TRIGGERS 写回 Neo4j |
| Critic/Evaluator | ✅  | evaluate_finding / evaluate_escalation |
| LangGraph      | ✅   | build_review_graph + run_review → StructuredRiskMemo |
| API            | ✅   | health、contracts（upload/demo）、review；CORS + 异常处理 |
| 前端           | ✅   | Next.js 布局、RiskCard + EvidenceChain、中英双语、上传→审查全流程 |
| Phase 6 评估与基线 | ⏸️  | 暂不实施（MVP 不需要 benchmark / 指标 / 基线对比）|
| 单元测试       | ✅   | tests/unit，20 条，mock Neo4j/OpenAI |
| 集成测试       | ✅   | tests/integration，PDF→review→StructuredRiskMemo，需 Neo4j+OpenAI |
| 文档           | ✅   | README Getting started + Progress 表，PROGRESS 记录各阶段 |
| 部署           | ✅   | 后端 Render、前端 Vercel；Neo4j 仅环境变量，无静默回退；见 Phase 8 |

更多命令见 `docs/commands.md`。

---

## Phase 8：生产部署与配置收紧

### 任务 26：Neo4j 配置完全由环境变量驱动

- **完成**：
  - **app/config.py**：去掉 Neo4j 硬编码默认值（`bolt://localhost:7687`、`neo4j`、`""`）。Neo4j 字段改为空字符串默认，并用 `@model_validator(mode="after")`（`require_neo4j_env`）校验三者均非空；任一项缺失则抛出 `ValueError`，并列出缺失的环境变量名（如 `NEO4J_URI`、`NEO4J_PASSWORD`）。仍用 Pydantic Settings 的 `SettingsConfigDict(env_file=".env", ...)`；环境变量名 `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` 自动映射到字段。
  - **app/graph/client.py**：`get_driver()` 仅使用 `get_settings()` 的 neo4j_uri/user/password；移除多余的内联密码检查（在 settings 加载时已校验）。
  - **tests/integration/test_review_pipeline.py**：`_integration_ready()` 改为通过 `os.environ.get("NEO4J_URI")` 等判断是否 skip，避免在未配置 Neo4j 时调用 `get_settings()` 触发校验错误。
  - **.env.example**（仓库根目录）：占位 `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD`、`OPENAI_API_KEY`。**frontend/.env.example**：占位 `NEXT_PUBLIC_API_URL`。
- **结果**：不再静默回退到 localhost 或空密码；Neo4j 相关环境变量缺失时在启动阶段报错并指明缺失项。本地用 `.env`，Render 用 Render 环境变量。

### 任务 27：后端部署到 Render

- **完成**：后端 API 以 Web Service 形式部署在 Render。在 Render 中配置环境变量：`NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD`、`OPENAI_API_KEY`（代码中不写明文）。
- **问题**：首次部署返回 500，Neo4j 报 `Neo.ClientError.Security.Unauthorized`。原因：Render 上填写的 Neo4j 凭证错误或过期（如 Aura 的 URI 格式不对、或在 Aura 重置密码后未同步到 Render）。处理：从 Neo4j Aura「Connect」重新复制 URI/用户/密码，在 Render 中更新环境变量并重新部署。
- **排查**：曾在 `app/main.py` 启动时临时打印 `neo4j_uri`、`neo4j_user`、`neo4j_password_len` 以确认服务端实际读取值；确认后已删除。

### 任务 28：前端部署到 Vercel

- **完成**：前端（Next.js）部署到 Vercel。项目 Root Directory 设为 `frontend`。环境变量 `NEXT_PUBLIC_API_URL` 指向 Render 后端地址（如 `https://contractsentinel.onrender.com`）。修改该变量后需重新部署，Next.js 会在构建时内联该值。
- **问题**：首次部署后点击「使用样本」/ demo，风险备忘录区域显示「fail to fetch」。原因：(1) 未设置或未生效 `NEXT_PUBLIC_API_URL`（构建结果里仍是 `http://localhost:8000`）；(2) 或 Render 免费实例冷启动，首请求超时。处理：在 Vercel 中设置 `NEXT_PUBLIC_API_URL` 并重新部署（可不勾选缓存）；若为冷启动，约 1 分钟后重试或先访问 GET /health 唤醒后端。
- **结果**：一个前端链接（如 `https://xxx.vercel.app`）即可使用完整产品；后端在 Render；CORS 已为 `allow_origins=["*"]`。

### 任务 29：前端构建修复（RiskCard TypeScript）

- **完成**：`frontend/app/components/RiskCard.tsx` 中 `riskLevelLabel(level, t)` 导致类型错误：`useLocale()` 的 `t` 只接受特定文案 key，但参数类型写成了 `(k: string) => string`。将 `t` 的类型收窄为 `(k: "riskLevelHigh" | "riskLevelLow" | "riskLevelMedium") => string`。
- **结果**：`npm run build` 通过，前端可正常部署。

### 生产部署流程

1. **后端（Render）**：创建 Web Service，连接仓库；设置环境变量 `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD`、`OPENAI_API_KEY`。构建：`pip install -r requirements.txt`；启动：`uvicorn app.main:app --host 0.0.0.0 --port $PORT`。
2. **前端（Vercel）**：导入仓库，Root Directory 设为 `frontend`。设置 `NEXT_PUBLIC_API_URL` 为后端地址（无末尾斜杠）。部署（修改环境变量后需重新部署以让 Next 内联该值）。
3. **Neo4j（Aura）**：从「Connect」获取 URI/用户/密码；Aura Free 无单独用户管理，该组凭证即唯一 DB 用户。若在 Aura 重置密码，需在 Render 中更新并重新部署。
4. **文档**：`docs/deploy-frontend.md` 说明 Vercel 及 Render 前端部署方式；`frontend/.env.example` 与根目录 `.env.example` 列出所需变量。
