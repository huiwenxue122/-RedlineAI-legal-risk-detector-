"use client";

import { useCallback, useRef, useState } from "react";
import { useLocale } from "@/app/context/LocaleContext";
import type { RiskMemoItem, StructuredRiskMemo } from "@/app/types/risk";
import { RiskCard } from "@/app/components/RiskCard";
import { demoContract, runReview, uploadContract } from "@/lib/api";

/** Unique clause block for left panel: clause_ref + clause text (from first occurrence in memo). */
function clausesFromMemo(memo: StructuredRiskMemo): { ref: string; clause: string }[] {
  const seen = new Set<string>();
  const out: { ref: string; clause: string }[] = [];
  for (const item of memo.items) {
    const ref = item.clause_ref || item.citation?.section || "";
    if (!ref || seen.has(ref)) continue;
    seen.add(ref);
    out.push({ ref, clause: item.clause || "" });
  }
  return out;
}

export default function Home() {
  const { t } = useLocale();
  const [contractId, setContractId] = useState<string | null>(null);
  const [memo, setMemo] = useState<StructuredRiskMemo | null>(null);
  const [uploading, setUploading] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedClauseRef, setSelectedClauseRef] = useState<string | null>(null);
  const leftScrollRef = useRef<HTMLDivElement>(null);
  const clauseRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const handleDemo = useCallback(async () => {
    setError(null);
    setUploading(true);
    try {
      const r = await demoContract();
      setContractId(r.contract_id);
      setMemo(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }, []);

  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file?.name?.toLowerCase().endsWith(".pdf")) {
      setError("Please select a PDF file.");
      return;
    }
    setError(null);
    setUploading(true);
    try {
      const r = await uploadContract(file);
      setContractId(r.contract_id);
      setMemo(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
    e.target.value = "";
  }, []);

  const handleStartReview = useCallback(async () => {
    if (!contractId) return;
    setError(null);
    setReviewing(true);
    try {
      const m = await runReview(contractId);
      setMemo(m);
      setSelectedClauseRef(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setReviewing(false);
    }
  }, [contractId]);

  const scrollToClause = useCallback((ref: string) => {
    setSelectedClauseRef(ref);
    const el = clauseRefs.current[ref];
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, []);

  const clauseBlocks = memo ? clausesFromMemo(memo) : [];

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Left: contract / clauses */}
      <aside className="w-1/2 flex flex-col border-r border-[var(--panel-border)] bg-[var(--card-bg)] overflow-hidden">
        <header className="shrink-0 px-4 py-3 border-b border-[var(--panel-border)] bg-[var(--panel-bg)] flex items-center justify-between">
          <h1 className="text-sm font-semibold text-[var(--accent)]">
            {t("panelContract")}
          </h1>
          {contractId && (
            <span className="text-xs text-[var(--muted)]">
              {t("contractIdLabel")}: {contractId}
            </span>
          )}
        </header>
        <div ref={leftScrollRef} className="flex-1 overflow-auto p-4">
          {!contractId && !memo && (
            <div className="rounded border border-dashed border-[var(--panel-border)] bg-[var(--panel-bg)] p-6 text-center text-[var(--muted)]">
              <p className="text-sm mb-4">{t("panelContractHint")}</p>
              <div className="flex flex-col sm:flex-row gap-3 justify-center">
                <label className="cursor-pointer rounded bg-[var(--accent)] text-white px-4 py-2 text-sm font-medium hover:opacity-90">
                  {t("uploadPdf")}
                  <input
                    type="file"
                    accept=".pdf"
                    className="hidden"
                    onChange={handleUpload}
                    disabled={uploading}
                  />
                </label>
                <button
                  type="button"
                  onClick={handleDemo}
                  disabled={uploading}
                  className="rounded border border-[var(--panel-border)] bg-[var(--card-bg)] px-4 py-2 text-sm font-medium hover:bg-[var(--panel-bg)] disabled:opacity-50"
                >
                  {uploading ? t("uploading") : t("useDemo")}
                </button>
              </div>
            </div>
          )}
          {contractId && !memo && (
            <div className="rounded border border-[var(--panel-border)] bg-[var(--panel-bg)] p-6 text-center">
              <p className="text-sm text-[var(--muted)] mb-4">{t("runReviewHint")}</p>
              <button
                type="button"
                onClick={handleStartReview}
                disabled={reviewing}
                className="rounded bg-[var(--accent)] text-white px-4 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-50"
              >
                {reviewing ? t("reviewing") : t("startReview")}
              </button>
            </div>
          )}
          {memo && clauseBlocks.length > 0 && (
            <div className="space-y-4">
              {clauseBlocks.map(({ ref, clause }) => (
                <div
                  key={ref}
                  ref={(el) => {
                    clauseRefs.current[ref] = el;
                  }}
                  id={`clause-${ref}`}
                  className={`rounded border p-4 transition-colors ${
                    selectedClauseRef === ref
                      ? "border-[var(--accent)] bg-blue-50/50"
                      : "border-[var(--panel-border)] bg-[var(--panel-bg)]"
                  }`}
                >
                  <div className="text-xs font-medium text-[var(--accent)] mb-2">
                    {ref}
                  </div>
                  <p className="text-sm text-gray-700 whitespace-pre-wrap">{clause}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>

      {/* Right: risk cards */}
      <main className="w-1/2 flex flex-col overflow-hidden">
        <header className="shrink-0 px-4 py-3 border-b border-[var(--panel-border)] bg-[var(--panel-bg)]">
          <h2 className="text-sm font-semibold text-[var(--accent)]">
            {t("panelRisks")}
          </h2>
        </header>
        <div className="flex-1 overflow-auto p-4 space-y-3">
          {error && (
            <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {t("error")}: {error}
            </div>
          )}
          {!memo && (
            <p className="text-sm text-[var(--muted)]">{t("runReviewHint")}</p>
          )}
          {memo && memo.items.length === 0 && (
            <p className="text-sm text-[var(--muted)]">{t("noRisks")}</p>
          )}
          {memo &&
            memo.items.length > 0 &&
            memo.items.map((item, i) => (
              <div
                key={i}
                role="button"
                tabIndex={0}
                onClick={() => {
                  const ref = item.clause_ref || item.citation?.section || null;
                  if (ref) scrollToClause(ref);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    const ref = item.clause_ref || item.citation?.section || null;
                    if (ref) scrollToClause(ref);
                  }
                }}
                className="cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-2 rounded-lg"
              >
                <RiskCard item={item} />
              </div>
            ))}
        </div>
      </main>
    </div>
  );
}
