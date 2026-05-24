"""Markdown exporter for document artifacts."""
from pathlib import Path

from src.normalization.document_object import DocumentStructure


def export_parse_summary(doc_id: str, structure: DocumentStructure, output_dir: Path) -> Path:
    """Generate parse_summary.md with section tree and page stats."""
    lines = [f"# Parse Summary: {doc_id}\n"]

    lines.append(f"## Pages: {len(structure.pages)}\n")

    lines.append("## Section Tree\n")
    for sec in structure.sections:
        indent = "  " * (sec.level - 1)
        lines.append(f"{indent}- {sec.title} (pp. {sec.page_start}-{sec.page_end})")

    lines.append("\n## Page Artifacts\n")
    tables_count = sum(len(p.tables) for p in structure.pages)
    figures_count = sum(len(p.figures) for p in structure.pages)
    lines.append(f"- Tables: {tables_count}")
    lines.append(f"- Figures: {figures_count}")
    lines.append(f"- Pages with images: {sum(1 for p in structure.pages if p.image_path)}")

    output_path = output_dir / "parse_summary.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
