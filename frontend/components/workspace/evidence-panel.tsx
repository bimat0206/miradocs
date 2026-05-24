"use client";

import { useState } from "react";

import { ImageLightbox } from "@/components/ui/image-lightbox";
import { figureImageUrl, pageImageUrl } from "@/lib/api";
import type { SearchResult } from "@/lib/types";

interface EvidencePanelProps {
  evidence: NonNullable<SearchResult["evidence"]>;
  docId: string;
}

export function EvidencePanel({ evidence, docId }: EvidencePanelProps) {
  const [largeImage, setLargeImage] = useState<{ src: string; title: string } | null>(null);

  return (
    <div className="border-t border-white/10 bg-black/20 p-4 space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        {/* Page image */}
        {evidence.page_image && (
          <div>
            <p className="mb-1 text-xs uppercase tracking-wider text-slate-500">
              Page {evidence.page_number}
            </p>
            <button
              type="button"
              onClick={() =>
                setLargeImage({
                  src: pageImageUrl(docId, evidence.page_number),
                  title: `Page ${evidence.page_number}`,
                })
              }
              className="block rounded-xl transition hover:ring-2 hover:ring-cyan-300/35"
              aria-label={`View page ${evidence.page_number} larger`}
            >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={pageImageUrl(docId, evidence.page_number)}
              alt={`Page ${evidence.page_number}`}
              className="max-h-48 rounded-xl border border-white/10 object-contain bg-black/25"
            />
            </button>
          </div>
        )}
        {/* Cropped diagram */}
        {evidence.cropped_diagram && (
          <div>
            <p className="mb-1 text-xs uppercase tracking-wider text-slate-500">
              {evidence.figure_number ?? "Figure"}
            </p>
            <button
              type="button"
              onClick={() =>
                setLargeImage({
                  src: figureImageUrl(
                    docId,
                    evidence.figure_number?.replace(/[^a-z0-9_]/gi, "_") ?? "unknown",
                  ),
                  title: evidence.figure_number ?? "Figure",
                })
              }
              className="block rounded-xl transition hover:ring-2 hover:ring-cyan-300/35"
              aria-label="View figure larger"
            >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={figureImageUrl(
                docId,
                evidence.figure_number?.replace(/[^a-z0-9_]/gi, "_") ?? "unknown",
              )}
              alt="Diagram"
              className="max-h-48 rounded-xl border border-white/10 object-contain bg-black/25"
            />
            </button>
          </div>
        )}
      </div>
      <div className="grid gap-2 text-sm">
        {evidence.caption && (
          <div>
            <span className="text-xs text-slate-500">Caption:</span>{" "}
            <span className="text-slate-300">{evidence.caption}</span>
          </div>
        )}
        {evidence.ocr_text && (
          <div>
            <span className="text-xs text-slate-500">OCR:</span>{" "}
            <span className="text-slate-300">{evidence.ocr_text}</span>
          </div>
        )}
        <div>
          <span className="text-xs text-slate-500">Section:</span>{" "}
          <span className="text-slate-300">{evidence.section_path}</span>
        </div>
        {evidence.nearby_text && (
          <details className="text-xs">
            <summary className="cursor-pointer text-slate-500 hover:text-slate-300">Nearby text</summary>
            <p className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap text-slate-400">
              {evidence.nearby_text.slice(0, 800)}
            </p>
          </details>
        )}
      </div>
      {largeImage && (
        <ImageLightbox
          src={largeImage.src}
          alt={largeImage.title}
          title={largeImage.title}
          onClose={() => setLargeImage(null)}
        />
      )}
    </div>
  );
}
