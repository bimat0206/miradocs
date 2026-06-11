"""Version diff service — wrapper around compare_service for version-to-version diffs."""
from pathlib import Path

from src.intake.document_registry import DocumentRegistry
from src.services.compare_service import CompareError, run_compare


class VersionDiffError(Exception):
    """Raised when a version comparison cannot be performed."""


def compare_versions(
    *,
    group_id: str,
    source_version: int,
    target_version: int,
    registry: DocumentRegistry,
    data_dir: Path,
) -> dict:
    """Run a semantic version diff between two versions of a document group.

    Args:
        group_id: ID of the document group.
        source_version: version_number of the older (source) version.
        target_version: version_number of the newer (target) version.
        registry: DocumentRegistry instance.
        data_dir: Path to the data directory.

    Returns:
        Compare run dict enriched with version labels and group_id.

    Raises:
        VersionDiffError: If versions are invalid, identical, or belong to different groups.
    """
    if source_version == target_version:
        raise VersionDiffError("source_version and target_version must differ")

    source_ver = registry.get_version(group_id, source_version)
    if not source_ver:
        raise VersionDiffError(
            f"Version {source_version} not found in group {group_id}"
        )

    target_ver = registry.get_version(group_id, target_version)
    if not target_ver:
        raise VersionDiffError(
            f"Version {target_version} not found in group {group_id}"
        )

    source_doc_id = source_ver["doc_id"]
    target_doc_id = target_ver["doc_id"]

    try:
        compare_result = run_compare(
            source_doc_id=source_doc_id,
            target_doc_id=target_doc_id,
            mode="version_diff",
            registry=registry,
            data_dir=data_dir,
        )
    except CompareError as exc:
        raise VersionDiffError(str(exc)) from exc

    source_label = source_ver.get("version_label", f"v{source_version}")
    target_label = target_ver.get("version_label", f"v{target_version}")

    return {
        **compare_result,
        "group_id": group_id,
        "source_version": source_ver,
        "target_version": target_ver,
        "version_label": f"{source_label} -> {target_label}",
    }
