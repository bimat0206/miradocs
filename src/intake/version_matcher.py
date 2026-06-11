"""Filename normalization and fuzzy group matching for version auto-grouping."""
import re
from difflib import SequenceMatcher
from pathlib import Path


_VERSION_RE = re.compile(
    r"""^(
        v\d+(\.\d+)*     |  # v1, v2.1, v2.1.3
        rev\d*           |  # rev2, rev
        r\d+             |  # r3
        rc\d*            |  # rc1, rc
        draft\d*         |  # draft, draft3
        final            |
        wip              |
        approved         |
        release          |
        \d{4}-\d{2}-\d{2}|  # 2024-01-15
        \d{8}            |  # 20240115
        \d{2}-\d{2}-\d{4}   # 15-01-2024
    )$""",
    re.VERBOSE,
)


def normalise_filename(filename: str) -> str:
    """Strip extension, version/date/state suffix tokens, return lowercase stem.

    Examples:
        "SRS_v2.1_FINAL.docx"                       -> "srs"
        "Architecture Design - Draft 3.pdf"         -> "architecture design"
        "HLD_2024-01-15.docx"                       -> "hld"
        "network-connectivity-request-workflow.md"  -> "network connectivity request workflow"
        "Design_r3.pdf"                             -> "design"
        "spec_rev2_20231101.pdf"                    -> "spec"
    """
    stem = Path(filename).stem.lower()
    # Split on any separator (dash, underscore, space)
    tokens = re.split(r"[-_\s]+", stem)

    kept = []
    for tok in tokens:
        if not tok:
            continue
        # Skip version/date/state tokens
        if _VERSION_RE.match(tok):
            continue
        # Skip bare numbers
        if re.fullmatch(r"\d+", tok):
            continue
        kept.append(tok)

    return " ".join(kept).strip()


def auto_match_group(
    filename: str,
    project: str,
    registry,
    threshold: float = 0.80,
) -> str | None:
    """Return the group_id of the best-matching existing group above threshold, or None.

    Uses SequenceMatcher ratio on normalised filename stems.
    Only matches against groups in the same project.
    """
    needle = normalise_filename(filename)
    if not needle:
        return None

    groups = registry.list_groups(project=project)
    best_ratio = 0.0
    best_group_id = None

    for group in groups:
        haystack = group.get("base_filename", "")
        ratio = SequenceMatcher(None, needle, haystack).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_group_id = group["group_id"]

    if best_ratio >= threshold:
        return best_group_id
    return None
