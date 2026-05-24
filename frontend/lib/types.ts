export type PipelineStep = {
  id?: number;
  doc_id?: string;
  step_name: string;
  status: "pending" | "running" | "success" | "warning" | "failed";
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
};

export type PipelineSummary = {
  completed: number;
  total: number;
  failed: number;
  running: number;
  percent: number;
};

export type DocumentRecord = {
  doc_id: string;
  project: string;
  filename: string;
  file_type: string;
  file_size: number;
  sha256: string;
  upload_time: string;
  document_type: string;
  domain: string;
  sensitivity: string;
  tags: string[];
  status: string;
  duplicate?: boolean;
  pipeline?: PipelineSummary;
  pipeline_steps?: PipelineStep[];
};

export type JobEvent = {
  seq?: number;
  type: "queued" | "running" | "progress" | "done" | "failed";
  job_id: string;
  doc_id: string;
  timestamp: number;
  message?: string;
  step?: string;
  label?: string;
  status?: string;
  percent?: number;
  elapsed_seconds?: number;
  eta_seconds?: number | null;
  result?: Record<string, unknown>;
};

export type PipelineRun = {
  run_id: string;
  doc_id: string;
  status: "queued" | "running" | "done" | "failed";
  started_at: string;
  completed_at?: string | null;
  duration_seconds?: number | null;
  result?: Record<string, unknown> | null;
  error_message?: string | null;
  events: Array<{
    event_type: string;
    timestamp: number;
    payload: JobEvent;
  }>;
};

export type ActivePipeline = {
  job_id: string | null;
  status: "queued" | "running" | "done" | "failed" | null;
  run: PipelineRun | null;
  events: JobEvent[];
  steps: PipelineStep[];
};

export type TableArtifact = {
  table_id: string;
  page: number;
  rows: number;
  cols: number;
  file_csv?: string | null;
  file_md?: string | null;
  status?: string;
};

export type FigureArtifact = {
  figure_id: string;
  page: number;
  caption?: string;
  image_path?: string | null;
  has_bbox?: boolean;
  bbox?: number[] | null;
};

export type IndexStatus = {
  doc_id: string;
  chunks_available: boolean;
  chunks_count: number;
  indexed: boolean;
  last_indexed_at?: string | null;
  last_index_result?: { status?: string; indexed?: number; [key: string]: unknown } | null;
  index_step?: PipelineStep | null;
  adapter: Record<string, unknown>;
  reindex_recommended: boolean;
};

export type SearchResult = {
  score: number;
  hybrid_score?: number;
  rerank_score?: number;
  bm25_score?: number;
  chunk_id: string;
  doc_id: string;
  chunk_type: string;
  page_start: number;
  section_path: string;
  text: string;
  source_refs: Record<string, unknown>;
  source_file?: string;
  evidence?: {
    page_number: number;
    page_image: string | null;
    cropped_diagram: string | null;
    ocr_text: string | null;
    caption: string | null;
    figure_number: string | null;
    nearby_text: string;
    section_path: string;
    table_file?: string | null;
  };
};

export type SearchOptions = {
  hybrid?: boolean;
  rerank?: boolean;
  dense_weight?: number;
  sparse_weight?: number;
};

export type PageImageMatch = {
  text: string;
  term: string;
  x: number;
  y: number;
  width: number;
  height: number;
};

export type PageImageMatchesResponse = {
  doc_id: string;
  page: number;
  query: string;
  page_width: number;
  page_height: number;
  matches: PageImageMatch[];
};

export type CompareMode =
  | "auto"
  | "hld_lld"
  | "requirements_design"
  | "requirements_test"
  | "policy_architecture"
  | "sow_design"
  | "version_diff"
  | "generic_diff";

export type CompareEvidence = {
  doc_id: string;
  page: number;
  section_path?: string;
  text: string;
  table_id?: string | null;
};

export type CompareFinding = {
  finding_id: string;
  run_id?: string;
  type: string;
  severity: "high" | "medium" | "low";
  title: string;
  description: string;
  source_evidence: CompareEvidence[];
  target_evidence: CompareEvidence[];
  normalized_key: string;
  llm_status?: string | null;
  llm_summary?: string | null;
  llm_recommendation?: string | null;
};

export type CompareRun = {
  run_id: string;
  source_doc_id: string;
  target_doc_id: string;
  requested_mode: CompareMode | string;
  detected_mode: CompareMode | string;
  status: "running" | "done" | "failed" | string;
  started_at: string;
  completed_at?: string | null;
  summary?: CompareSummary;
  error_message?: string | null;
};

export type CompareSummary = {
  total?: number;
  by_severity?: Record<string, number>;
  by_type?: Record<string, number>;
};

export type CompareResult = {
  run: CompareRun;
  summary: CompareSummary;
  findings: CompareFinding[];
};

export type CompareModeDetection = {
  detected_mode: CompareMode;
  confidence: number;
  reasons: string[];
};
