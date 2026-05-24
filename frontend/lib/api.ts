import type {
  ActivePipeline,
  CompareMode,
  CompareModeDetection,
  CompareResult,
  CompareRun,
  DocumentRecord,
  IndexStatus,
  PageImageMatchesResponse,
  PipelineRun,
  PipelineStep,
  SearchResult,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: init?.body instanceof FormData
      ? init.headers
      : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || response.statusText);
  }
  return response.json() as Promise<T>;
}

export function listDocuments() {
  return request<{ documents: DocumentRecord[] }>("/api/documents");
}

export function getDocument(docId: string) {
  return request<DocumentRecord>(`/api/documents/${docId}`);
}

export function uploadDocument(form: FormData) {
  return request<DocumentRecord>("/api/documents", {
    method: "POST",
    body: form,
  });
}

export function deleteDocument(docId: string) {
  return request<{ status: string; warnings: string[] }>(`/api/documents/${docId}`, {
    method: "DELETE",
  });
}

export function updateDocumentTags(docId: string, tags: string[]) {
  return request<DocumentRecord>(`/api/documents/${docId}/tags`, {
    method: "PATCH",
    body: JSON.stringify({ tags }),
  });
}

export function getPipeline(docId: string) {
  return request<{ steps: PipelineStep[] }>(`/api/documents/${docId}/pipeline`);
}

export function getPipelineRuns(docId: string) {
  return request<{ runs: PipelineRun[] }>(`/api/documents/${docId}/pipeline/runs`);
}

export function getActivePipeline(docId: string) {
  return request<ActivePipeline>(`/api/documents/${docId}/pipeline/active`);
}

export function runPipeline(docId: string) {
  return request<{ job_id: string; status: string }>(`/api/documents/${docId}/pipeline/run`, {
    method: "POST",
  });
}

export function getArtifact<T>(docId: string, artifactType: string) {
  return request<T>(`/api/documents/${docId}/artifacts/${artifactType}`);
}

export async function getArtifactFileText(docId: string, artifactType: string, filename: string) {
  const response = await fetch(artifactFileUrl(docId, artifactType, filename));
  if (!response.ok) throw new Error(await response.text() || response.statusText);
  return response.text();
}

export function indexDocument(docId: string) {
  return request<{ status: string; indexed: number }>(`/api/documents/${docId}/index`, {
    method: "POST",
  });
}

export function getIndexStatus(docId: string) {
  return request<IndexStatus>(`/api/documents/${docId}/index/status`);
}

export function search(docId: string | string[], query: string, topK = 5, options?: import("./types").SearchOptions) {
  return request<{ results: SearchResult[] }>("/api/search", {
    method: "POST",
    body: JSON.stringify({
      doc_id: docId,
      query,
      top_k: topK,
      hybrid: options?.hybrid ?? true,
      rerank: options?.rerank ?? false,
      dense_weight: options?.dense_weight ?? 0.7,
      sparse_weight: options?.sparse_weight ?? 0.3,
    }),
  });
}

export function detectCompareMode(sourceDocId: string, targetDocId: string) {
  return request<CompareModeDetection>("/api/compare/detect-mode", {
    method: "POST",
    body: JSON.stringify({ source_doc_id: sourceDocId, target_doc_id: targetDocId }),
  });
}

export function runCompare(sourceDocId: string, targetDocId: string, mode: CompareMode) {
  return request<CompareResult>("/api/compare/run", {
    method: "POST",
    body: JSON.stringify({ source_doc_id: sourceDocId, target_doc_id: targetDocId, mode }),
  });
}

export function getCompareRun(runId: string) {
  return request<CompareResult>(`/api/compare/${runId}`);
}

export function getDocumentCompareRuns(docId: string) {
  return request<{ runs: CompareRun[] }>(`/api/documents/${docId}/compare/runs`);
}

export function pageImageUrl(docId: string, pageNum: number) {
  return `${API_BASE}/api/documents/${docId}/pages/${pageNum}/image`;
}

export function getPageImageMatches(docId: string, pageNum: number, query: string) {
  return request<PageImageMatchesResponse>(
    `/api/documents/${docId}/pages/${pageNum}/matches?query=${encodeURIComponent(query)}`,
  );
}

export function figureImageUrl(docId: string, figureId: string) {
  return `${API_BASE}/api/documents/${docId}/figures/${figureId}/image`;
}

export function artifactFileUrl(docId: string, artifactType: string, filename: string) {
  return `${API_BASE}/api/documents/${docId}/artifacts/${artifactType}/${encodeURIComponent(filename)}`;
}

export function jobEventsUrl(jobId: string) {
  return `${API_BASE}/api/jobs/${jobId}/events`;
}
