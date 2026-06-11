"use client";

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Calendar,
  ChevronRight,
  GitBranch,
  GitCommit,
  GitCompare,
  GitPullRequest,
  Loader2,
  Search,
  Trash2,
  ArrowLeft,
  X,
  Database,
  ArrowRight,
  Maximize2,
  ExternalLink,
  CheckCircle2,
  AlertCircle,
  Filter
} from "lucide-react";

import {
  fetchGroups,
  fetchGroup,
  compareVersions,
  deleteVersion,
  pageImageUrl
} from "@/lib/api";
import type { DocumentGroup, VersionSummary, CompareResult, CompareFinding, CompareEvidence } from "@/lib/types";
import { ImageLightbox } from "@/components/ui/image-lightbox";

const severityStyles: Record<string, string> = {
  high: "border-red-300/45 bg-red-500/10 text-red-100",
  medium: "border-amber-300/45 bg-amber-500/10 text-amber-100",
  low: "border-cyan-300/35 bg-cyan-500/10 text-cyan-100",
};

const DIFF_TERM_STOPWORDS = new Set([
  "and", "are", "but", "for", "from", "has", "have", "into", "its", "not", "the", "this", "that", "with",
  "source", "target", "evidence", "document", "page", "section", "missing", "extra", "different", "differs",
]);

interface VersionsViewProps {
  currentProject?: string;
  onSelectDocument: (docId: string) => void;
}

export function VersionsView({ currentProject = "default", onSelectDocument }: VersionsViewProps) {
  const queryClient = useQueryClient();
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [groupSearch, setGroupSearch] = useState("");

  // Selection for version comparison
  const [selectedVersions, setSelectedVersions] = useState<number[]>([]);

  // Active compare run details
  const [compareResult, setCompareResult] = useState<CompareResult | null>(null);
  const [isComparing, setIsComparing] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  // Findings filter
  const [severityFilter, setSeverityFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null);

  // Lightbox for image viewer
  const [lightbox, setLightbox] = useState<{ src: string; title: string; docId: string; page: number; query: string } | null>(null);

  // Queries
  const groupsQuery = useQuery({
    queryKey: ["version-groups", currentProject],
    queryFn: () => fetchGroups(currentProject),
  });

  const groupDetailQuery = useQuery({
    queryKey: ["version-group", selectedGroupId],
    queryFn: () => fetchGroup(selectedGroupId!),
    enabled: !!selectedGroupId,
  });

  const deleteMutation = useMutation({
    mutationFn: ({ groupId, versionNum }: { groupId: string; versionNum: number }) =>
      deleteVersion(groupId, versionNum),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["version-groups"] });
      queryClient.invalidateQueries({ queryKey: ["version-group", selectedGroupId] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      setSelectedVersions([]);
      setCompareResult(null);
    },
  });

  const groups = groupsQuery.data ?? [];
  const selectedGroup = groupDetailQuery.data;

  // Filter groups
  const filteredGroups = useMemo(() => {
    return groups.filter((g) =>
      g.name.toLowerCase().includes(groupSearch.toLowerCase()) ||
      g.base_filename.toLowerCase().includes(groupSearch.toLowerCase())
    );
  }, [groups, groupSearch]);

  const handleGroupSelect = (groupId: string) => {
    setSelectedGroupId(groupId);
    setSelectedVersions([]);
    setCompareResult(null);
    setCompareError(null);
  };

  const handleVersionCheckboxChange = (versionNum: number) => {
    setSelectedVersions((prev) => {
      if (prev.includes(versionNum)) {
        return prev.filter((v) => v !== versionNum);
      }
      if (prev.length >= 2) {
        // limit to 2 selections
        return [prev[1], versionNum];
      }
      return [...prev, versionNum];
    });
  };

  const handleRunCompare = async () => {
    if (selectedVersions.length !== 2 || !selectedGroupId) return;
    const sorted = [...selectedVersions].sort((a, b) => a - b);
    setIsComparing(true);
    setCompareError(null);
    setCompareResult(null);
    try {
      const res = await compareVersions(selectedGroupId, sorted[0], sorted[1]);
      setCompareResult(res);
    } catch (e: any) {
      setCompareError(e.message || "Failed to compare versions.");
    } finally {
      setIsComparing(false);
    }
  };

  // Findings processing
  const findings = compareResult?.findings ?? [];
  const types = useMemo(() => Array.from(new Set(findings.map((f) => f.type))).sort(), [findings]);
  const filteredFindings = useMemo(() => {
    return findings.filter((f) => {
      const severityMatch = severityFilter === "all" || f.severity === severityFilter;
      const typeMatch = typeFilter === "all" || f.type === typeFilter;
      return severityMatch && typeMatch;
    });
  }, [findings, severityFilter, typeFilter]);

  const selectedFinding = useMemo(() => {
    return filteredFindings.find((f) => f.finding_id === selectedFindingId) ?? filteredFindings[0] ?? null;
  }, [filteredFindings, selectedFindingId]);

  const selectedDiffQuery = useMemo(() => (selectedFinding ? diffQueryForFinding(selectedFinding) : ""), [selectedFinding]);

  const sourceDocInfo = useMemo(() => {
    if (!selectedGroup || selectedVersions.length < 2) return null;
    const sorted = [...selectedVersions].sort((a, b) => a - b);
    return selectedGroup.versions?.find((v) => v.version_number === sorted[0]) || null;
  }, [selectedGroup, selectedVersions]);

  const targetDocInfo = useMemo(() => {
    if (!selectedGroup || selectedVersions.length < 2) return null;
    const sorted = [...selectedVersions].sort((a, b) => a - b);
    return selectedGroup.versions?.find((v) => v.version_number === sorted[1]) || null;
  }, [selectedGroup, selectedVersions]);

  return (
    <div className="grid h-full min-h-0 gap-5 xl:grid-cols-[280px_1fr] flex-1">
      {/* LEFT PANEL: Group Browser */}
      <div className="flex flex-col rounded-2xl border border-white/10 bg-white/[0.02] p-4 min-h-0">
        <div className="mb-4">
          <h3 className="text-sm font-semibold tracking-wider text-slate-400 uppercase">Document Groups</h3>
          <div className="relative mt-2.5">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
            <input
              type="text"
              placeholder="Filter groups..."
              value={groupSearch}
              onChange={(e) => setGroupSearch(e.target.value)}
              className="h-9 w-full rounded-xl border border-white/10 bg-slate-950/50 pl-9 pr-3 text-xs text-slate-100 outline-none focus:border-cyan-400/40"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto thin-scrollbar space-y-2 pr-1">
          {groupsQuery.isLoading ? (
            <div className="flex items-center justify-center p-8 text-slate-500 gap-2">
              <Loader2 className="h-4 w-4 animate-spin text-cyan-400" />
              <span className="text-xs">Loading groups...</span>
            </div>
          ) : filteredGroups.length === 0 ? (
            <p className="p-4 text-center text-xs text-slate-500">No version groups found.</p>
          ) : (
            filteredGroups.map((g) => {
              const active = g.group_id === selectedGroupId;
              return (
                <button
                  key={g.group_id}
                  onClick={() => handleGroupSelect(g.group_id)}
                  className={`w-full rounded-xl border p-3 text-left transition ${
                    active
                      ? "border-cyan-400/50 bg-cyan-400/10 text-slate-50"
                      : "border-white/5 bg-black/10 text-slate-400 hover:border-white/10 hover:bg-white/[0.02]"
                  }`}
                >
                  <div className="flex items-start justify-between gap-1.5">
                    <span className="truncate text-xs font-semibold text-slate-200">{g.name}</span>
                    <span className="rounded-full bg-slate-950/40 px-1.5 py-0.5 text-[10px] text-slate-500 font-mono shrink-0">
                      {g.version_count} v
                    </span>
                  </div>
                  <p className="mt-1 truncate text-[10px] text-slate-500 font-mono">{g.base_filename}</p>
                  {g.latest_label && (
                    <div className="mt-2 flex items-center gap-1 text-[10px] text-cyan-300/80">
                      <GitBranch size={10} />
                      <span>Latest: {g.latest_label}</span>
                    </div>
                  )}
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* CENTER & RIGHT PANELS */}
      <div className="flex flex-col min-h-0 flex-1">
        {!selectedGroupId ? (
          <div className="flex flex-col items-center justify-center flex-1 rounded-2xl border border-dashed border-white/10 bg-white/[0.01] p-8 text-center text-slate-500">
            <GitPullRequest className="h-8 w-8 text-slate-600 mb-2.5 animate-pulse" />
            <p className="text-sm">Select a document group from the browser to manage version history and run semantic diffs.</p>
          </div>
        ) : (
          <div className="grid h-full min-h-0 gap-5 xl:grid-cols-[1fr_1.3fr] flex-1">

            {/* CENTER PANEL: Version Timeline */}
            <div className="flex flex-col rounded-2xl border border-white/10 bg-white/[0.02] p-4 min-h-0">
              <div className="shrink-0 flex items-center justify-between pb-3 border-b border-white/5 mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-slate-200">{selectedGroup?.name ?? "Timeline"}</h3>
                  <p className="text-[10px] text-slate-500 font-mono">{selectedGroup?.group_id}</p>
                </div>
                <button
                  disabled={selectedVersions.length !== 2 || isComparing}
                  onClick={handleRunCompare}
                  className="flex items-center gap-1.5 rounded-xl bg-cyan-400 px-3.5 py-2 text-xs font-bold text-slate-950 hover:bg-cyan-300 disabled:opacity-40 disabled:cursor-not-allowed transition"
                >
                  <GitCompare size={14} />
                  Compare Selected
                </button>
              </div>

              <div className="flex-1 overflow-y-auto thin-scrollbar pr-1 relative">
                {groupDetailQuery.isLoading ? (
                  <div className="flex items-center justify-center p-8 text-slate-500 gap-2">
                    <Loader2 className="h-4 w-4 animate-spin text-cyan-400" />
                    <span className="text-xs">Loading timeline...</span>
                  </div>
                ) : !selectedGroup?.versions?.length ? (
                  <p className="text-xs text-slate-500 text-center p-6">No versions in group.</p>
                ) : (
                  <div className="relative pl-6 border-l border-white/10 ml-3 py-2 space-y-6">
                    {/* Render timeline from newest (top) to oldest (bottom) */}
                    {[...selectedGroup.versions].reverse().map((v) => {
                      const isSelected = selectedVersions.includes(v.version_number);
                      const isLatest = v.is_latest;
                      const uploadDate = v.upload_time
                        ? new Date(v.upload_time).toLocaleDateString()
                        : "Unknown";

                      return (
                        <div key={v.version_id} className="relative group/node">
                          {/* Circle indicator on timeline */}
                          <div className={`absolute -left-[31px] top-1.5 flex h-4 w-4 items-center justify-center rounded-full border bg-slate-950 transition ${
                            isLatest
                              ? "border-cyan-400 text-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.3)]"
                              : "border-slate-700 text-slate-500"
                          }`}>
                            <GitCommit size={10} />
                          </div>

                          <div className="rounded-xl border border-white/5 bg-black/20 p-3 hover:border-white/10 transition">
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="text-xs font-bold text-slate-200">{v.version_label}</span>
                                  {isLatest && (
                                    <span className="rounded bg-cyan-400/10 px-1 py-0.5 text-[9px] font-medium text-cyan-300 border border-cyan-400/10">
                                      latest
                                    </span>
                                  )}
                                  <span className="rounded bg-slate-950/40 px-1 py-0.5 text-[9px] text-slate-500 font-mono">
                                    v{v.version_number}
                                  </span>
                                </div>
                                <p className="mt-1.5 truncate text-[11px] text-slate-400">{v.filename}</p>
                              </div>

                              <div className="flex items-center gap-2 shrink-0">
                                <label className="flex items-center gap-1.5 cursor-pointer">
                                  <input
                                    type="checkbox"
                                    checked={isSelected}
                                    onChange={() => handleVersionCheckboxChange(v.version_number)}
                                    className="h-3.5 w-3.5 rounded border-white/10 bg-slate-950/50 text-cyan-400 focus:ring-0 cursor-pointer"
                                  />
                                  <span className="text-[10px] text-slate-500 select-none">Diff</span>
                                </label>
                                <button
                                  onClick={() => onSelectDocument(v.doc_id)}
                                  className="rounded p-1 text-slate-500 hover:bg-white/5 hover:text-slate-300 transition"
                                  title="Inspect Document"
                                >
                                  <Maximize2 size={12} />
                                </button>
                                <button
                                  disabled={deleteMutation.isPending}
                                  onClick={() => {
                                    if (confirm(`Are you sure you want to delete ${v.version_label} (this will delete the document)?`)) {
                                      deleteMutation.mutate({ groupId: selectedGroup.group_id, versionNum: v.version_number });
                                    }
                                  }}
                                  className="rounded p-1 text-slate-600 hover:bg-red-500/10 hover:text-red-400 transition disabled:opacity-40"
                                  title="Delete Version"
                                >
                                  <Trash2 size={12} />
                                </button>
                              </div>
                            </div>

                            <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[10px] text-slate-500 border-t border-white/5 pt-2.5">
                              <span className="flex items-center gap-1">
                                <Calendar size={11} />
                                {uploadDate}
                              </span>
                              {v.page_count !== undefined && (
                                <span>{v.page_count} pages</span>
                              )}
                              <span className={`inline-flex items-center gap-0.5 rounded px-1 py-0.5 font-medium uppercase text-[9px] ${
                                v.status === "success" || v.status === "done"
                                  ? "bg-emerald-500/10 text-emerald-400"
                                  : v.status === "failed"
                                  ? "bg-red-500/10 text-red-400"
                                  : "bg-amber-500/10 text-amber-400"
                              }`}>
                                {v.status ?? "unknown"}
                              </span>
                            </div>

                            {v.notes && (
                              <p className="mt-2 text-[10px] italic text-slate-500 leading-normal bg-slate-950/20 rounded p-1.5 border border-white/5">
                                "{v.notes}"
                              </p>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* RIGHT PANEL: Compare / Findings Diff */}
            <div className="flex flex-col rounded-2xl border border-white/10 bg-white/[0.02] p-4 min-h-0">
              {isComparing ? (
                <div className="flex flex-col items-center justify-center flex-1 p-8 text-center text-slate-500">
                  <Loader2 className="h-6 w-6 animate-spin text-cyan-400 mb-2" />
                  <p className="text-xs">Computing semantic diff between selected versions...</p>
                </div>
              ) : compareError ? (
                <div className="flex flex-col items-center justify-center flex-1 p-8 text-center text-red-400">
                  <AlertCircle className="h-6 w-6 mb-2" />
                  <p className="text-xs">{compareError}</p>
                </div>
              ) : !compareResult ? (
                <div className="flex flex-col items-center justify-center flex-1 p-8 text-center text-slate-500">
                  <GitCompare className="h-6 w-6 mb-2 text-slate-600" />
                  <p className="text-xs">Select two checkboxes on the timeline and click Compare to view side-by-side semantic differences.</p>
                </div>
              ) : (
                <div className="flex flex-col h-full min-h-0">
                  <div className="shrink-0 border-b border-white/10 pb-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <h4 className="text-xs uppercase tracking-widest text-slate-500">Version Difference</h4>
                        <h3 className="text-sm font-semibold text-slate-200 mt-1">
                          {sourceDocInfo?.version_label} <span className="text-slate-500 font-normal">({sourceDocInfo?.version_number})</span>
                          <span className="mx-2 text-slate-600">→</span>
                          {targetDocInfo?.version_label} <span className="text-slate-500 font-normal">({targetDocInfo?.version_number})</span>
                        </h3>
                      </div>
                      <button
                        onClick={() => setCompareResult(null)}
                        className="rounded-lg p-1 text-slate-500 hover:bg-white/5 hover:text-slate-300"
                      >
                        <X size={15} />
                      </button>
                    </div>

                    <div className="mt-3 flex items-center gap-2">
                      <Filter size={13} className="text-slate-500" />
                      <select
                        value={typeFilter}
                        onChange={(e) => setTypeFilter(e.target.value)}
                        className="h-8 min-w-0 flex-1 rounded-xl border border-white/10 bg-slate-950/80 px-2.5 text-xs text-slate-200 outline-none focus:border-cyan-400/40"
                      >
                        <option value="all">All differences</option>
                        {types.map((t) => (
                          <option key={t} value={t}>{t.replaceAll("_", " ")}</option>
                        ))}
                      </select>
                    </div>

                    <div className="mt-2.5 flex justify-between gap-2 border-t border-white/5 pt-2.5">
                      {(["high", "medium", "low"] as const).map((sev) => {
                        const active = severityFilter === sev;
                        return (
                          <button
                            key={sev}
                            onClick={() => setSeverityFilter(active ? "all" : sev)}
                            className={`flex-1 rounded-lg border py-1 px-2 text-[10px] text-center transition capitalize font-semibold ${
                              active ? severityStyles[sev] : "border-white/5 bg-black/10 text-slate-500 hover:border-white/10"
                            }`}
                          >
                            {compareResult.summary?.by_severity?.[sev] ?? 0} {sev}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="flex-1 overflow-y-auto thin-scrollbar py-3 pr-1 space-y-2.5 min-h-0">
                    {filteredFindings.length === 0 ? (
                      <p className="text-xs text-slate-500 text-center py-6">No matching differences found.</p>
                    ) : (
                      filteredFindings.map((f) => {
                        const selected = selectedFinding?.finding_id === f.finding_id;
                        return (
                          <div
                            key={f.finding_id}
                            className={`rounded-xl border p-3 transition ${
                              selected ? "border-cyan-400/30 bg-cyan-400/5" : "border-white/5 bg-black/10"
                            }`}
                          >
                            <div className="flex flex-wrap items-center gap-1.5 mb-2">
                              <span className={`rounded-full border px-1.5 py-0.5 text-[9px] font-medium capitalize ${severityStyles[f.severity]}`}>
                                {f.severity}
                              </span>
                              <span className="rounded-full border border-white/10 bg-white/[0.04] px-1.5 py-0.5 text-[9px] text-slate-400 font-mono">
                                {f.type.replaceAll("_", " ")}
                              </span>
                            </div>
                            <h4 className="text-xs font-semibold text-slate-200">{f.title}</h4>
                            <p className="mt-1 text-[11px] leading-normal text-slate-400">{f.description}</p>

                            <div className="mt-3 grid gap-2.5 lg:grid-cols-2 pt-3 border-t border-white/5">
                              <div>
                                <h5 className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">
                                  {sourceDocInfo?.version_label} Evidence
                                </h5>
                                {f.source_evidence?.length ? (
                                  f.source_evidence.map((ev, idx) => (
                                    <div key={idx} className="bg-slate-950/30 rounded-lg p-2 border border-white/5 text-[10px] leading-normal text-slate-400 space-y-1">
                                      <div className="flex justify-between items-center text-slate-500 text-[9px] font-mono">
                                        <span>Page {ev.page}</span>
                                        <button
                                          onClick={() => setLightbox({
                                            src: pageImageUrl(ev.doc_id, ev.page),
                                            title: `${sourceDocInfo?.filename} - page ${ev.page}`,
                                            docId: ev.doc_id,
                                            page: ev.page,
                                            query: selectedDiffQuery,
                                          })}
                                          className="text-cyan-400/80 hover:text-cyan-300 flex items-center gap-0.5"
                                        >
                                          Image
                                          <ExternalLink size={8} />
                                        </button>
                                      </div>
                                      <p className="line-clamp-3 italic">"{ev.text}"</p>
                                    </div>
                                  ))
                                ) : (
                                  <p className="text-[10px] text-slate-600 italic">No corresponding section found.</p>
                                )}
                              </div>

                              <div>
                                <h5 className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">
                                  {targetDocInfo?.version_label} Evidence
                                </h5>
                                {f.target_evidence?.length ? (
                                  f.target_evidence.map((ev, idx) => (
                                    <div key={idx} className="bg-slate-950/30 rounded-lg p-2 border border-white/5 text-[10px] leading-normal text-slate-400 space-y-1">
                                      <div className="flex justify-between items-center text-slate-500 text-[9px] font-mono">
                                        <span>Page {ev.page}</span>
                                        <button
                                          onClick={() => setLightbox({
                                            src: pageImageUrl(ev.doc_id, ev.page),
                                            title: `${targetDocInfo?.filename} - page ${ev.page}`,
                                            docId: ev.doc_id,
                                            page: ev.page,
                                            query: selectedDiffQuery,
                                          })}
                                          className="text-cyan-400/80 hover:text-cyan-300 flex items-center gap-0.5"
                                        >
                                          Image
                                          <ExternalLink size={8} />
                                        </button>
                                      </div>
                                      <p className="line-clamp-3 italic">"{ev.text}"</p>
                                    </div>
                                  ))
                                ) : (
                                  <p className="text-[10px] text-slate-600 italic">No corresponding section found.</p>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              )}
            </div>

          </div>
        )}
      </div>

      {lightbox && (
        <ImageLightbox
          src={lightbox.src}
          alt={lightbox.title}
          title={lightbox.title}
          docId={lightbox.docId}
          pageNum={lightbox.page}
          query={lightbox.query}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
}

function diffQueryForFinding(finding: CompareFinding) {
  const text = [
    finding.title,
    finding.description,
    ...finding.source_evidence.map((item) => item.text),
    ...finding.target_evidence.map((item) => item.text),
  ].join(" ");
  const terms: string[] = [];
  for (const match of text.matchAll(/[A-Za-z0-9][A-Za-z0-9./:-]{2,}/g)) {
    const term = match[0].toLowerCase().replace(/^[^a-z0-9]+|[^a-z0-9]+$/g, "");
    if (!term || DIFF_TERM_STOPWORDS.has(term) || terms.includes(term)) continue;
    terms.push(term);
    if (terms.length === 12) break;
  }
  return terms.join(" ");
}
