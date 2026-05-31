import type { JobEvent, PipelineStep, PipelineSummary } from "./types";

export const workflowTabs = ["Process", "Tags", "Inspect", "Index"] as const;
export type WorkflowTab = (typeof workflowTabs)[number];

export const stepLabels: Record<string, string> = {
  parsed: "Parse",
  page_images: "Images",
  tables_extracted: "Tables",
  figures_extracted: "Figures",
  entities_extracted: "Entities",
  relations_extracted: "Relations",
  metadata_built: "Metadata",
  quality_checked: "Quality",
  chunks_created: "Chunks",
  indexed: "Indexed",
};

export function pipelineProgress(steps: PipelineStep[] = []) {
  const total = steps.length;
  const completed = steps.filter((step) => step.status === "success").length;
  const failed = steps.filter((step) => step.status === "failed").length;
  const running = steps.filter((step) => step.status === "running").length;
  return {
    completed,
    total,
    failed,
    running,
    percent: total ? Math.round((completed / total) * 100) : 0,
  };
}

export function livePipelineProgress(progress: PipelineSummary, logs: JobEvent[] = []): PipelineSummary {
  const latestTerminal = [...logs].reverse().find((log) => log.type === "done" || log.type === "failed");
  if (latestTerminal?.type === "done") {
    return { ...progress, percent: 100 };
  }

  const latestPercent = [...logs].reverse().find((log) => typeof log.percent === "number")?.percent;
  if (typeof latestPercent !== "number") return progress;

  return {
    ...progress,
    percent: Math.max(0, Math.min(100, Math.round(latestPercent))),
  };
}

export function mergeJobEvents(existing: JobEvent[] = [], incoming: JobEvent[] = []) {
  const eventsByKey = new Map<string, JobEvent>();
  for (const event of [...existing, ...incoming]) {
    eventsByKey.set(jobEventKey(event), event);
  }
  return [...eventsByKey.values()].sort((a, b) => {
    if (a.job_id === b.job_id && typeof a.seq === "number" && typeof b.seq === "number") {
      return a.seq - b.seq;
    }
    return a.timestamp - b.timestamp;
  });
}

function jobEventKey(event: JobEvent) {
  if (typeof event.seq === "number") return `${event.job_id}:${event.seq}`;
  return [
    event.job_id,
    event.doc_id,
    event.type,
    event.timestamp,
    event.step ?? "",
    event.percent ?? "",
    event.message ?? "",
  ].join(":");
}

export function processingComplete(steps: PipelineStep[] = []) {
  return steps.length > 0 && steps.every((step) => step.status === "success");
}

export function canRunPipeline(steps: PipelineStep[] = []) {
  return !steps.some((step) => step.status === "running");
}

export function formatDuration(seconds?: number | null) {
  if (seconds == null) return "calculating";
  const value = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(value / 60);
  const secs = value % 60;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

export function statusTone(status?: string) {
  if (status === "success" || status === "done" || status === "READY") return "good";
  if (status === "failed" || status === "ERROR" || status === "NOT_READY") return "bad";
  if (status === "running" || status === "warning" || status === "READY_WITH_WARNINGS") return "warn";
  return "idle";
}

const STATUS_LABELS: Record<string, string> = {
  READY: "Ready",
  NOT_READY: "Low quality",
  READY_WITH_WARNINGS: "Ready (warnings)",
  success: "Success",
  done: "Done",
  failed: "Failed",
  running: "Running",
  pending: "Pending",
  uploaded: "Uploaded",
  queued: "Queued",
  warning: "Warning",
};

export function statusLabel(status?: string): string {
  if (!status) return "Unknown";
  return STATUS_LABELS[status] ?? status;
}
