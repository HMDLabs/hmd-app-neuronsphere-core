"""Shape a release version for the catalog views (NERD011 SPEC002, SPEC005).

A release shows its evidence the same way everywhere, and what it claims is
never louder than what was proved: *verified* (a gated apply), *attested* (an
operator's note) or *partly attested* (pins were carried forward).
"""
from typing import Dict, List, Optional

PROVEN_STATUSES = ("verified", "released")

# Per-artifact statuses reported by the service's ``release_install_status``.
PRESENT = "present"
DIGEST_MISMATCH = "digest_mismatch"


def carried_forward(release_version: Dict) -> List[Dict]:
    """The pins taken from an earlier release instead of this environment, each
    naming the release it came from."""
    return list((release_version.get("evidence") or {}).get("carried_forward") or [])


def evidence_level(release_version: Dict) -> str:
    """``partly_attested`` | ``attested`` | ``verified`` | ``none``.

    Carried-forward pins win over everything: a release that carries any pin
    was not tested as a whole, whatever else its evidence says.
    """
    evidence = release_version.get("evidence") or {}
    if evidence.get("carried_forward"):
        return "partly_attested"
    if evidence.get("method") == "manual":
        return "attested"
    return "verified" if release_version.get("status") in PROVEN_STATUSES else "none"


def pin_rows(release_version: Dict) -> List[Dict]:
    """The pins table: repo class, version, content path, digest.

    Rows come from ``artifacts`` (one per pin, so a class pinned at several
    versions has a row each); a release without them falls back to ``pins``.
    """
    artifacts = release_version.get("artifacts") or [
        {"repo_class_name": name, "version": version}
        for name, version in (release_version.get("pins") or {}).items()
    ]
    rows = [
        {
            "repo_class_name": a.get("repo_class_name"),
            "version": a.get("version"),
            "content_path": a.get("content_path"),
            "digest": a.get("digest"),
        }
        for a in artifacts
    ]
    pinned = release_version.get("pins") or {}
    known = {(r["repo_class_name"], r["version"]) for r in rows}
    rows += [
        {"repo_class_name": n, "version": v, "content_path": None, "digest": None}
        for n, v in pinned.items()
        if (n, v) not in known
    ]
    return sorted(rows, key=lambda r: (r["repo_class_name"] or "", r["version"] or ""))


def arrival_summary(report: Optional[Dict]) -> Dict:
    """Condense an install report to ``installed`` / ``arriving`` / ``blocked`` /
    ``unknown`` (never received), with counts, and whether the page should keep
    polling: only while something is still arriving."""
    entries = (report or {}).get("entries") or []
    if not entries:
        return {
            "state": "unknown",
            "present": 0,
            "total": 0,
            "blocked": 0,
            "polling": False,
        }
    present = sum(1 for e in entries if e.get("status") == PRESENT)
    blocked = sum(1 for e in entries if e.get("status") == DIGEST_MISMATCH)
    if blocked:
        state = "blocked"
    elif report.get("installed"):
        state = "installed"
    else:
        state = "arriving"
    return {
        "state": state,
        "present": present,
        "total": len(entries),
        "blocked": blocked,
        "polling": state == "arriving",
    }
