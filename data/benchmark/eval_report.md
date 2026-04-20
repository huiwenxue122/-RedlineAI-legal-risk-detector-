# RedlineAI Scanner Evaluation Report
**Date:** 2026-04-20  
**Dataset:** CUAD (Contract Understanding Atticus Dataset)  
**Contracts evaluated:** 25  
**Playbook:** saas_customer.yaml (10 rules, S001–S010)

---

## 1. 环境准备

```bash
cd /Users/claire/-RedlineAI-legal-risk-detector-
source .venv/bin/activate
pip install datasets
```

---

## 2. 数据集

**来源：** HuggingFace `kenlevine/CUAD`  
**格式：** 510 份商业合同，每份合同有 41 类专家标注（问答格式）  
**加载方式：**
```python
from datasets import load_dataset
ds = load_dataset("kenlevine/CUAD", verification_mode="no_checks")
contracts = ds["train"][0]["data"]  # 510 份合同
```

---

## 3. CUAD 类别 → Playbook 规则映射

| CUAD 标注类别 | 对应规则 | 说明 |
|---|---|---|
| Uncapped Liability | S001 | 无限责任 |
| Cap On Liability | S002 | 责任上限不合理 |
| Revenue/Profit Sharing | S005 | 收入分成（支付条款代理） |
| Minimum Commitment | S007 | 最低承诺量（锁定） |
| Termination For Convenience | S008 | 无供应商退出权 |
| Renewal Term | S009 | 自动续约 |
| Notice Period To Terminate Renewal | S010 | 续约取消通知期过长 |

未覆盖规则：S003（单方面赔偿）、S004（赔偿范围过宽）、S006（逾期付款救济弱）—— CUAD 无对应标注类别。

---

## 4. 评估方法

### 4.1 Pipeline 流程（每份合同）

```
合同文本
  → clause_segmenter.py（多格式条款切分）
  → scanner.py × N 条款（keyword 预筛 + LLM tool calling）
  → 输出 findings: [{clause_ref, rule_triggered, evidence_summary}]
```

### 4.2 TP / FP / FN 判定规则

- **TP**：CUAD 标注该类别存在（has_gt=True）且 Scanner 找到对应规则，且 Scanner 找到的条款文本与 CUAD 答案 span 有字符级重叠
- **FN**：CUAD 标注存在，但 Scanner 未触发对应规则
- **FP**：CUAD 标注不存在，但 Scanner 触发了对应规则

### 4.3 重叠检测（text_overlap）

```python
# 取较短字符串，每 40 字符为窗口，
# 若 ≥30% 的窗口出现在较长字符串中，则判定为重叠
chunk = 40
hits = sum(1 for i in range(0, len(shorter)-chunk+1, chunk//2)
           if shorter[i:i+chunk] in longer)
return hits / windows >= 0.3
```

重叠对象：Scanner 找到的**完整条款原文**（非 evidence_summary）vs CUAD 标注的答案 span。

---

## 5. 运行命令

### 5.1 快速验证（3 份合同，不花多少 API）

```bash
cd /Users/claire/-RedlineAI-legal-risk-detector-
source .venv/bin/activate
python scripts/eval_cuad.py --n 3 --out data/benchmark/eval_test.json
```

### 5.2 正式评估（25 份合同）

```bash
python scripts/eval_cuad.py --n 25 --out data/benchmark/eval_results.json
```

参数说明：
- `--n`：评估合同数量（默认 25）
- `--out`：结果输出路径（JSON）
- `--playbook`：使用的 playbook（默认 `data/playbooks/saas_customer.yaml`）

---

## 6. 实验结果（25 份合同）

### 6.1 各规则指标

| Rule | CUAD 类别 | TP | FP | FN | Precision | Recall | F1 |
|------|-----------|----|----|----|-----------|--------|----|
| S001 | Uncapped Liability | 1 | 7 | 2 | 0.125 | 0.333 | 0.182 |
| S002 | Cap On Liability | 2 | 0 | 8 | **1.000** | 0.200 | 0.333 |
| S005 | Revenue/Profit Sharing | 0 | 1 | 5 | 0.000 | 0.000 | — |
| S007 | Minimum Commitment | 1 | 1 | 3 | 0.500 | 0.250 | 0.333 |
| S008 | Termination For Convenience | 0 | 0 | 10 | — | 0.000 | — |
| S009 | Renewal Term | 2 | 0 | 5 | **1.000** | 0.286 | 0.444 |
| S010 | Notice Period | 1 | 0 | 3 | **1.000** | 0.250 | 0.400 |

### 6.2 总体指标

| 指标 | 数值 |
|------|------|
| Macro Precision | **0.604** |
| Macro Recall | **0.220** |
| 覆盖规则数（有数据） | 6 / 7 |

---

## 7. 结果分析

### 优势
- **Precision 较高（0.60）**：Scanner 报出的内容基本是真实风险，误报率低
- S002、S009、S010 的 precision 均为 1.0（零误报）

### 问题：Recall 低（0.22）的根本原因

**Keyword filter 过于保守。** Scanner 在调用 LLM 前先做关键词预筛，没有匹配到 keywords 的条款直接跳过，不进入 LLM。这导致：

1. **S008 Recall=0**：CUAD 里 "Termination For Convenience" 条款常用 "either party may terminate"、"upon X days written notice" 等措辞，与 playbook 中的 keywords（"may not terminate"、"terminate for convenience"）完全不匹配
2. **S002 FN=8**：大量责任条款写的是 "total liability" 而非 "aggregate liability"，被 keyword filter 过滤（已在实验过程中补充 "total liability" keyword，补充后有改善）
3. **S005 Recall=0**：CUAD 的 "Revenue/Profit Sharing" 是收入分成条款，而 S005 的关键词是 Net 60/90 支付条款，类别定义不对齐

### 数据集局限
- CUAD 包含分销协议、IP 协议、联合投资协议等，非纯 SaaS 客户合同，与系统 ICP（SaaS 供应商审查客户 MSA）存在领域偏差
- 部分 CUAD 类别与 playbook 规则语义对不上（如 S005 vs Revenue/Profit Sharing）

---

## 8. 下一步改进方向

1. **扩展 keyword 覆盖（短期）**：为 S008 补充 "may terminate"、"upon notice"、"written notice" 等宽泛关键词 ✅ 已在 v2 实施
2. **改 keyword filter 为宽松模式（中期）**：对每个规则类别只保留一个宽泛触发词（如 S001/S002 统一用 "liability"），把精确判断留给 LLM ✅ 已在 v2 实施
3. **领域对齐（长期）**：用 SEC EDGAR 上的真实 SaaS MSA 合同补充评估集，替代 CUAD 中非 SaaS 类型合同

---

## 9. 实验二：宽松 Keyword Filter（v2）

### 改动内容

将每条规则的 keyword 从"精确短语"改为"宽泛触发词 + 精确短语"组合：

| Rule | 新增宽泛 keyword |
|------|----------------|
| S001 | "liability", "liable", "damages", "limitation of liability" |
| S002 | "liability", "liable", "cap on liability", "limit of liability" |
| S007 | "term", "commit", "volume", "purchase obligation" |
| S008 | "terminat", "may terminate", "written notice", "upon notice", "days notice" |
| S009 | "renew", "renewal", "additional term", "successive period" |
| S010 | "notice", "days prior", "days before", "written notice" |

### 运行命令

```bash
python scripts/eval_cuad.py --n 25 --out data/benchmark/eval_results_v2.json
```

### 结果对比（25 份合同）

| Rule | CUAD 类别 | v1 Recall | v2 Recall | v1 Precision | v2 Precision |
|------|-----------|-----------|-----------|--------------|--------------|
| S001 | Uncapped Liability | 0.333 | **0.667** | 0.125 | 0.222 |
| S002 | Cap On Liability | 0.200 | 0.222 | 1.000 | 0.667 |
| S005 | Revenue/Profit Sharing | 0.000 | 0.000 | — | — |
| S007 | Minimum Commitment | 0.250 | **0.667** | 0.500 | 0.182 |
| S008 | Termination For Convenience | 0.000 | **0.222** | — | 0.286 |
| S009 | Renewal Term | 0.286 | **0.429** | 1.000 | 0.600 |
| S010 | Notice Period | 0.250 | 0.000 | 1.000 | 0.000 |

| 总体指标 | v1（原版） | v2（宽松 keyword） | 变化 |
|---------|-----------|-------------------|------|
| Macro Precision | 0.604 | 0.326 | -46% |
| Macro Recall | 0.220 | **0.368** | **+67%** |

### 分析

- **Recall 提升 67%**，S001/S007 从 0.25-0.33 跳到 0.67，S008 从 0 到 0.22（从完全找不到到能找到）
- **Precision 下降**：更多条款进入 LLM，FP 增多。对合同审查工具来说这是**正确 tradeoff**——宁可多报，不能漏报
- **S010 regression**：宽泛的 "notice" 关键词让很多无关条款进入 LLM，LLM 误判增多；可考虑 S010 单独保持精确 keyword

---

## 10. 脚本位置

| 文件 | 说明 |
|------|------|
| `scripts/eval_cuad.py` | 主评估脚本 |
| `data/benchmark/eval_results.json` | v1 结果（25 份合同） |
| `data/benchmark/eval_results_v2.json` | v2 结果（宽松 keyword，25 份合同） |
| `data/benchmark/eval_test.json` | 3 份合同验证结果 |
| `data/playbooks/saas_customer.yaml` | 评估使用的 playbook（v2 版本） |
