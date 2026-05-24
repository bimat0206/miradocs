import { describe, expect, it } from "vitest";
import { canRunPipeline, formatDuration, livePipelineProgress, mergeJobEvents, pipelineProgress, processingComplete, statusTone, workflowTabs } from "./workflow";

describe("workflow helpers", () => {
  it("calculates pipeline progress from successful steps", () => {
    expect(pipelineProgress([
      { step_name: "parsed", status: "success" },
      { step_name: "page_images", status: "running" },
      { step_name: "chunks_created", status: "pending" },
      { step_name: "indexed", status: "failed" },
    ])).toEqual({
      completed: 1,
      total: 4,
      failed: 1,
      running: 1,
      percent: 25,
    });
  });

  it("formats durations for live logs", () => {
    expect(formatDuration(8.9)).toBe("8s");
    expect(formatDuration(70.1)).toBe("1m 10s");
  });

  it("keeps step-derived progress without live events", () => {
    const progress = pipelineProgress([
      { step_name: "parsed", status: "success" },
      { step_name: "page_images", status: "pending" },
    ]);

    expect(livePipelineProgress(progress, [])).toEqual(progress);
  });

  it("uses live SSE percent while registry progress is stale", () => {
    const progress = pipelineProgress([
      { step_name: "parsed", status: "running" },
      { step_name: "page_images", status: "pending" },
    ]);

    expect(livePipelineProgress(progress, [
      { type: "progress", job_id: "job", doc_id: "doc", timestamp: 1, percent: 11 },
    ])).toEqual({ ...progress, percent: 11 });
  });

  it("shows complete immediately when the done event arrives", () => {
    const progress = pipelineProgress([
      { step_name: "parsed", status: "success" },
      { step_name: "page_images", status: "running" },
    ]);

    expect(livePipelineProgress(progress, [
      { type: "progress", job_id: "job", doc_id: "doc", timestamp: 1, percent: 33 },
      { type: "done", job_id: "job", doc_id: "doc", timestamp: 2 },
    ])).toEqual({ ...progress, percent: 100 });
  });

  it("keeps the last live percent after a failed event", () => {
    const progress = pipelineProgress([
      { step_name: "parsed", status: "running" },
      { step_name: "page_images", status: "pending" },
    ]);

    expect(livePipelineProgress(progress, [
      { type: "progress", job_id: "job", doc_id: "doc", timestamp: 1, percent: 22 },
      { type: "failed", job_id: "job", doc_id: "doc", timestamp: 2 },
    ])).toEqual({ ...progress, percent: 22 });
  });

  it("merges restored and live events without duplicates", () => {
    expect(mergeJobEvents([
      { seq: 0, type: "queued", job_id: "job", doc_id: "doc-a", timestamp: 1 },
      { seq: 1, type: "progress", job_id: "job", doc_id: "doc-a", timestamp: 2, percent: 12 },
    ], [
      { seq: 1, type: "progress", job_id: "job", doc_id: "doc-a", timestamp: 2, percent: 12 },
      { seq: 2, type: "progress", job_id: "job", doc_id: "doc-a", timestamp: 3, percent: 24 },
    ])).toEqual([
      { seq: 0, type: "queued", job_id: "job", doc_id: "doc-a", timestamp: 1 },
      { seq: 1, type: "progress", job_id: "job", doc_id: "doc-a", timestamp: 2, percent: 12 },
      { seq: 2, type: "progress", job_id: "job", doc_id: "doc-a", timestamp: 3, percent: 24 },
    ]);
  });

  it("keeps per-document restored event streams separate", () => {
    const logsByDoc = {
      "doc-a": mergeJobEvents([], [
        { type: "progress", job_id: "job-a", doc_id: "doc-a", timestamp: 1, percent: 44 },
      ]),
      "doc-b": mergeJobEvents([], [
        { type: "progress", job_id: "job-b", doc_id: "doc-b", timestamp: 1, percent: 9 },
      ]),
    };

    expect(livePipelineProgress({ completed: 0, total: 9, failed: 0, running: 1, percent: 0 }, logsByDoc["doc-a"]).percent).toBe(44);
    expect(livePipelineProgress({ completed: 0, total: 9, failed: 0, running: 1, percent: 0 }, logsByDoc["doc-b"]).percent).toBe(9);
  });

  it("maps status values into UI tones", () => {
    expect(statusTone("success")).toBe("good");
    expect(statusTone("failed")).toBe("bad");
    expect(statusTone("running")).toBe("warn");
    expect(statusTone("pending")).toBe("idle");
  });

  it("prevents starting another pipeline while a step is running", () => {
    expect(canRunPipeline([
      { step_name: "parsed", status: "success" },
      { step_name: "page_images", status: "pending" },
    ])).toBe(true);
    expect(canRunPipeline([
      { step_name: "parsed", status: "running" },
      { step_name: "page_images", status: "success" },
    ])).toBe(false);
  });

  it("treats processing as complete only when all steps including indexing are success", () => {
    expect(processingComplete([
      { step_name: "parsed", status: "success" },
      { step_name: "chunks_created", status: "success" },
      { step_name: "indexed", status: "success" },
    ])).toBe(true);
    expect(processingComplete([
      { step_name: "parsed", status: "success" },
      { step_name: "chunks_created", status: "success" },
      { step_name: "indexed", status: "pending" },
    ])).toBe(false);
  });

  it("defines the operator workspace tabs", () => {
    expect(workflowTabs).toEqual(["Process", "Tags", "Inspect", "Index"]);
  });
});
