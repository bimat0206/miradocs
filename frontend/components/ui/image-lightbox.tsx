"use client";

import { ChevronLeft, ChevronRight, Loader2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { getPageImageMatches } from "@/lib/api";
import type { PageImageMatch } from "@/lib/types";

interface ImageLightboxProps {
  src: string;
  alt: string;
  title?: string;
  docId?: string;
  pageNum?: number;
  query?: string;
  onClose: () => void;
}

export function ImageLightbox({ src, alt, title, docId, pageNum, query = "", onClose }: ImageLightboxProps) {
  const [matches, setMatches] = useState<PageImageMatch[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [isLoadingMatches, setIsLoadingMatches] = useState(false);
  const [matchError, setMatchError] = useState<string | null>(null);
  const activeMatchRef = useRef<HTMLSpanElement | null>(null);
  const canLoadMatches = Boolean(docId && pageNum && query.trim().length >= 2);
  const hasMatches = matches.length > 0;

  useEffect(() => {
    let cancelled = false;
    setActiveIndex(0);
    setMatches([]);
    setMatchError(null);

    if (!canLoadMatches || !docId || !pageNum) return;

    setIsLoadingMatches(true);
    getPageImageMatches(docId, pageNum, query)
      .then((response) => {
        if (!cancelled) setMatches(response.matches);
      })
      .catch((error: Error) => {
        if (!cancelled) setMatchError(error.message || "Unable to load image matches");
      })
      .finally(() => {
        if (!cancelled) setIsLoadingMatches(false);
      });

    return () => {
      cancelled = true;
    };
  }, [canLoadMatches, docId, pageNum, query]);

  useEffect(() => {
    activeMatchRef.current?.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
  }, [activeIndex]);

  const moveMatch = (direction: -1 | 1) => {
    if (!hasMatches) return;
    setActiveIndex((current) => (current + direction + matches.length) % matches.length);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={title ?? alt}
      onClick={onClose}
    >
      <div
        className="flex max-h-full w-full max-w-6xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-slate-950"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
          <p className="min-w-0 truncate text-sm font-medium text-slate-100">{title ?? alt}</p>
          <div className="flex items-center gap-2">
            {canLoadMatches && (
              <div className="flex h-9 items-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-2 text-xs text-slate-300">
                {isLoadingMatches ? (
                  <>
                    <Loader2 size={14} className="animate-spin text-cyan-200" />
                    Matching
                  </>
                ) : (
                  <span>{hasMatches ? `${activeIndex + 1}/${matches.length} matches` : "0 matches"}</span>
                )}
                <button
                  type="button"
                  onClick={() => moveMatch(-1)}
                  disabled={!hasMatches}
                  className="flex h-7 w-7 items-center justify-center rounded-lg border border-white/10 bg-black/25 text-slate-200 transition hover:border-cyan-300/40 hover:text-cyan-100 disabled:cursor-not-allowed disabled:opacity-35"
                  aria-label="Previous matching term"
                >
                  <ChevronLeft size={15} />
                </button>
                <button
                  type="button"
                  onClick={() => moveMatch(1)}
                  disabled={!hasMatches}
                  className="flex h-7 w-7 items-center justify-center rounded-lg border border-white/10 bg-black/25 text-slate-200 transition hover:border-cyan-300/40 hover:text-cyan-100 disabled:cursor-not-allowed disabled:opacity-35"
                  aria-label="Next matching term"
                >
                  <ChevronRight size={15} />
                </button>
              </div>
            )}
            <button
              type="button"
              onClick={onClose}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-slate-300 transition hover:border-cyan-300/40 hover:text-cyan-100"
              aria-label="Close image preview"
            >
              <X size={17} />
            </button>
          </div>
        </div>
        <div className="thin-scrollbar flex min-h-0 flex-1 items-center justify-center overflow-auto p-4">
          <div className="relative inline-block">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={src} alt={alt} className="block max-h-[82vh] max-w-full object-contain" />
            {matches.map((match, index) => {
              const isActive = index === activeIndex;
              return (
                <span
                  key={`${match.term}-${index}-${match.x}-${match.y}`}
                  ref={isActive ? activeMatchRef : null}
                  className={`absolute rounded-[2px] border transition ${
                    isActive
                      ? "border-amber-100 bg-amber-300/45 shadow-[0_0_0_2px_rgba(251,191,36,0.35)]"
                      : "border-cyan-100/60 bg-cyan-300/25"
                  }`}
                  style={{
                    left: `${match.x * 100}%`,
                    top: `${match.y * 100}%`,
                    width: `${match.width * 100}%`,
                    height: `${match.height * 100}%`,
                  }}
                  title={match.text}
                />
              );
            })}
          </div>
        </div>
        {matchError && (
          <p className="shrink-0 border-t border-red-400/20 bg-red-500/10 px-4 py-2 text-xs text-red-100">
            {matchError}
          </p>
        )}
      </div>
    </div>
  );
}
