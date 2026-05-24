"use client";

import { Plus, Tag, X } from "lucide-react";
import { useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/empty-state";
import type { DocumentRecord } from "@/lib/types";

interface TagsViewProps {
  doc: DocumentRecord | null;
  onSave: (tags: string[]) => void;
  isSaving: boolean;
}

export function TagsView({ doc, onSave, isSaving }: TagsViewProps) {
  const [tags, setTags] = useState<string[]>([]);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setTags(doc?.tags ?? []);
    setDraft("");
  }, [doc?.doc_id, doc?.tags]);

  if (!doc) return <EmptyState title="No document selected" />;

  const addTag = () => {
    const tag = draft.trim();
    if (!tag || tags.length >= 5 || tags.some((item) => item.toLowerCase() === tag.toLowerCase())) return;
    setTags([...tags, tag.slice(0, 32)]);
    setDraft("");
  };

  const removeTag = (tag: string) => {
    setTags(tags.filter((item) => item !== tag));
  };

  const hasChanges = JSON.stringify(tags) !== JSON.stringify(doc.tags ?? []);

  return (
    <section className="flex h-full min-h-[420px] flex-col rounded-3xl border border-white/10 bg-white/[0.035] p-5">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-semibold">
            <Tag size={18} /> Document tags
          </h3>
          <p className="mt-1 text-sm text-slate-400 [overflow-wrap:anywhere]">{doc.filename}</p>
        </div>
        <span className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-slate-400">
          {tags.length}/5
        </span>
      </div>

      <div className="flex max-w-2xl gap-2">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addTag();
            }
          }}
          placeholder="Add tag"
          className="min-w-0 flex-1 rounded-2xl border border-white/10 bg-slate-950/35 px-4 py-3 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-cyan-300/60"
          maxLength={32}
        />
        <button
          type="button"
          onClick={addTag}
          disabled={!draft.trim() || tags.length >= 5}
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-cyan-300 text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Add tag"
        >
          <Plus size={18} />
        </button>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {tags.length === 0 ? (
          <p className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 text-sm text-slate-500">
            No tags yet.
          </p>
        ) : (
          tags.map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => removeTag(tag)}
              className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-cyan-300/25 bg-cyan-300/10 px-3 py-1.5 text-sm text-cyan-100"
            >
              <span className="truncate">{tag}</span>
              <X size={13} />
            </button>
          ))
        )}
      </div>

      <div className="mt-auto flex justify-end pt-6">
        <button
          type="button"
          onClick={() => onSave(tags)}
          disabled={!hasChanges || isSaving}
          className="rounded-2xl bg-white px-4 py-3 text-sm font-medium text-slate-950 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isSaving ? "Saving..." : "Save tags"}
        </button>
      </div>
    </section>
  );
}
