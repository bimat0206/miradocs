"use client";

import * as Tabs from "@radix-ui/react-tabs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Activity, CheckCircle2, Database, Eye, Lock, Tags } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { LibraryPanel } from "./workspace/library-panel";

import { WorkspaceHeader } from "./workspace/workspace-header";
import { ProcessView } from "./workspace/process-view";
import { InspectView } from "./workspace/inspect-view";
import { IndexView } from "./workspace/index-view";
import { TagsView } from "./workspace/tags-view";
import { CompareView } from "./workspace/compare-view";
import { CrossDocumentSearchView } from "./workspace/cross-document-search-view";
import { AboutView } from "./workspace/about-view";
import { GuideView } from "./workspace/guide-view";
import {
  detectCompareMode,
  deleteDocument,
  getActivePipeline,
  getDocument,
  getIndexStatus,
  getPipeline,
  getPipelineRuns,
  indexDocument,
  jobEventsUrl,
  listDocuments,
  runCompare,
  runPipeline,
  search,
  updateDocumentTags,
  uploadDocument,
} from "@/lib/api";
import { useWorkspaceStore } from "@/lib/store";
import type { CompareMode, JobEvent } from "@/lib/types";
import type { WorkflowTab } from "@/lib/workflow";

import {
  canRunPipeline,
  livePipelineProgress,
  mergeJobEvents,
  pipelineProgress,
  processingComplete,
} from "@/lib/workflow";

const workflowNav: Array<{
  value: WorkflowTab;
  label: string;
  detail: string;
  Icon: typeof Activity;
  accent: {
    active: string;
    icon: string;
    text: string;
    hover: string;
  };
}> = [
  {
    value: "Process",
    label: "Process",
    detail: "Run extraction",
    Icon: Activity,
    accent: {
      active: "data-[state=active]:border-cyan-300/60 data-[state=active]:bg-cyan-300/10",
      icon: "group-data-[state=active]:border-cyan-300/45 group-data-[state=active]:bg-cyan-300/15 group-data-[state=active]:text-cyan-100",
      text: "group-data-[state=active]:text-cyan-100/80",
      hover: "group-hover:border-cyan-300/30 group-hover:text-cyan-100",
    },
  },
  {
    value: "Tags",
    label: "Tag",
    detail: "Organize document",
    Icon: Tags,
    accent: {
      active: "data-[state=active]:border-emerald-300/60 data-[state=active]:bg-emerald-300/10",
      icon: "group-data-[state=active]:border-emerald-300/45 group-data-[state=active]:bg-emerald-300/15 group-data-[state=active]:text-emerald-100",
      text: "group-data-[state=active]:text-emerald-100/80",
      hover: "group-hover:border-emerald-300/30 group-hover:text-emerald-100",
    },
  },
  {
    value: "Inspect",
    label: "Inspect",
    detail: "Review pages",
    Icon: Eye,
    accent: {
      active: "data-[state=active]:border-amber-300/60 data-[state=active]:bg-amber-300/10",
      icon: "group-data-[state=active]:border-amber-300/45 group-data-[state=active]:bg-amber-300/15 group-data-[state=active]:text-amber-100",
      text: "group-data-[state=active]:text-amber-100/80",
      hover: "group-hover:border-amber-300/30 group-hover:text-amber-100",
    },
  },
  {
    value: "Index",
    label: "Index",
    detail: "Search evidence",
    Icon: Database,
    accent: {
      active: "data-[state=active]:border-violet-300/60 data-[state=active]:bg-violet-300/10",
      icon: "group-data-[state=active]:border-violet-300/45 group-data-[state=active]:bg-violet-300/15 group-data-[state=active]:text-violet-100",
      text: "group-data-[state=active]:text-violet-100/80",
      hover: "group-hover:border-violet-300/30 group-hover:text-violet-100",
    },
  },
];

export function Workspace() {
  const queryClient = useQueryClient();
  const {
    selectedDocId,
    setSelectedDocId,
    selectedDocIds,
    setSelectedDocIds,
    activeTab,
    setActiveTab,
  } = useWorkspaceStore();

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [logsByDoc, setLogsByDoc] = useState<Record<string, JobEvent[]>>({});
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchHybrid, setSearchHybrid] = useState(true);
  const [searchRerank, setSearchRerank] = useState(false);
  const [compareDocIds, setCompareDocIds] = useState<[string, string] | null>(null);
  const [crossSearchDocIds, setCrossSearchDocIds] = useState<[string, string] | null>(null);
  const [crossSearchQuery, setCrossSearchQuery] = useState("");
  const [crossSearchHybrid, setCrossSearchHybrid] = useState(true);
  const [crossSearchRerank, setCrossSearchRerank] = useState(false);
  const [compareMode, setCompareMode] = useState<CompareMode>("auto");
  const [showAbout, setShowAbout] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const eventSourceJobIdRef = useRef<string | null>(null);

  const documentsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
    refetchInterval: false,
  });
  const documents = documentsQuery.data?.documents ?? [];
  const selectedDoc = useMemo(
    () => documents.find((doc) => doc.doc_id === selectedDocId) ?? documents[0] ?? null,
    [documents, selectedDocId],
  );
  const compareDocs = useMemo(() => {
    if (!compareDocIds) return null;
    const source = documents.find((doc) => doc.doc_id === compareDocIds[0]);
    const target = documents.find((doc) => doc.doc_id === compareDocIds[1]);
    return source && target ? { source, target } : null;
  }, [compareDocIds, documents]);
  const crossSearchDocs = useMemo(() => {
    if (!crossSearchDocIds) return null;
    const left = documents.find((doc) => doc.doc_id === crossSearchDocIds[0]);
    const right = documents.find((doc) => doc.doc_id === crossSearchDocIds[1]);
    return left && right ? { left, right } : null;
  }, [crossSearchDocIds, documents]);

  useEffect(() => {
    if (!selectedDocId && selectedDoc) setSelectedDocId(selectedDoc.doc_id);
  }, [selectedDoc, selectedDocId, setSelectedDocId]);

  useEffect(() => {
    if (compareDocIds && documents.length > 0 && !compareDocs) {
      setCompareDocIds(null);
    }
    if (crossSearchDocIds && documents.length > 0 && !crossSearchDocs) {
      setCrossSearchDocIds(null);
    }
  }, [compareDocIds, compareDocs, crossSearchDocIds, crossSearchDocs, documents.length]);

  const sseConnected = Boolean(eventSourceRef.current);

  const documentQuery = useQuery({
    queryKey: ["document", selectedDoc?.doc_id],
    queryFn: () => getDocument(selectedDoc!.doc_id),
    enabled: Boolean(selectedDoc),
    refetchInterval: false,
  });
  const pipelineQuery = useQuery({
    queryKey: ["pipeline", selectedDoc?.doc_id],
    queryFn: () => getPipeline(selectedDoc!.doc_id),
    enabled: Boolean(selectedDoc),
    refetchInterval: false,
  });
  const runsQuery = useQuery({
    queryKey: ["pipeline-runs", selectedDoc?.doc_id],
    queryFn: () => getPipelineRuns(selectedDoc!.doc_id),
    enabled: Boolean(selectedDoc),
    refetchInterval: false,
  });
  const activePipelineQuery = useQuery({
    queryKey: ["pipeline-active", selectedDoc?.doc_id],
    queryFn: () => getActivePipeline(selectedDoc!.doc_id),
    enabled: Boolean(selectedDoc) && activeTab === "Process",
    refetchInterval: activeTab === "Process" && !sseConnected ? 3000 : false,
  });
  const indexStatusQuery = useQuery({
    queryKey: ["index-status", selectedDoc?.doc_id],
    queryFn: () => getIndexStatus(selectedDoc!.doc_id),
    enabled: Boolean(selectedDoc) && activeTab === "Index",
    refetchInterval: activeTab === "Index" ? 5000 : false,
  });

  const steps = activePipelineQuery.data?.steps ?? pipelineQuery.data?.steps ?? documentQuery.data?.pipeline_steps ?? [];
  const runs = runsQuery.data?.runs ?? [];
  const logs = selectedDoc ? logsByDoc[selectedDoc.doc_id] ?? [] : [];
  const progress = pipelineProgress(steps);
  const displayProgress = livePipelineProgress(progress, logs);
  const processReady = processingComplete(steps);
  const pipelineCanRun = canRunPipeline(steps);
  const latestProgressLog = [...logs]
    .reverse()
    .find((log) => log.type === "progress" || typeof log.elapsed_seconds === "number");
  const pipelineRuntime = {
    elapsed_seconds: latestProgressLog?.elapsed_seconds ?? null,
    eta_seconds: latestProgressLog?.eta_seconds ?? null,
    label: latestProgressLog?.label ?? latestProgressLog?.message ?? null,
  };
  const activePipelineRunning = activePipelineQuery.data?.status === "queued" || activePipelineQuery.data?.status === "running";
  const selectedTagCount = (documentQuery.data ?? selectedDoc)?.tags?.length ?? 0;

  const appendLogs = useCallback((docId: string, events: JobEvent[]) => {
    if (events.length === 0) return;
    setLogsByDoc((current) => ({
      ...current,
      [docId]: mergeJobEvents(current[docId] ?? [], events),
    }));
  }, []);

  const closeEventSource = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    eventSourceJobIdRef.current = null;
  }, []);

  const connectToJob = useCallback((jobId: string, docId: string) => {
    if (eventSourceJobIdRef.current === jobId) return;
    closeEventSource();
    const events = new EventSource(jobEventsUrl(jobId));
    eventSourceRef.current = events;
    eventSourceJobIdRef.current = jobId;
    ["queued", "running", "progress", "done", "failed"].forEach((type) => {
      events.addEventListener(type, (event) => {
        const payload = JSON.parse((event as MessageEvent).data) as JobEvent;
        appendLogs(payload.doc_id || docId, [payload]);
        if (payload.type === "done" || payload.type === "failed") {
          closeEventSource();
          queryClient.invalidateQueries({ queryKey: ["pipeline", payload.doc_id] });
          queryClient.invalidateQueries({ queryKey: ["pipeline-active", payload.doc_id] });
          queryClient.invalidateQueries({ queryKey: ["pipeline-runs", payload.doc_id] });
          queryClient.invalidateQueries({ queryKey: ["documents"] });
        }
      });
    });
  }, [appendLogs, closeEventSource, queryClient]);

  useEffect(() => {
    const active = activePipelineQuery.data;
    if (!selectedDoc || !active) return;
    appendLogs(selectedDoc.doc_id, active.events);
    if (active.job_id) {
      connectToJob(active.job_id, selectedDoc.doc_id);
    } else if (eventSourceRef.current) {
      closeEventSource();
    }
  }, [activePipelineQuery.data, appendLogs, closeEventSource, connectToJob, selectedDoc]);

  useEffect(() => closeEventSource, [closeEventSource]);

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      form.append("project", "default");
      return uploadDocument(form);
    },
    onSuccess: (doc) => {
      setSelectedDocId(doc.doc_id);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (docIds: string[]) => {
      return Promise.all(docIds.map((id) => deleteDocument(id)));
    },
    onSuccess: (_, deletedIds) => {
      if (selectedDocId && deletedIds.includes(selectedDocId)) {
        setSelectedDocId(null);
      }
      if (compareDocIds?.some((docId) => deletedIds.includes(docId))) {
        setCompareDocIds(null);
      }
      if (crossSearchDocIds?.some((docId) => deletedIds.includes(docId))) {
        setCrossSearchDocIds(null);
      }
      setSelectedDocIds([]);
      setLogsByDoc((current) => {
        const next = { ...current };
        deletedIds.forEach((docId) => delete next[docId]);
        return next;
      });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const runMutation = useMutation({
    mutationFn: runPipeline,
    onSuccess: ({ job_id }, docId) => {
      setLogsByDoc((current) => ({ ...current, [docId]: [] }));
      connectToJob(job_id, docId);
      queryClient.invalidateQueries({ queryKey: ["pipeline-active", docId] });
    },
  });

  const indexMutation = useMutation({
    mutationFn: indexDocument,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pipeline", selectedDoc?.doc_id] });
      queryClient.invalidateQueries({ queryKey: ["index-status", selectedDoc?.doc_id] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const tagsMutation = useMutation({
    mutationFn: ({ docId, tags }: { docId: string; tags: string[] }) => updateDocumentTags(docId, tags),
    onSuccess: (doc) => {
      queryClient.setQueryData(["document", doc.doc_id], doc);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const searchMutation = useMutation({
    mutationFn: () =>
      search(selectedDoc?.doc_id ? [selectedDoc.doc_id] : [], searchQuery, 12, { hybrid: searchHybrid, rerank: searchRerank }),
  });

  const crossSearchMutation = useMutation({
    mutationFn: () =>
      search(crossSearchDocIds ?? [], crossSearchQuery, 24, { hybrid: crossSearchHybrid, rerank: crossSearchRerank }),
  });

  const detectCompareMutation = useMutation({
    mutationFn: ({ sourceDocId, targetDocId }: { sourceDocId: string; targetDocId: string }) =>
      detectCompareMode(sourceDocId, targetDocId),
    onSuccess: (detection) => {
      setCompareMode(detection.detected_mode);
    },
  });

  const runCompareMutation = useMutation({
    mutationFn: ({ sourceDocId, targetDocId, mode }: { sourceDocId: string; targetDocId: string; mode: CompareMode }) =>
      runCompare(sourceDocId, targetDocId, mode),
  });

  const openAbout = useCallback(() => { setShowAbout(true); setShowGuide(false); setCompareDocIds(null); setCrossSearchDocIds(null); }, []);
  const openGuide = useCallback(() => { setShowGuide(true); setShowAbout(false); setCompareDocIds(null); setCrossSearchDocIds(null); }, []);

  const openCompare = useCallback(() => {
    if (selectedDocIds.length !== 2) return;
    const ids: [string, string] = [selectedDocIds[0], selectedDocIds[1]];
    setCompareDocIds(ids);
    setCrossSearchDocIds(null);
    setCompareMode("auto");
    detectCompareMutation.reset();
    runCompareMutation.reset();
    detectCompareMutation.mutate({ sourceDocId: ids[0], targetDocId: ids[1] });
  }, [detectCompareMutation, runCompareMutation, selectedDocIds]);

  const openCrossSearch = useCallback(() => {
    if (selectedDocIds.length !== 2) return;
    setCrossSearchDocIds([selectedDocIds[0], selectedDocIds[1]]);
    setCompareDocIds(null);
    crossSearchMutation.reset();
  }, [crossSearchMutation, selectedDocIds]);

  const closeCompare = useCallback(() => {
    setCompareDocIds(null);
    setCompareMode("auto");
    detectCompareMutation.reset();
    runCompareMutation.reset();
  }, [detectCompareMutation, runCompareMutation]);

  const closeCrossSearch = useCallback(() => {
    setCrossSearchDocIds(null);
    crossSearchMutation.reset();
  }, [crossSearchMutation]);

  const swapCompareDirection = useCallback(() => {
    if (!compareDocIds) return;
    const swapped: [string, string] = [compareDocIds[1], compareDocIds[0]];
    setCompareDocIds(swapped);
    setCompareMode("auto");
    detectCompareMutation.reset();
    runCompareMutation.reset();
    detectCompareMutation.mutate({ sourceDocId: swapped[0], targetDocId: swapped[1] });
  }, [compareDocIds, detectCompareMutation, runCompareMutation]);

  return (
    <main className="min-h-screen lg:h-screen lg:overflow-hidden p-4 lg:p-5 text-slate-100 flex flex-col">
      <div
        className={`mx-auto w-full max-w-[1800px] grid gap-5 flex-1 min-h-0 transition-all duration-300 ${
          sidebarOpen ? "lg:grid-cols-[360px_1fr]" : "lg:grid-cols-[0px_1fr]"
        }`}
      >
        <div
          className={`overflow-hidden transition-all duration-300 ${
            sidebarOpen ? "lg:w-[360px] opacity-100" : "h-0 lg:h-auto lg:w-0 opacity-0 pointer-events-none"
          }`}
        >
          <LibraryPanel
            documents={documents}
            selectedDocId={selectedDoc?.doc_id ?? null}
            selectedDocIds={selectedDocIds}
            setSelectedDocIds={setSelectedDocIds}
            fileInput={fileInput}
            onUpload={(file) => uploadMutation.mutate(file)}
            onSelect={setSelectedDocId}
            isUploading={uploadMutation.isPending}
            onDeleteMultiple={(docIds) => deleteMutation.mutate(docIds)}
            onCompare={openCompare}
            onCrossSearch={openCrossSearch}
            onOpenAbout={openAbout}
            onOpenGuide={openGuide}
            onToggle={() => setSidebarOpen(false)}
            onImportComplete={() => queryClient.invalidateQueries({ queryKey: ["documents"] })}
          />
        </div>
        <section className="relative rounded-[28px] glass gradient-border flex flex-col overflow-hidden lg:h-full min-h-[600px] lg:min-h-0">
          {!showAbout && !showGuide && <WorkspaceHeader
            doc={documentQuery.data ?? selectedDoc}
            progress={displayProgress}
            onRun={() => selectedDoc && runMutation.mutate(selectedDoc.doc_id)}
            isRunning={runMutation.isPending || activePipelineRunning || progress.running > 0}
            canRun={pipelineCanRun}
            leadingAction={
              !sidebarOpen && (
                <button
                  type="button"
                  onClick={() => setSidebarOpen(true)}
                  title="Show library panel"
                  className="flex shrink-0 items-center gap-2 self-start rounded-xl border border-white/10 bg-white/[0.06] px-3 py-2 text-xs font-medium text-slate-300 backdrop-blur-sm transition hover:border-cyan-300/40 hover:bg-white/[0.1] hover:text-cyan-100"
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                    <rect x="1" y="1" width="12" height="12" rx="2.5" stroke="currentColor" strokeWidth="1.3"/>
                    <rect x="1" y="1" width="4" height="12" rx="2.5" fill="currentColor" opacity="0.3"/>
                    <path d="M5 5l3 2-3 2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  Library
                </button>
              )
            }
          />}
          {showAbout ? (
            <div className="flex-1 min-h-0 px-6 pb-6">
              <AboutView onClose={() => setShowAbout(false)} />
            </div>
          ) : showGuide ? (
            <div className="flex-1 min-h-0 px-6 pb-6">
              <GuideView onClose={() => setShowGuide(false)} />
            </div>
          ) : crossSearchDocs ? (
            <div className="flex-1 min-h-0 px-6 pb-6">
              <CrossDocumentSearchView
                leftDoc={crossSearchDocs.left}
                rightDoc={crossSearchDocs.right}
                query={crossSearchQuery}
                setQuery={setCrossSearchQuery}
                hybrid={crossSearchHybrid}
                setHybrid={setCrossSearchHybrid}
                rerank={crossSearchRerank}
                setRerank={setCrossSearchRerank}
                onSearch={() => crossSearchDocIds && crossSearchMutation.mutate()}
                isSearching={crossSearchMutation.isPending}
                results={crossSearchMutation.data?.results ?? []}
                error={crossSearchMutation.error?.message ?? null}
                onClose={closeCrossSearch}
              />
            </div>
          ) : compareDocs ? (
            <div className="flex-1 min-h-0 px-6 pb-6">
              <CompareView
                sourceDoc={compareDocs.source}
                targetDoc={compareDocs.target}
                detection={detectCompareMutation.data ?? null}
                mode={compareMode}
                setMode={setCompareMode}
                onDetect={() => {
                  detectCompareMutation.mutate({
                    sourceDocId: compareDocs.source.doc_id,
                    targetDocId: compareDocs.target.doc_id,
                  });
                }}
                onRun={() => {
                  runCompareMutation.mutate({
                    sourceDocId: compareDocs.source.doc_id,
                    targetDocId: compareDocs.target.doc_id,
                    mode: compareMode,
                  });
                }}
                onSwap={swapCompareDirection}
                onClose={closeCompare}
                isDetecting={detectCompareMutation.isPending}
                isRunning={runCompareMutation.isPending}
                result={runCompareMutation.data ?? null}
                error={(detectCompareMutation.error ?? runCompareMutation.error)?.message ?? null}
              />
            </div>
          ) : (
            <Tabs.Root
              value={activeTab}
              onValueChange={(value) => {
                if (value === "Process" || value === "Tags" || processReady) setActiveTab(value as typeof activeTab);
              }}
              className="px-6 pb-6 flex-1 min-h-0 flex flex-col"
            >
              <Tabs.List className="mb-5 grid w-full shrink-0 grid-cols-1 gap-2 rounded-2xl border border-white/10 bg-black/20 p-2 sm:grid-cols-2 xl:grid-cols-4">
                {workflowNav.map(({ value, label, detail, Icon, accent }, index) => {
                  const disabled = value !== "Process" && value !== "Tags" && !processReady;
                  const statusLabel =
                    value === "Process"
                      ? activePipelineRunning
                        ? "Running"
                        : processReady
                        ? "Complete"
                        : "Ready"
                      : value === "Tags"
                      ? `${selectedTagCount}/5 tags`
                      : disabled
                      ? "Locked"
                      : "Ready";
                  return (
                    <Tabs.Trigger
                      key={value}
                      value={value}
                      disabled={disabled}
                      className={[
                        "group relative flex min-h-[72px] items-center gap-3 rounded-xl border px-3 py-3 text-left transition-all duration-200",
                        "disabled:cursor-not-allowed disabled:opacity-50",
                        "border-transparent text-slate-400 hover:border-white/15 hover:bg-white/[0.04] hover:text-slate-100",
                        "data-[state=active]:text-slate-50",
                        accent.active,
                        "data-[state=active]:shadow-[0_0_22px_rgba(45,212,191,0.10)]",
                      ].join(" ")}
                    >
                      <span
                        className={[
                          "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border text-slate-300 transition",
                          "border-white/10 bg-white/[0.04]",
                          accent.hover,
                          accent.icon,
                        ].join(" ")}
                      >
                        {disabled ? <Lock size={17} /> : <Icon size={17} />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center justify-between gap-2">
                          <span className="text-sm font-semibold">{label}</span>
                          <span className={`text-[11px] text-slate-500 ${accent.text}`}>
                            {String(index + 1).padStart(2, "0")}
                          </span>
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-slate-500 group-data-[state=active]:text-slate-300">
                          {detail}
                        </span>
                        <span className={`mt-1.5 inline-flex items-center gap-1 text-[11px] text-slate-500 ${accent.text}`}>
                          {statusLabel === "Complete" && <CheckCircle2 size={12} />}
                          {statusLabel}
                        </span>
                      </span>
                    </Tabs.Trigger>
                  );
                })}
              </Tabs.List>
              <div className="flex-1 min-h-0 overflow-hidden">
                <AnimatePresence mode="wait">
                  <motion.div
                    key={activeTab}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.22 }}
                    className="h-full"
                  >
                    <Tabs.Content value="Process" className="h-full min-h-0">
                      <ProcessView
                        steps={steps}
                        progress={displayProgress}
                        runtime={pipelineRuntime}
                        isRunning={runMutation.isPending || activePipelineRunning || progress.running > 0}
                        logs={logs}
                        runs={runs}
                      />
                    </Tabs.Content>
                    <Tabs.Content value="Tags" className="h-full min-h-0">
                      <TagsView
                        doc={documentQuery.data ?? selectedDoc}
                        onSave={(tags) => selectedDoc && tagsMutation.mutate({ docId: selectedDoc.doc_id, tags })}
                        isSaving={tagsMutation.isPending}
                      />
                    </Tabs.Content>
                    <Tabs.Content value="Inspect" className="h-full min-h-0">
                      <InspectView doc={selectedDoc} page={page} setPage={setPage} />
                    </Tabs.Content>
                    <Tabs.Content value="Index" className="h-full min-h-0">
                      <IndexView
                        doc={selectedDoc}
                        indexStatus={indexStatusQuery.data ?? null}
                        onIndex={() => selectedDoc && indexMutation.mutate(selectedDoc.doc_id)}
                        isIndexing={indexMutation.isPending}
                        searchQuery={searchQuery}
                        setSearchQuery={setSearchQuery}
                        searchHybrid={searchHybrid}
                        setSearchHybrid={setSearchHybrid}
                        searchRerank={searchRerank}
                        setSearchRerank={setSearchRerank}
                        onSearch={() => selectedDoc && searchMutation.mutate()}
                        isSearching={searchMutation.isPending}
                        results={searchMutation.data?.results ?? []}
                      />
                    </Tabs.Content>
                  </motion.div>
                </AnimatePresence>
              </div>
            </Tabs.Root>
          )}
        </section>
      </div>
    </main>
  );
}
