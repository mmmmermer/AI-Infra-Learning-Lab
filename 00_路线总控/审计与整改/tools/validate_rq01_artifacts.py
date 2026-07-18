from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_RELATIVE = Path(
    "60_科研训练/研究项目/RQ01_RAG_Agent请求调度尾延迟/"
    "artifacts/rq01_e2_pilot_20260711"
)
HASH_LINE = re.compile(r"^(?P<digest>[0-9a-f]{64})  (?P<path>.+)$")
SOURCE_ARCHIVE_PREFIX = PurePosixPath(
    "50_项目产出/P01_Mini_Scheduler/mini_scheduler"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate RQ01 pilot checksums and source archive.")
    parser.add_argument("root", nargs="?", type=Path, default=ROOT)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def sha256_stream(handle) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return sha256_stream(handle)


def load_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        match = HASH_LINE.fullmatch(raw_line)
        if not match:
            raise ValueError(f"{path.name}:{line_number}: invalid SHA-256 manifest line")
        relative = PurePosixPath(match.group("path").replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts or str(relative) in entries:
            raise ValueError(f"{path.name}:{line_number}: unsafe or duplicate path {relative}")
        entries[str(relative)] = match.group("digest")
    return entries


def validate(root: Path) -> dict[str, object]:
    artifact = root / ARTIFACT_RELATIVE
    errors: list[str] = []
    checked_files = 0
    checked_members = 0
    try:
        manifest = load_manifest(artifact / "checksums.sha256")
        published_files = {
            path.name
            for path in artifact.iterdir()
            if path.is_file() and path.name not in {"checksums.sha256", "stdout.log"}
        }
        if set(manifest) != published_files:
            errors.append(
                "checksums.sha256 coverage mismatch: "
                f"missing={sorted(published_files - set(manifest))}, "
                f"extra={sorted(set(manifest) - published_files)}"
            )
        for relative, expected in manifest.items():
            path = artifact / relative
            if not path.is_file():
                errors.append(f"checksums.sha256 references missing file: {relative}")
                continue
            checked_files += 1
            actual = sha256_file(path)
            if actual != expected:
                errors.append(f"SHA-256 mismatch for {relative}: expected {expected}, got {actual}")

        source_manifest = load_manifest(artifact / "source_snapshot_files.sha256")
        archive_entries: dict[str, str] = {}
        with tarfile.open(artifact / "source_snapshot.tar.gz", mode="r:gz") as archive:
            for member in archive.getmembers():
                relative = PurePosixPath(member.name.replace("\\", "/"))
                if relative.is_absolute() or ".." in relative.parts:
                    errors.append(f"unsafe source archive member: {member.name}")
                    continue
                if not member.isfile():
                    errors.append(f"non-file source archive member: {member.name}")
                    continue
                prefix_parts = SOURCE_ARCHIVE_PREFIX.parts
                if relative.parts[: len(prefix_parts)] != prefix_parts:
                    errors.append(
                        f"source archive member is outside {SOURCE_ARCHIVE_PREFIX}: {member.name}"
                    )
                    continue
                stripped = PurePosixPath(*relative.parts[len(prefix_parts) :])
                if not stripped.parts or str(stripped) in archive_entries:
                    errors.append(f"empty or duplicate source archive member: {member.name}")
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    errors.append(f"cannot read source archive member: {member.name}")
                    continue
                archive_entries[str(stripped)] = sha256_stream(extracted)
                checked_members += 1
        if set(archive_entries) != set(source_manifest):
            errors.append(
                "source archive coverage mismatch: "
                f"missing={sorted(set(source_manifest) - set(archive_entries))}, "
                f"extra={sorted(set(archive_entries) - set(source_manifest))}"
            )
        for relative, expected in source_manifest.items():
            actual = archive_entries.get(relative)
            if actual is not None and actual != expected:
                errors.append(
                    f"source archive SHA-256 mismatch for {relative}: expected {expected}, got {actual}"
                )
    except (OSError, UnicodeError, ValueError, tarfile.TarError) as error:
        errors.append(str(error))
    return {
        "status": "failed" if errors else "passed",
        "artifact": ARTIFACT_RELATIVE.as_posix(),
        "checked_files": checked_files,
        "checked_archive_members": checked_members,
        "errors": errors,
    }


def main() -> int:
    args = parse_args()
    report = validate(args.root.resolve())
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(payload + "\n", encoding="utf-8")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
