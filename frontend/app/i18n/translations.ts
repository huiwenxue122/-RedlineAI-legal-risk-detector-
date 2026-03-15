export type Locale = "zh" | "en";

export const translations: Record<
  Locale,
  {
    appTitle: string;
    appDescription: string;
    panelContract: string;
    panelContractPlaceholder: string;
    panelContractHint: string;
    panelRisks: string;
    riskCardRulePlaceholder: string;
    riskCardLevelMedium: string;
    riskCardBodyPlaceholder: string;
    riskCardEvidenceHint: string;
    language: string;
    langZh: string;
    langEn: string;
    riskCardRule: string;
    riskCardReason: string;
    riskCardFallback: string;
    riskCardEscalation: string;
    riskCardCitation: string;
    riskCardEvidence: string;
    riskCardJustified: string;
    riskCardConfidence: string;
    riskLevelHigh: string;
    riskLevelMedium: string;
    riskLevelLow: string;
    evidenceChainTitle: string;
    evidenceSection: string;
    evidenceExpand: string;
    evidenceCollapse: string;
    justifiedYes: string;
    justifiedNo: string;
    uploadPdf: string;
    useDemo: string;
    startReview: string;
    loading: string;
    uploading: string;
    reviewing: string;
    runReviewHint: string;
    noRisks: string;
    contractIdLabel: string;
    error: string;
  }
> = {
  zh: {
    appTitle: "ContractSentinel — 证据导向合同审查",
    appDescription: "合同风险审查与证据链展示",
    panelContract: "合同 / 条款",
    panelContractPlaceholder: "此处展示合同全文或选中条款",
    panelContractHint: "上传合同并运行审查后，将在此显示对应内容",
    panelRisks: "风险备忘录",
    riskCardRulePlaceholder: "规则 R00{i} · 占位",
    riskCardLevelMedium: "中",
    riskCardBodyPlaceholder:
      "此处展示单条风险：条款摘要、触发规则、原因、建议修订与升级建议。",
    riskCardEvidenceHint: "证据链与引用将在任务 18 接入",
    language: "语言",
    langZh: "中文",
    langEn: "English",
    riskCardRule: "规则",
    riskCardReason: "原因",
    riskCardFallback: "建议修订",
    riskCardEscalation: "升级建议",
    riskCardCitation: "引用",
    riskCardEvidence: "证据摘要",
    riskCardJustified: "判定",
    riskCardConfidence: "置信度",
    riskLevelHigh: "高",
    riskLevelMedium: "中",
    riskLevelLow: "低",
    evidenceChainTitle: "证据",
    evidenceSection: "条款",
    evidenceExpand: "证据 ↓",
    evidenceCollapse: "收起证据",
    justifiedYes: "是",
    justifiedNo: "否",
    uploadPdf: "上传 PDF",
    useDemo: "使用样本合同",
    startReview: "开始审查",
    loading: "加载中…",
    uploading: "解析中…",
    reviewing: "审查中…",
    runReviewHint: "上传或使用样本后点击「开始审查」",
    noRisks: "未发现风险项",
    contractIdLabel: "合同",
    error: "错误",
  },
  en: {
    appTitle: "ContractSentinel — Evidence-Based Contract Review",
    appDescription: "Contract risk review and evidence chain",
    panelContract: "Contract / Clause",
    panelContractPlaceholder: "Contract text or selected clause will appear here",
    panelContractHint: "Upload a contract and run review to see content here",
    panelRisks: "Risk Memo",
    riskCardRulePlaceholder: "Rule R00{i} · placeholder",
    riskCardLevelMedium: "Medium",
    riskCardBodyPlaceholder:
      "Single risk item: clause excerpt, rule triggered, reason, suggested revision, escalation.",
    riskCardEvidenceHint: "Evidence chain will be wired in Task 18",
    language: "Language",
    langZh: "中文",
    langEn: "English",
    riskCardRule: "Rule",
    riskCardReason: "Reason",
    riskCardFallback: "Suggested revision",
    riskCardEscalation: "Escalation",
    riskCardCitation: "Citation",
    riskCardEvidence: "Evidence",
    riskCardJustified: "Justified",
    riskCardConfidence: "Confidence",
    riskLevelHigh: "High",
    riskLevelMedium: "Medium",
    riskLevelLow: "Low",
    evidenceChainTitle: "Evidence",
    evidenceSection: "Section",
    evidenceExpand: "Evidence ↓",
    evidenceCollapse: "Collapse",
    justifiedYes: "Yes",
    justifiedNo: "No",
    uploadPdf: "Upload PDF",
    useDemo: "Use sample contract",
    startReview: "Start review",
    loading: "Loading…",
    uploading: "Parsing…",
    reviewing: "Reviewing…",
    runReviewHint: "Upload or use sample, then click Start review",
    noRisks: "No risk items found",
    contractIdLabel: "Contract",
    error: "Error",
  },
};

function interpolate(text: string, vars: Record<string, string>): string {
  return text.replace(/\{(\w+)\}/g, (_, key) => vars[key] ?? `{${key}}`);
}

export function t(
  locale: Locale,
  key: keyof (typeof translations)["zh"],
  vars?: Record<string, string>
): string {
  const value = translations[locale][key];
  return vars ? interpolate(value, vars) : value;
}
