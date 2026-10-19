"""Tests and attestation behind a release version (NERD011 SPEC002).

The service records a cut's evidence as ``method`` / ``by`` / ``note``; it does
not record test runs or a signed attestation yet (NERD0016 leaves signing open).
When it does, they arrive as ``evidence.tests`` and ``evidence.attestation`` and
are shown as recorded.

Until then a local demo can set ``RELEASE_DEMO_EVIDENCE`` to show stand-ins. They
are derived only from the release version itself, so a publisher's and a
customer's GUI show the same runs and the same signature for the same version,
and every view marks them as demo data. Recorded evidence always wins.
"""
import hashlib
import json
from typing import Dict, List, Optional

from django.conf import settings

PROVEN_STATUSES = ("verified", "released")

# Generic acceptance checks a member's suite is drawn from.
_MEMBER_CASES = [
    "deploys cleanly from an empty namespace",
    "health endpoint responds",
    "configuration is applied",
    "credentials resolve through external secrets",
    "survives a pod restart",
    "upgrades in place from the previous release",
    "exports metrics to the collector",
    "rolls back on a failed upgrade",
]

_END_TO_END_CASES = [
    "every member reaches DEPLOYED",
    "dependencies resolve to the pinned instances",
    "telemetry flows from collector to storage",
    "dashboards load against live data",
]


def _digest(*parts) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()


def _pins(detail: Dict) -> List[Dict]:
    """One row per pinned (repo class, version), in name order."""
    seen, rows = set(), []
    for artifact in detail.get("artifacts") or []:
        key = (artifact.get("repo_class_name"), artifact.get("version"))
        if key not in seen:
            seen.add(key)
            rows.append(
                {
                    "repo_class_name": key[0],
                    "version": key[1],
                    "digest": artifact.get("digest"),
                }
            )
    for name, version in (detail.get("pins") or {}).items():
        if (name, version) not in seen:
            seen.add((name, version))
            rows.append({"repo_class_name": name, "version": version, "digest": None})
    return sorted(rows, key=lambda r: (r["repo_class_name"] or "", r["version"] or ""))


def _summary(tests: List[Dict]) -> Dict:
    return {
        key: sum(int(t.get(key) or 0) for t in tests)
        for key in ("passed", "failed", "skipped")
    } | {"suites": len(tests)}


def _test_rows(tests: List[Dict]) -> List[Dict]:
    rows = []
    for t in tests:
        row = dict(t)
        row.setdefault("outcome", "failed" if t.get("failed") else "passed")
        rows.append(row)
    return rows


def _demo_suite(
    seed: str, suite: str, cases: List[str], count: int, outcome: str, env, at
) -> Dict:
    picked = cases[:count]
    failed = 1 if outcome == "failed" else 0
    ran = outcome in ("passed", "failed")
    return {
        "suite": suite,
        "outcome": outcome,
        "environment": env,
        "run_at": at if ran else None,
        "passed": len(picked) - failed if ran else 0,
        "failed": failed,
        "skipped": 0 if ran else len(picked),
        "duration_seconds": 20 + int(_digest(seed, suite)[:4], 16) % 400
        if ran
        else None,
        "cases": [
            {
                "name": c,
                "outcome": ("failed" if failed and i == len(picked) - 1 else "passed")
                if ran
                else "not_run",
            }
            for i, c in enumerate(picked)
        ],
    }


def _demo_evidence(detail: Dict) -> Dict:
    name, version = detail.get("release_name"), detail.get("version")
    status = detail.get("status")
    evidence = detail.get("evidence") or {}
    env, at = evidence.get("environment"), evidence.get("at")
    seed = _digest(name, version)
    outcome = (
        "passed"
        if status in PROVEN_STATUSES
        else "failed"
        if status == "failed"
        else "not_run"
    )
    pins = _pins(detail)

    tests = [
        _demo_suite(
            seed,
            f"{p['repo_class_name']} {p['version']} acceptance",
            _MEMBER_CASES,
            3 + int(_digest(seed, p["repo_class_name"])[:2], 16) % 4,
            "passed" if outcome == "failed" else outcome,
            env,
            at,
        )
        for p in pins
    ]
    tests.append(
        _demo_suite(
            seed,
            f"{name} end-to-end",
            _END_TO_END_CASES,
            len(_END_TO_END_CASES),
            outcome,
            env,
            at,
        )
    )

    attestation = None
    if status in PROVEN_STATUSES:
        materials = [
            {
                **p,
                "digest": p["digest"]
                or f"sha256:{_digest(p['repo_class_name'], p['version'])}",
            }
            for p in pins
        ]
        subject_digest = (
            f"sha256:{_digest(name, version, json.dumps(materials, sort_keys=True))}"
        )
        attestation = {
            "predicate_type": "https://slsa.dev/provenance/v1",
            "subject": f"release:/{name}/{version}/release.json",
            "subject_digest": subject_digest,
            "builder": "hmd-ms-deployment release_environment",
            "signed_by": evidence.get("by") or "release-manager",
            "signed_at": at,
            "key_id": f"demo-{seed[:12]}",
            "signature": _digest("signature", subject_digest)[:64],
            "verification": "valid",
            "materials": materials,
        }
    return {
        "tests": tests,
        "attestation": attestation,
        "demo": True,
        "summary": _summary(tests),
    }


def release_evidence(detail: Optional[Dict]) -> Dict:
    """``{tests, attestation, summary, demo}`` for a release version.

    ``tests`` is a list of suites (``suite``, ``outcome``, ``environment``,
    ``passed``/``failed``/``skipped``, ``cases``); ``attestation`` is a signed
    statement over the release description and its pinned builds, or ``None``
    while the version is unsigned.
    """
    detail = detail or {}
    evidence = detail.get("evidence") or {}
    tests, attestation = evidence.get("tests"), evidence.get("attestation")
    if tests or attestation:
        rows = _test_rows(tests or [])
        return {
            "tests": rows,
            "attestation": attestation,
            "demo": False,
            "summary": _summary(rows),
        }
    if getattr(settings, "RELEASE_DEMO_EVIDENCE", False):
        return _demo_evidence(detail)
    return {"tests": [], "attestation": None, "demo": False, "summary": None}
