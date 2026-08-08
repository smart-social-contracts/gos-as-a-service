"""Descriptor version validation and deploy-time resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests

from gaas.artifacts import ArtifactError

VERSION_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")
SPECIAL_VERSIONS = frozenset({"main", "latest"})

_latest_tag_cache: dict[str, str] = {}


def validate_descriptor_version(value: str) -> str:
    """Accept semver release tags (vX.Y.Z), ``main``, or ``latest`` (case-insensitive)."""
    stripped = value.strip()
    lower = stripped.lower()
    if lower in SPECIAL_VERSIONS:
        return lower
    if VERSION_TAG_RE.match(stripped):
        return stripped
    raise ValueError(
        f"version must match vX.Y.Z, 'main', or 'latest' (got {value!r})"
    )


def normalize_catalog_version(version: str) -> str:
    """Map a deploy/catalog label to the file-registry namespace segment."""
    if version.lower() == "main":
        return "main"
    return version.lstrip("v")


@dataclass(frozen=True)
class ResolvedDeployVersion:
    descriptor_version: str
    fetch_tag: str | None
    catalog_version: str

    @property
    def source_build(self) -> bool:
        return self.descriptor_version == "main"


def clear_latest_tag_cache() -> None:
    """Clear the in-process ``latest`` tag cache (for tests)."""
    _latest_tag_cache.clear()


def resolve_latest_tag(
    release_repo: str,
    session: requests.Session | None = None,
) -> str:
    """Resolve ``latest`` to the newest GitHub release tag for *release_repo*."""
    if release_repo in _latest_tag_cache:
        return _latest_tag_cache[release_repo]

    http = session or requests.Session()
    url = f"https://api.github.com/repos/{release_repo}/releases/latest"
    response = http.get(
        url,
        timeout=30,
        headers={"Accept": "application/vnd.github+json"},
    )
    if response.status_code != 200:
        raise ArtifactError(
            f"failed to resolve latest release for {release_repo}: "
            f"HTTP {response.status_code} {response.reason}"
        )
    payload = response.json()
    tag = payload.get("tag_name")
    if not tag or not VERSION_TAG_RE.match(tag):
        raise ArtifactError(
            f"latest release for {release_repo} has invalid tag {tag!r} "
            f"(expected vX.Y.Z)"
        )
    _latest_tag_cache[release_repo] = tag
    return tag


def resolve_deploy_version(
    version: str,
    release_repo: str,
    session: requests.Session | None = None,
) -> ResolvedDeployVersion:
    """Resolve a descriptor version pin to fetch/build and catalog labels."""
    normalized = validate_descriptor_version(version)
    if normalized == "main":
        return ResolvedDeployVersion("main", None, "main")
    if normalized == "latest":
        tag = resolve_latest_tag(release_repo, session=session)
        return ResolvedDeployVersion("latest", tag, normalize_catalog_version(tag))
    return ResolvedDeployVersion(
        normalized,
        normalized,
        normalize_catalog_version(normalized),
    )
