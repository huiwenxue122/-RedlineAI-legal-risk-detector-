# ContractSentinel 终端命令速查

每次重新跑项目时按顺序看这里即可。所有命令默认在**项目根目录** `ContractSentinel` 下执行。

---

## 一、一次性准备（新电脑 / 新 clone 后）

### 1. 进入项目并创建虚拟环境

```bash
cd /Users/claire/ContractSentinel
python -m venv .venv
source .venv/bin/activate
```

Windows 激活命令：

```bash
.venv\Scripts\activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 环境变量

```bash
cp .env.example .env
```

然后编辑 `.env`，填写：

- `OPENAI_API_KEY=sk-...`
- `NEO4J_URI=bolt://localhost:7687`
- `NEO4J_USER=neo4j`
- `NEO4J_PASSWORD=你的密码`

### 4. 启动 Neo4j（Docker）

若本机还没有名为 `neo4j` 的容器，或需要重新起一个（密码与 .env 一致）：

```bash
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/你的密码 neo4j:5
```

若已有同名容器，先删再起：

```bash
docker stop neo4j
docker rm neo4j
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/你的密码 neo4j:5
```

确认在跑：

```bash
docker ps
```

---

## 二、每次打开终端要跑项目时

### 1. 进入项目并激活虚拟环境

```bash
cd /Users/claire/ContractSentinel
source .venv/bin/activate
```

### 2. （可选）确认 Neo4j 在跑

```bash
docker ps
```

若 `neo4j` 未在列表或未运行，用 Docker Desktop 点启动，或重新执行上面「启动 Neo4j」的 `docker run`。

---

## 三、按任务/功能要运行的命令

### 任务 3+4+5+6：结构层端到端（PDF → 解析 → 抽取 → Neo4j）

用样本 PDF 跑通「PDF → 规则分段 → LLM 抽取 → 规则交叉引用 → 写入 Neo4j」：

```bash
python scripts/run_structural_pipeline.py "data/sample_contracts/EX-10.4(a).pdf"
```

不传参数则默认用 `data/sample_contracts/EX-10.4(a).pdf`：

```bash
python scripts/run_structural_pipeline.py
```

输出包含：rule-based clause 数量、LLM 抽取统计、Neo4j 写入节点/边数（需在 .env 配置 NEO4J_PASSWORD）。

### 验证抽取结果（摘要 + 导出 JSON）

```bash
python scripts/verify_extraction.py "data/sample_contracts/EX-10.4(a).pdf"
```

输出在 `out/contract_EX-10.4(a).json`，可打开与 PDF 对照。

### 任务 7：审查手册（Playbook）加载与查看

加载默认 playbook 并打印规则列表：

```bash
python scripts/run_playbook_demo.py
```

### 任务 8：图增强检索（随机或指定条款上下文）

从图中取**随机一个 section** 的 clause_text + graph_context + snippets：

```bash
python scripts/run_retrieval_demo.py
python scripts/run_retrieval_demo.py "EX-10.4(a)"
```

指定合同和条款：

```bash
python scripts/run_retrieval_demo.py "EX-10.4(a)" section_1_1
```

依赖 Neo4j 中已有该合同数据（先跑过 `run_structural_pipeline.py` 并成功 ingest）。

### 任务 9：Scanner Agent（条款风险扫描）

对图中**随机一个 section** 做规则扫描（Playbook 规则 R001/R002/R003）：

```bash
python scripts/run_scanner_demo.py
python scripts/run_scanner_demo.py "EX-10.4(a)"
```

指定合同和条款（**推荐用 section_9_1 复现非空结果**：该条含 “indemnify, defend and hold harmless”，应触发 R003）。注意：合同 ID 含括号时请加引号，否则 zsh 会报 “number expected”：

```bash
python scripts/run_scanner_demo.py "EX-10.4(a)" section_9_1
```

**当前状态总结（与现有证据一致）**

- Scanner 代码与解析逻辑正常，人工构造必中条款可成功触发 findings；rules_text、clause_text、graph_context 对部分 clause 已确认传入模型。
- 对真实合同条款返回 **Findings: 0** 的原因有两类，不能全部归因于“clause 不在图里 / clause_text 为空”：
  1. **数据缺失**：该 clause 在图中不存在或未写入 `text`，导致 `clause_text` 为空（demo 会打 Warning）。
  2. **规则未命中**：该 clause 有完整 clause_text 和 graph_context，但条文不匹配当前 playbook（或规则/提示词过窄），模型正确返回 0。

**已确认**：Scanner 未坏；demo 增加 empty-clause Warning 有价值；图中“空 clause_text”是真实存在的一类问题。  
**尚未确认**：真实合同命中率低，主要是规则太少、prompt 过保守，还是尚未扫到真正相关条款。

**验证 1：区分“空文本导致 0” vs “有文本但未命中”**

- **类别 1（有 text 的 clause）**：例如已验证的 section_5_1。若 debug 输出中 CLAUSE 非空、GRAPH CONTEXT 非空、且 Findings: 0 → 属于“规则未命中”，不是数据缺失。
  ```bash
  CONTRACT_SENTINEL_DEBUG_SCANNER=1 python scripts/run_scanner_demo.py "EX-10.4(a)" section_5_1
  ```
- **类别 2（会触发 Warning 的 clause）**：若输出出现“Warning: clause_text is empty”且 Findings: 0 → 才是“图里没数据”。

**验证 2：在真实条款上打出非空 findings**

- 优先试：section_7_2、section_7_6、section_5_5（或 section_9_1 若在图里）。**先确认图中确有 text**，再跑 Scanner：
  - Neo4j 中检查（浏览器或 cypher-shell）：  
    `MATCH (cl:Clause {contract_id: "EX-10.4(a)", id: "section_7_2"}) RETURN cl.id, cl.section_id, cl.text`
  - 若 `text` 非空，再执行：  
    `python scripts/run_scanner_demo.py "EX-10.4(a)" section_7_2`

**扫完整合同**（图中所有 clause 跑 Scanner，输出 Clause | Rule | Risk Level，并写入 `out/scan_<contract_id>.tsv`；同时把 findings 写回 Neo4j：`Clause -[:TRIGGERS {evidence?}]-> Rule`，便于 Critic Agent 直接读取）：

```bash
python scripts/scan_all_clauses.py "EX-10.4(a)"
```

**一键跑两项验证**（区分空文本 vs 规则未命中，并检查若干真实 clause 是否有 findings）：

```bash
python scripts/run_scanner_verifications.py "EX-10.4(a)"
```

**诊断脚本（排查代码/解析 vs 规则覆盖）**

- **诊断 1**：人工必中条款，若仍空 → 查 prompt / rules_text / 解析。
  ```bash
  python scripts/run_scanner_diagnostic.py
  ```
- **诊断 2**：打印实际传入模型的 rules / clause / graph_context。
  ```bash
  CONTRACT_SENTINEL_DEBUG_SCANNER=1 python scripts/run_scanner_demo.py "EX-10.4(a)" section_5_1
  ```

### 任务 10：Critic Agent（判断 Scanner 发现是否成立）

对指定条款先跑 Scanner，再对每条 finding 跑 Critic，结合条款全文与图上下文判断是否成立，输出 Justified / Reason：

```bash
python scripts/run_critic_demo.py "EX-10.4(a)" section_5_1
```

省略 clause_id 则随机选一个 clause；若该 clause 无 Scanner findings，会提示先跑有触发的条款或 scan_all_clauses。依赖 Neo4j + OPENAI_API_KEY。

### 任务 11：Evaluator Agent（升级决策 + 建议表述）

对指定条款跑 Scanner → Critic → Evaluator，输出每条 finding 的 Escalation（Acceptable / Suggest Revision / Escalate for Human Review）、可选 Fallback language、Reason：

```bash
python scripts/run_evaluator_demo.py "EX-10.4(a)" section_7_2
```

省略 clause_id 则随机选一个 clause。依赖 Neo4j + OPENAI_API_KEY。

### 启动后端 API（FastAPI）

（后续任务完成后可用）

```bash
uvicorn app.main:app --reload
```

浏览器访问：<http://127.0.0.1:8000>，API 文档：<http://127.0.0.1:8000/docs>。

### 启动前端（后续任务完成后可用）

在**新开一个终端**里：

```bash
cd /Users/claire/ContractSentinel/frontend
npm install
npm run dev
```

按提示在浏览器打开（一般为 <http://localhost:3000>）。

---

## 四、常用检查命令

| 目的           | 命令              |
|----------------|-------------------|
| 看 Neo4j 是否在跑 | `docker ps`       |
| 停掉 neo4j 容器  | `docker stop neo4j` |
| 删除 neo4j 容器  | `docker rm neo4j`   |
| 当前 Python / 包 | `which python` / `pip list` |

---

## 五、命令与任务对应关系

| 任务 / 用途      | 要运行的命令（在项目根、已激活 .venv） |
|------------------|----------------------------------------|
| 环境准备         | 见「一、一次性准备」                   |
| 每次开终端       | `cd /Users/claire/ContractSentinel` + `source .venv/bin/activate` |
| 任务 3+4+5+6 结构层 | `python scripts/run_structural_pipeline.py "data/sample_contracts/EX-10.4(a).pdf"` |
| 验证抽取 + 导出 JSON | `python scripts/verify_extraction.py "data/sample_contracts/EX-10.4(a).pdf"` |
| 任务 7 Playbook 查看 | `python scripts/run_playbook_demo.py` |
| 任务 8 图检索（随机 section） | `python scripts/run_retrieval_demo.py` 或 `python scripts/run_retrieval_demo.py "EX-10.4(a)"` |
| 任务 8 图检索（指定条款） | `python scripts/run_retrieval_demo.py "EX-10.4(a)" section_1_1` |
| 任务 9 Scanner（随机） | `python scripts/run_scanner_demo.py "EX-10.4(a)"` |
| 任务 9 Scanner（指定条款，可复现有 findings） | `python scripts/run_scanner_demo.py "EX-10.4(a)" section_9_1` |
| 任务 9 Scanner 扫完整合同 | `python scripts/scan_all_clauses.py "EX-10.4(a)"` |
| 任务 9 Scanner 两项验证（一键） | `python scripts/run_scanner_verifications.py "EX-10.4(a)"` |
| 任务 10 Critic（指定条款） | `python scripts/run_critic_demo.py "EX-10.4(a)" section_5_1` |
| 任务 11 Evaluator（Scanner→Critic→Evaluator 全链） | `python scripts/run_evaluator_demo.py "EX-10.4(a)" section_7_2` |
| 启动后端 API     | `uvicorn app.main:app --reload`        |
| 启动前端         | `cd frontend && npm run dev`          |

有新任务或新脚本时，把对应命令补进本文档即可。
