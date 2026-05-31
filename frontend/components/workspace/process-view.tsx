"use client";

import { Activity, CheckCircle2, AlertCircle, Loader2, Circle } from "lucide-react";
import { useEffect, useState } from "react";

import { StatusPill } from "@/components/ui/status-pill";
import { PipelineProgressCard } from "./pipeline-progress-card";
import type { JobEvent, PipelineRun, PipelineStep } from "@/lib/types";
import { formatDuration, statusLabel, type pipelineProgress } from "@/lib/workflow";

interface ProcessViewProps {
  steps: PipelineStep[];
  progress: ReturnType<typeof pipelineProgress>;
  runtime: { elapsed_seconds?: number | null; eta_seconds?: number | null; label?: string | null };
  isRunning: boolean;
  logs: JobEvent[];
  runs: PipelineRun[];
}

export function ProcessView({
  steps,
  progress,
  runtime,
  isRunning,
  logs,
  runs,
}: ProcessViewProps) {
  const [expandedRun, setExpandedRun] = useState<string | null>(runs[0]?.run_id ?? null);
  const [selectedNodeId, setSelectedNodeId] = useState<string>("parsed");
  const [activeSidebarTab, setActiveSidebarTab] = useState<"inspect" | "logs" | "history">("inspect");

  useEffect(() => {
    const runningStep = steps.find((step) => step.status === "running");
    if (runningStep) setSelectedNodeId(runningStep.step_name);
  }, [steps]);

  const getStepStatus = (name: string) => {
    const step = steps.find((s) => s.step_name === name);
    return step ? step.status : "pending";
  };

  const getStepDetails = (name: string) => {
    const step = steps.find((s) => s.step_name === name);
    return step
      ? {
          status: step.status,
          started_at: step.started_at,
          completed_at: step.completed_at,
          error_message: step.error_message,
        }
      : {
          status: "pending",
          started_at: null,
          completed_at: null,
          error_message: null,
        };
  };

  const groups = [
    {
      title: "Ingest & Parse",
      subtitle: "Ingestion & structural parsing",
      steps: ["parsed", "page_images"],
    },
    {
      title: "Extraction",
      subtitle: "Asset & pattern extraction",
      steps: ["tables_extracted", "figures_extracted", "entities_extracted", "relations_extracted"],
    },
    {
      title: "Enrich & Validate",
      subtitle: "Metadata compiling & quality",
      steps: ["metadata_built", "quality_checked"],
    },
    {
      title: "Chunk & Index",
      subtitle: "Vector embedding ingestion",
      steps: ["chunks_created", "indexed"],
    },
  ];

  const stepsInfo = {
    parsed: {
      order: "01",
      label: "Parse Document",
      desc: "Extracts document structural text, parses headers, page boundaries, and creates layout coordinates.",
    },
    page_images: {
      order: "02",
      label: "Page Images",
      desc: "Converts each document page into high-resolution PNG images for rendering visual search evidence.",
    },
    tables_extracted: {
      order: "03",
      label: "Tables",
      desc: "Scans for table boundaries, extracts tabular data structure, and formats output as Markdown and CSV.",
    },
    figures_extracted: {
      order: "04",
      label: "Figures",
      desc: "Isolates diagrams and charts, extracts OCR text, and maps visual figures to corresponding sections.",
    },
    entities_extracted: {
      order: "05",
      label: "Entities",
      desc: "Uses entity extraction (LLM/rule-based) to identify key AWS/GCP/Azure resources, subnets, and IPs.",
    },
    relations_extracted: {
      order: "06",
      label: "Relations",
      desc: "Builds an entity co-occurrence graph linking AWS services, CIDRs, and governance terms found on adjacent pages. Powers graph_local search.",
    },
    metadata_built: {
      order: "07",
      label: "Metadata",
      desc: "Assembles structural hierarchy, extracted entities, and asset references into a single unified JSON manifest.",
    },
    quality_checked: {
      order: "08",
      label: "Quality Check",
      desc: "Performs heuristics-based validation on document extracts, verifying OCR confidence and raising warnings.",
    },
    chunks_created: {
      order: "09",
      label: "Chunks",
      desc: "Splits extracted text into optimal semantic passages with overlap, anchoring them to layout page sections.",
    },
    indexed: {
      order: "10",
      label: "Index Document",
      desc: "Generates vector embeddings using Ollama BGE-M3 model and upserts payloads to the Qdrant database.",
    },
  };

  const selectedDetails = getStepDetails(selectedNodeId);
  const selectedInfo = stepsInfo[selectedNodeId as keyof typeof stepsInfo] || { label: selectedNodeId, desc: "", order: "" };

  const getDuration = () => {
    if (!selectedDetails.started_at) return "N/A";
    const start = new Date(selectedDetails.started_at).getTime();
    const end = selectedDetails.completed_at
      ? new Date(selectedDetails.completed_at).getTime()
      : Date.now();
    return formatDuration((end - start) / 1000);
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-5 overflow-hidden">
      <PipelineProgressCard progress={progress} runtime={runtime} isRunning={isRunning} />

      {/* Full-height Flow Visualizer */}
      <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-3xl border border-white/10 bg-white/[0.035] p-5">
        <div className="mb-4 flex items-center justify-between shrink-0">
          <div>
            <h3 className="text-lg font-semibold">Pipeline Flow Visualizer</h3>
            <p className="text-sm text-slate-400">Click steps to inspect data ingestion phases</p>
          </div>
          <Activity className="text-cyan-200" />
        </div>
        <div className="thin-scrollbar grid min-h-0 flex-1 grid-cols-1 items-stretch gap-6 overflow-y-auto pr-1 lg:grid-cols-[minmax(0,1fr)_minmax(300px,360px)] lg:overflow-hidden lg:pr-0">
          {/* Responsive Visualizer Grid Container */}
          <div className="relative flex min-h-[260px] flex-col justify-center overflow-y-auto rounded-2xl border border-white/5 bg-slate-950/40 p-4 lg:min-h-0 lg:p-6">
            
            {/* HTML Columns Layout */}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 w-full relative z-10">
              {groups.map((group) => (
                <div
                  key={group.title}
                  className="flex flex-col rounded-2xl bg-white/[0.015] border border-white/5 p-4 min-h-0 flex-1"
                >
                  <div className="mb-4 shrink-0">
                    <h4 className="text-sm font-semibold text-cyan-200 tracking-wide">{group.title}</h4>
                    <p className="text-[10px] text-slate-500 mt-0.5">{group.subtitle}</p>
                  </div>
                  <div className="flex flex-col gap-4 flex-1 justify-center">
                    {group.steps.map((stepId) => {
                      const status = getStepStatus(stepId);
                      const isSelected = selectedNodeId === stepId;
                      const info = stepsInfo[stepId as keyof typeof stepsInfo];
                      if (!info) return null;

                      let cardBorder = "border-white/10";
                      let cardBg = "bg-slate-950/40";
                      let textColor = "text-slate-400";
                      let numColor = "text-slate-500";
                      let badgeBg = "bg-white/[0.04]";
                      let glowStyle = {};

                      if (isSelected) {
                        cardBorder = "border-cyan-400/80";
                        cardBg = "bg-cyan-950/20";
                        textColor = "text-white";
                        numColor = "text-cyan-300";
                        badgeBg = "bg-cyan-500/20";
                        glowStyle = {
                          boxShadow: "0 0 15px rgba(45, 212, 191, 0.15)",
                        };
                      } else if (status === "success") {
                        cardBorder = "border-cyan-500/20 hover:border-cyan-500/40";
                        cardBg = "bg-slate-900/20 hover:bg-slate-900/40";
                        textColor = "text-slate-200";
                        numColor = "text-cyan-400";
                      } else if (status === "running") {
                        cardBorder = "border-violet-500/80";
                        cardBg = "bg-violet-950/20";
                        textColor = "text-white";
                        numColor = "text-violet-300";
                        badgeBg = "bg-violet-500/20";
                        glowStyle = {
                          boxShadow: "0 0 15px rgba(139, 92, 246, 0.2)",
                        };
                      } else if (status === "failed") {
                        cardBorder = "border-red-500/60 hover:border-red-500/80";
                        cardBg = "bg-red-950/20";
                        textColor = "text-red-200";
                        numColor = "text-red-400";
                        badgeBg = "bg-red-500/20";
                      }

                      return (
                        <div
                          key={stepId}
                          onClick={() => {
                            setSelectedNodeId(stepId);
                            setActiveSidebarTab("inspect");
                          }}
                          style={{ ...glowStyle, transition: "all 0.25s ease" }}
                          className={`relative flex items-center justify-between gap-3 p-3.5 rounded-xl border ${cardBorder} ${cardBg} cursor-pointer group hover:scale-[1.02] active:scale-[0.98] select-none`}
                        >
                          <div className="flex min-w-0 items-center gap-3">
                            {/* Step Order Badge */}
                            <span className={`text-[10px] font-mono px-2 py-0.5 rounded-md ${badgeBg} ${numColor} font-bold`}>
                              {info.order}
                            </span>
                            {/* Title */}
                            <span className={`min-w-0 text-xs font-semibold [overflow-wrap:anywhere] ${textColor}`}>
                              {info.label}
                            </span>
                          </div>

                          {/* Status Icon */}
                          <div className="flex items-center">
                            {status === "success" && (
                              <CheckCircle2 size={15} className="text-cyan-400 drop-shadow-[0_0_4px_rgba(45,212,191,0.4)]" />
                            )}
                            {status === "running" && (
                              <Loader2 size={15} className="text-violet-400 animate-spin" />
                            )}
                            {status === "failed" && (
                              <AlertCircle size={15} className="text-red-400 animate-bounce" />
                            )}
                            {status === "pending" && (
                              <Circle size={14} className="text-slate-600" />
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Tabbed Ingestion Sidebar (Unified Phase Inspection, Live Logs, Run History) */}
          <div className="flex min-h-[320px] flex-col overflow-hidden rounded-2xl border border-white/5 bg-slate-950/20 p-4 lg:h-full lg:min-h-0">
            {/* Sidebar Tabs Header */}
            <div className="flex border-b border-white/10 pb-2 mb-4 gap-1 shrink-0 overflow-x-auto">
              <button
                onClick={() => setActiveSidebarTab("inspect")}
                className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all duration-200 ${
                  activeSidebarTab === "inspect"
                    ? "bg-cyan-500/20 text-cyan-200 border border-cyan-500/30"
                    : "text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent"
                }`}
              >
                Inspect
              </button>
              <button
                onClick={() => setActiveSidebarTab("logs")}
                className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all duration-200 relative ${
                  activeSidebarTab === "logs"
                    ? "bg-cyan-500/20 text-cyan-200 border border-cyan-500/30"
                    : "text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent"
                }`}
              >
                Live Log
                {isRunning && (
                  <span className="absolute top-1 right-1 flex h-1.5 w-1.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-cyan-500"></span>
                  </span>
                )}
              </button>
              <button
                onClick={() => setActiveSidebarTab("history")}
                className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all duration-200 ${
                  activeSidebarTab === "history"
                    ? "bg-cyan-500/20 text-cyan-200 border border-cyan-500/30"
                    : "text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent"
                }`}
              >
                History ({runs.length})
              </button>
            </div>

            {/* Tab Content */}
            <div className="flex-1 min-h-0 overflow-y-auto thin-scrollbar">
              {activeSidebarTab === "inspect" && (
                <div className="flex min-h-full flex-col justify-between space-y-4">
                  <div className="space-y-4">
                    <div>
                      <span className="text-[10px] uppercase tracking-[0.25em] text-slate-500">
                        Selected Phase
                      </span>
                      <h4 className="text-lg font-semibold text-slate-100 mt-1">
                        {selectedInfo.order && `${selectedInfo.order} · `}{selectedInfo.label}
                      </h4>
                      <p className="text-[10px] font-mono text-slate-500 mt-0.5">{selectedNodeId}</p>
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-xs border-b border-white/5 pb-2">
                        <span className="text-slate-400">Status</span>
                        <StatusPill status={selectedDetails.status} />
                      </div>
                      <div className="flex items-center justify-between text-xs border-b border-white/5 pb-2">
                        <span className="text-slate-400">Duration</span>
                        <span className="text-slate-200 font-medium">{getDuration()}</span>
                      </div>
                      <div className="flex items-center justify-between text-xs border-b border-white/5 pb-2">
                        <span className="text-slate-400">Started</span>
                        <span className="text-slate-200 font-medium">
                          {selectedDetails.started_at
                            ? new Date(selectedDetails.started_at).toLocaleTimeString()
                            : "N/A"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-xs border-b border-white/5 pb-2">
                        <span className="text-slate-400">Completed</span>
                        <span className="text-slate-200 font-medium">
                          {selectedDetails.completed_at
                            ? new Date(selectedDetails.completed_at).toLocaleTimeString()
                            : "N/A"}
                        </span>
                      </div>
                    </div>

                    <div>
                      <span className="text-[10px] uppercase tracking-[0.25em] text-slate-500">
                        Documentation
                      </span>
                      <p className="text-xs text-slate-400 leading-5 mt-1.5 bg-black/25 rounded-xl p-3 border border-white/5">
                        {selectedInfo.desc}
                      </p>
                    </div>
                  </div>

                  {selectedDetails.error_message && (
                    <div className="mt-4 rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-300 [overflow-wrap:anywhere]">
                      <span className="font-semibold block mb-1">Execution Failure:</span>
                      {selectedDetails.error_message}
                    </div>
                  )}
                </div>
              )}

              {activeSidebarTab === "logs" && (
                <div className="thin-scrollbar h-full min-h-0 overflow-auto rounded-xl border border-white/5 bg-black/35 p-4 font-mono text-xs text-cyan-100/85 [overflow-wrap:anywhere]">
                  {logs.length === 0 ? (
                    <p className="text-slate-500">No active run logs yet.</p>
                  ) : (
                    logs.map((log, index) => (
                      <p key={`${log.timestamp}-${index}`} className="mb-2">
                        {new Date(log.timestamp * 1000).toLocaleTimeString()} ·{" "}
                        {log.label ?? log.message ?? log.type}
                        {typeof log.percent === "number" ? ` · ${log.percent}%` : ""}
                        {typeof log.eta_seconds === "number"
                          ? ` · ETA ${formatDuration(log.eta_seconds)}`
                          : ""}
                      </p>
                    ))
                  )}
                </div>
              )}

              {activeSidebarTab === "history" && (
                <div className="thin-scrollbar h-full space-y-2 overflow-auto">
                  {runs.length === 0 ? (
                    <p className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 text-sm text-slate-500">
                      No pipeline runs recorded yet.
                    </p>
                  ) : (
                    runs.map((run) => (
                      <div key={run.run_id} className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                        <button
                          onClick={() => setExpandedRun(expandedRun === run.run_id ? null : run.run_id)}
                          className="mb-2 flex w-full items-center justify-between gap-3 text-left"
                        >
                          <p className="truncate text-sm font-medium">
                            {new Date(run.started_at).toLocaleString()}
                          </p>
                          <StatusPill status={run.status} />
                        </button>
                        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
                          <span>{run.events.length} events</span>
                          {typeof run.duration_seconds === "number" && (
                            <span>{formatDuration(run.duration_seconds)}</span>
                          )}
                          {typeof run.result?.status === "string" && (
                            <span>quality: {statusLabel(run.result.status)}</span>
                          )}
                          {typeof run.result?.chunks === "number" && (
                            <span>{String(run.result.chunks)} chunks</span>
                          )}
                          {run.error_message && (
                            <span className="text-red-200 [overflow-wrap:anywhere]">
                              {run.error_message}
                            </span>
                          )}
                        </div>
                        {expandedRun === run.run_id && (
                          <div className="mt-3 space-y-2 border-t border-white/10 pt-3">
                            {run.events.map((event, index) => (
                              <div
                                key={`${run.run_id}-${index}`}
                                className="grid grid-cols-[88px_minmax(0,1fr)_auto] gap-2 text-xs text-slate-400"
                              >
                                <span>
                                  {event.timestamp
                                    ? new Date(event.timestamp * 1000).toLocaleTimeString()
                                    : "--"}
                                </span>
                                <span className="text-left text-slate-300 [overflow-wrap:anywhere]">
                                  {event.payload.label ?? event.payload.message ?? event.event_type}
                                </span>
                                <span>
                                  {typeof event.payload.percent === "number"
                                    ? `${event.payload.percent}%`
                                    : event.event_type}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
