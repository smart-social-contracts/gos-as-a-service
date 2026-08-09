"""Seed codex and extension packages into the file_registry canister.

Mirrors ``realms codex publish`` / ``realms extension publish`` path conventions
without shelling out to the Realms CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

from gaas.file_registry_client import (
    fetch_namespace_hashes,
    publish_namespace,
    upload_file,
)
from gaas.source_build import clone_repo, clone_repo_at_ref
from gaas.versions import resolve_deploy_version

console = Console()

SKIP_EXTENSION_IDS = frozenset({"_shared"})
SKIP_CODEX_IDS = frozenset({"_common", "common"})

from gaas.known import GosCatalog


class CodexSeedError(RuntimeError):
    pass


@dataclass(frozen=True)
class UploadSpec:
    registry_path: str
    local_path: Path | None = None
    content: bytes | None = None


def _read_manifest(source_dir: Path) -> dict:
    manifest_path = source_dir / "manifest.json"
    if not manifest_path.is_file():
        return {}
    with manifest_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _has_codex_packages(root: Path) -> bool:
    if not root.is_dir():
        return False
    for child in root.iterdir():
        if not child.is_dir() or child.name in SKIP_CODEX_IDS:
            continue
        has_backend = (child / "backend").is_dir()
        has_loose_py = any(p.suffix == ".py" for p in child.iterdir())
        if has_backend or has_loose_py:
            return True
    return False


def _has_extension_manifests(root: Path) -> bool:
    if not root.is_dir():
        return False
    for child in root.iterdir():
        if not child.is_dir() or child.name in SKIP_EXTENSION_IDS:
            continue
        if (child / "manifest.json").is_file():
            return True
    return False


def resolve_extensions_root(extensions_repo: Path) -> Path:
    """Return the directory holding per-extension subdirectories."""
    nested = extensions_repo / "extensions" / "extensions"
    flat = extensions_repo / "extensions"

    if _has_extension_manifests(nested):
        return nested
    if _has_extension_manifests(flat):
        return flat
    raise CodexSeedError(
        "no extension manifests found under either of:\n"
        f"  {nested}  (nested realms+submodule layout)\n"
        f"  {flat}  (standalone realms-extensions checkout layout)"
    )


def resolve_codices_root(realms_root: Path) -> Path | None:
    """Locate codices under a Realms checkout (submodule or vendored layout)."""
    nested = realms_root / "codices" / "codices"
    if _has_codex_packages(nested):
        return nested
    flat = realms_root / "codices"
    if _has_codex_packages(flat):
        return flat
    return None


def list_codices(codices_root: Path, only: set[str] | None = None) -> list[Path]:
    if not codices_root.is_dir():
        raise CodexSeedError(f"codices root not found: {codices_root}")
    out: list[Path] = []
    for child in sorted(codices_root.iterdir()):
        if not child.is_dir() or child.name in SKIP_CODEX_IDS:
            continue
        if only and child.name not in only:
            continue
        has_backend = (child / "backend").is_dir()
        has_loose_py = any(p.suffix == ".py" for p in child.iterdir())
        if not (has_backend or has_loose_py):
            continue
        out.append(child)
    return out


def list_extensions(extensions_root: Path, only: set[str] | None = None) -> list[Path]:
    if not extensions_root.is_dir():
        raise CodexSeedError(f"extensions root not found: {extensions_root}")
    out: list[Path] = []
    for child in sorted(extensions_root.iterdir()):
        if not child.is_dir() or child.name in SKIP_EXTENSION_IDS:
            continue
        if not (child / "manifest.json").is_file():
            continue
        if only and child.name not in only:
            continue
        out.append(child)
    return out


def package_namespace(package_id: str, version: str, *, namespace_prefix: str) -> str:
    return f"{namespace_prefix}/{package_id}/{version}"


def is_unified_codex(source_dir: Path, manifest: dict) -> bool:
    return manifest.get("kind") == "codex" and (source_dir / "backend").is_dir()


def _extension_frontend_dist(source_dir: Path) -> Path:
    return source_dir / "frontend-rt" / "dist" / "index.js"


def ensure_extension_frontend_built(source_dir: Path, ext_id: str) -> str | None:
    """Build ``frontend-rt`` when ``package.json`` exists but ``dist/index.js`` does not.

    Returns ``None`` on success (including when no build is needed), or an error
    message string when the npm build fails.
    """
    frontend_rt = source_dir / "frontend-rt"
    package_json = frontend_rt / "package.json"
    dist_index = _extension_frontend_dist(source_dir)

    if not package_json.is_file():
        return None
    if dist_index.is_file():
        return None

    console.print(f"  building frontend for extension {ext_id}...")
    lock = frontend_rt / "package-lock.json"
    install_cmd = (
        ["npm", "ci", "--no-audit", "--no-fund"]
        if lock.is_file()
        else ["npm", "install", "--no-audit", "--no-fund"]
    )
    try:
        subprocess.run(install_cmd, cwd=frontend_rt, check=True)
        subprocess.run(["npm", "run", "build"], cwd=frontend_rt, check=True)
    except subprocess.CalledProcessError as exc:
        return f"npm build failed (exit {exc.returncode})"

    if not dist_index.is_file():
        return "build completed but frontend-rt/dist/index.js is still missing"
    return None


def collect_extension_uploads(source_dir: Path, ext_id: str) -> list[UploadSpec]:
    """File set for ``realms extension publish`` (also used for unified codices)."""
    uploads: list[UploadSpec] = []
    manifest_path = source_dir / "manifest.json"
    if manifest_path.is_file():
        uploads.append(UploadSpec("manifest.json", local_path=manifest_path))

    backend_dir = source_dir / "backend"
    if backend_dir.is_dir():
        for root, _dirs, files in os.walk(backend_dir):
            for fname in sorted(files):
                if not fname.endswith((".py", ".json")):
                    continue
                local = Path(root) / fname
                rel = local.relative_to(backend_dir).as_posix()
                uploads.append(UploadSpec(f"backend/{rel}", local_path=local))

    auto_bundle = source_dir / "frontend-rt" / "dist" / "index.js"
    if auto_bundle.is_file():
        uploads.append(UploadSpec("frontend/dist/index.js", local_path=auto_bundle))

    dist_dir = source_dir / "frontend-rt" / "dist"
    if dist_dir.is_dir():
        for fname in sorted(dist_dir.iterdir()):
            if fname.name == "index.js" or not fname.name.endswith((".js", ".css")):
                continue
            uploads.append(UploadSpec(f"frontend/dist/{fname.name}", local_path=fname))

    i18n_ext_dir = source_dir / "frontend" / "i18n" / "locales" / "extensions" / ext_id
    locales_root = source_dir / "frontend" / "i18n" / "locales"
    i18n_legacy_root = source_dir / "i18n"

    def _collect_i18n(i18n_root: Path, map_rel) -> None:
        for walk_root, _dirs, files in os.walk(i18n_root):
            for fname in sorted(files):
                if not fname.endswith(".json"):
                    continue
                local = Path(walk_root) / fname
                rel = local.relative_to(i18n_root).as_posix()
                registry_rel = map_rel(rel)
                if registry_rel is None:
                    continue
                uploads.append(UploadSpec(f"frontend/i18n/{registry_rel}", local_path=local))

    if i18n_ext_dir.is_dir():
        _collect_i18n(i18n_ext_dir, lambda rel: rel)
    elif locales_root.is_dir():
        ext_prefix = f"extensions/{ext_id}/"

        def _map_shared(rel: str):
            if rel.startswith(ext_prefix):
                return rel[len(ext_prefix) :]
            if rel.startswith("extensions/"):
                return None
            return rel

        _collect_i18n(locales_root, _map_shared)
    elif i18n_legacy_root.is_dir():
        _collect_i18n(i18n_legacy_root, lambda rel: rel)

    return uploads


def collect_legacy_codex_uploads(source_dir: Path, codex_id: str, version: str) -> list[UploadSpec]:
    """File set for legacy ``codex/<id>/<ver>/`` packages (no ``kind: codex``)."""
    uploads: list[UploadSpec] = []
    manifest_path = source_dir / "manifest.json"
    if manifest_path.is_file():
        uploads.append(UploadSpec("manifest.json", local_path=manifest_path))
    else:
        uploads.append(
            UploadSpec(
                "manifest.json",
                content=json.dumps(
                    {
                        "name": codex_id,
                        "version": version,
                        "description": f"Codex package {codex_id}",
                    }
                ).encode(),
            )
        )

    for root, _dirs, files in os.walk(source_dir):
        for fname in sorted(files):
            if not (fname.endswith(".py") or fname.endswith(".json")):
                continue
            local = Path(root) / fname
            if fname == "manifest.json" and local.parent == source_dir:
                continue
            rel = local.relative_to(source_dir).as_posix()
            uploads.append(UploadSpec(rel, local_path=local))

    return uploads


def collect_codex_uploads(source_dir: Path) -> tuple[str, str, str, list[UploadSpec]]:
    """Return (package_id, version, namespace_prefix, uploads) for a codex directory."""
    manifest = _read_manifest(source_dir)
    package_id = manifest.get("id") or source_dir.name
    version = manifest.get("version") or "0.0.0"

    if is_unified_codex(source_dir, manifest):
        return (
            package_id,
            version,
            "ext",
            collect_extension_uploads(source_dir, package_id),
        )

    return (
        package_id,
        version,
        "codex",
        collect_legacy_codex_uploads(source_dir, package_id, version),
    )


def collect_extension_package_uploads(source_dir: Path) -> tuple[str, str, list[UploadSpec]]:
    manifest = _read_manifest(source_dir)
    ext_id = manifest.get("id") or manifest.get("name") or source_dir.name
    version = manifest.get("version") or "0.0.0"
    return ext_id, version, collect_extension_uploads(source_dir, ext_id)


def _upload_specs(
    registry_id: str,
    namespace: str,
    uploads: list[UploadSpec],
    network: str,
    *,
    identity: str | None,
) -> tuple[int, int, int]:
    existing = fetch_namespace_hashes(registry_id, namespace, network, identity=identity)
    uploaded = 0
    skipped = 0
    failed = 0
    temp_paths: list[Path] = []

    try:
        for spec in uploads:
            local_path = spec.local_path
            if spec.content is not None:
                handle = tempfile.NamedTemporaryFile(
                    mode="wb", suffix=".json", delete=False
                )
                handle.write(spec.content)
                handle.close()
                local_path = Path(handle.name)
                temp_paths.append(local_path)
            elif local_path is None or not local_path.is_file():
                failed += 1
                continue

            result = upload_file(
                registry_id,
                namespace,
                spec.registry_path,
                local_path,
                network,
                identity=identity,
                existing_hashes=existing,
            )
            if result == "failed":
                failed += 1
            elif result == "uploaded":
                uploaded += 1
            else:
                skipped += 1
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)

    return uploaded, skipped, failed


def publish_package(
    registry_id: str,
    namespace: str,
    uploads: list[UploadSpec],
    network: str,
    *,
    identity: str | None,
    label: str,
) -> str:
    uploaded, skipped, failed = _upload_specs(
        registry_id, namespace, uploads, network, identity=identity
    )
    if failed:
        raise CodexSeedError(f"{label}: {failed} upload(s) failed under {namespace}")
    if uploaded > 0:
        publish_namespace(registry_id, namespace, network, identity=identity)
    console.print(
        f"  {label}: {namespace} "
        f"({uploaded} uploaded, {skipped} skipped)"
    )
    return namespace


def publish_codex_dir(
    registry_id: str,
    source_dir: Path,
    network: str,
    *,
    identity: str | None = None,
) -> str:
    package_id, version, prefix, uploads = collect_codex_uploads(source_dir)
    namespace = package_namespace(package_id, version, namespace_prefix=prefix)
    return publish_package(
        registry_id,
        namespace,
        uploads,
        network,
        identity=identity,
        label=f"codex {package_id}@{version}",
    )


def publish_extension_dir(
    registry_id: str,
    source_dir: Path,
    network: str,
    *,
    identity: str | None = None,
    namespace_prefix: str = "ext",
) -> str:
    ext_id, version, uploads = collect_extension_package_uploads(source_dir)
    namespace = package_namespace(ext_id, version, namespace_prefix=namespace_prefix)
    return publish_package(
        registry_id,
        namespace,
        uploads,
        network,
        identity=identity,
        label=f"extension {ext_id}@{version}",
    )


def _org_from_release_repo(release_repo: str) -> str:
    return release_repo.split("/", 1)[0]


def _clone_ref_for_version(version: str, release_repo: str, session=None) -> str:
    resolved = resolve_deploy_version(version, release_repo, session=session)
    if resolved.source_build:
        return "main"
    return resolved.fetch_tag or resolved.descriptor_version


def resolve_realms_checkout(
    release_repo: str,
    version: str,
    work_dir: Path,
    *,
    existing_checkout: Path | None = None,
    session=None,
) -> Path:
    """Return a Realms repo tree suitable for codex/extension seeding."""
    resolved = resolve_deploy_version(version, release_repo, session=session)
    if existing_checkout and existing_checkout.is_dir() and resolved.source_build:
        return existing_checkout

    clone_parent = work_dir / "realms-src"
    slug = release_repo.replace("/", "_")
    if resolved.source_build:
        return clone_repo(release_repo, clone_parent)

    ref = resolved.fetch_tag or resolved.descriptor_version
    dest = clone_parent / slug / ref.replace("/", "_")
    return clone_repo_at_ref(release_repo, dest, ref)


def _ensure_codices_root(
    realms_root: Path,
    release_repo: str,
    work_dir: Path,
    ref: str,
    *,
    catalog: GosCatalog,
) -> Path:
    found = resolve_codices_root(realms_root)
    if found is not None:
        return found

    org = _org_from_release_repo(release_repo)
    codices_repo = f"{org}/{catalog.codices_repo_suffix}"
    slug = codices_repo.replace("/", "_")
    dest = work_dir / "codices-clone" / slug / ref.replace("/", "_")
    console.print(
        f"  codices submodule empty in Realms checkout; cloning {codices_repo}@{ref}"
    )
    checkout = clone_repo_at_ref(codices_repo, dest, ref)
    cloned_root = checkout / "codices"
    if not _has_codex_packages(cloned_root):
        raise CodexSeedError(
            f"no codex packages found after cloning {codices_repo}@{ref} "
            f"(expected under {cloned_root})"
        )
    return cloned_root


def _try_seed_extensions(
    registry_id: str,
    realms_root: Path,
    release_repo: str,
    work_dir: Path,
    ref: str,
    network: str,
    *,
    identity: str | None,
    catalog: GosCatalog,
) -> list[str]:
    extensions_repo_root: Path | None = None
    nested = realms_root / "extensions"
    if nested.is_dir():
        try:
            resolve_extensions_root(nested)
            extensions_repo_root = nested
        except CodexSeedError:
            extensions_repo_root = None

    if extensions_repo_root is None:
        org = _org_from_release_repo(release_repo)
        ext_repo = f"{org}/{catalog.extensions_repo_suffix}"
        slug = ext_repo.replace("/", "_")
        dest = work_dir / "extensions-clone" / slug / ref.replace("/", "_")
        try:
            console.print(
                f"  extensions not in Realms checkout; cloning {ext_repo}@{ref}"
            )
            extensions_repo_root = clone_repo_at_ref(ext_repo, dest, ref)
        except Exception as exc:
            console.print(
                f"  [yellow]warning:[/yellow] could not clone {ext_repo}@{ref} "
                f"for extension seeding ({exc}); realm extension installs may fail"
            )
            return []

    try:
        extensions_root = resolve_extensions_root(extensions_repo_root)
    except CodexSeedError as exc:
        console.print(f"  [yellow]warning:[/yellow] {exc}")
        return []

    ext_dirs = list_extensions(extensions_root)
    if not ext_dirs:
        console.print("  [yellow]warning:[/yellow] no extensions found to seed")
        return []

    console.print(f"  seeding {len(ext_dirs)} extensions from {extensions_root}")
    failures: list[str] = []
    build_failures: list[str] = []
    namespaces: list[str] = []
    for ext_dir in ext_dirs:
        build_err = ensure_extension_frontend_built(ext_dir, ext_dir.name)
        if build_err:
            console.print(
                f"  [yellow]warning:[/yellow] extension {ext_dir.name}: {build_err}"
            )
            build_failures.append(ext_dir.name)
        try:
            namespaces.append(
                publish_extension_dir(
                    registry_id, ext_dir, network, identity=identity
                )
            )
        except CodexSeedError:
            failures.append(ext_dir.name)
    if build_failures:
        console.print(
            f"  [yellow]warning:[/yellow] extension frontend builds failed: "
            f"{', '.join(build_failures)}"
        )
    if failures:
        console.print(
            f"  [yellow]warning:[/yellow] extension publish failed for: "
            f"{', '.join(failures)}"
        )
    return namespaces


def seed_codex_catalog(
    registry_id: str,
    release_repo: str,
    version: str,
    work_dir: Path,
    network: str,
    *,
    identity: str | None = None,
    catalog: GosCatalog,
    existing_realms_checkout: Path | None = None,
    session=None,
) -> list[str]:
    """Publish codex (and best-effort extension) catalogs for one GOS source tree."""
    ref = _clone_ref_for_version(version, release_repo, session=session)
    realms_root = resolve_realms_checkout(
        release_repo,
        version,
        work_dir,
        existing_checkout=existing_realms_checkout,
        session=session,
    )
    codices_root = _ensure_codices_root(
        realms_root, release_repo, work_dir, ref, catalog=catalog
    )
    codex_dirs = list_codices(codices_root)
    if not codex_dirs:
        raise CodexSeedError(f"no codex packages under {codices_root}")

    console.print(
        f"  seeding {len(codex_dirs)} codices from {codices_root} "
        f"({release_repo}@{ref})"
    )
    failures: list[str] = []
    namespaces: list[str] = []
    for codex_dir in codex_dirs:
        try:
            namespaces.append(
                publish_codex_dir(registry_id, codex_dir, network, identity=identity)
            )
        except CodexSeedError:
            failures.append(codex_dir.name)

    if failures:
        raise CodexSeedError(
            f"codex publish failed for: {', '.join(failures)}"
        )

    namespaces.extend(
        _try_seed_extensions(
            registry_id,
            realms_root,
            release_repo,
            work_dir,
            ref,
            network,
            identity=identity,
            catalog=catalog,
        )
    )
    return namespaces
