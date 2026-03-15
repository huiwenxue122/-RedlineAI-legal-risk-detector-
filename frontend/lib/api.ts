/**
 * Backend API client for ContractSentinel.
 * Base URL: NEXT_PUBLIC_API_URL or http://localhost:8000
 */
import type { StructuredRiskMemo } from "@/app/types/risk";

const API_BASE =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8000";

export interface UploadResult {
  contract_id: string;
  status: string;
  clauses: number;
  definitions: number;
  ingest: string;
}

export async function uploadContract(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/contracts/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || String(res.status));
  }
  return res.json();
}

export async function demoContract(): Promise<UploadResult> {
  const res = await fetch(`${API_BASE}/contracts/demo`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || String(res.status));
  }
  return res.json();
}

export async function runReview(
  contractId: string,
  playbookId?: string | null
): Promise<StructuredRiskMemo> {
  const url = new URL(`${API_BASE}/review`);
  url.searchParams.set("contract_id", contractId);
  if (playbookId) url.searchParams.set("playbook_id", playbookId);
  const res = await fetch(url.toString(), { method: "GET" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || String(res.status));
  }
  return res.json();
}
