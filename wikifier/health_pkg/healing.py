"""
Stub healing: promote map-first "Initial stub" rows once a real wiki exists.

High-quality wikis heal straight to 🟢, medium ones to 🟡 (policy-configurable).
The ``stale`` target re-Yellows rows whose wiki drifted from recorded intent.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import locking
from .freshness import _find_existing_wiki_file, _is_stale_wiki
from .store import GREEN, YELLOW, RootLike, _coerce_root, _do_save_health, _timestamp, load_health, normalize_entry
from .summary import _in_directory, _is_map_first_stub_entry

_IMPORTANT_SECTIONS = (
    "purpose", "role", "overview", "responsibilities", "summary",
    "dependencies", "usage", "api", "interface", "examples",
    "notes", "implementation details", "how it works",
)


def _assess_wiki_quality(wiki_path: Path) -> Dict[str, Any]:
    """Score a wiki file 0–15 on length, structure and section coverage."""
    try:
        text = wiki_path.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return {"score": 0, "quality": "low", "length": 0, "word_count": 0, "reason": "unreadable"}
    if not text:
        return {"score": 0, "quality": "low", "length": 0, "word_count": 0, "reason": "empty"}

    word_count = len(text.split())
    headings = re.findall(r"^#{1,6}\s+.+$", text, re.MULTILINE)
    bullet_count = len(re.findall(r"^\s*[-*+]\s+", text, re.MULTILINE))
    has_code_block = bool(re.search(r"```|`[^`]+`", text))
    has_numbered_list = bool(re.search(r"^\s*\d+\.\s+", text, re.MULTILINE))
    lowered = text.lower()
    section_hits = sum(1 for kw in _IMPORTANT_SECTIONS if kw in lowered)
    has_purpose = any(kw in lowered for kw in ("purpose", "role", "overview", "summary"))

    score = 0
    score += 4 if word_count > 250 else 3 if word_count > 120 else 2 if word_count > 60 else 1 if word_count > 30 else 0
    score += 3 if len(headings) >= 4 else 2 if len(headings) >= 2 else 1 if headings else 0
    score += 1 if any(len(h) - len(h.lstrip("#")) >= 3 for h in headings) else 0
    score += 2 if bullet_count >= 4 else 1 if bullet_count else 0
    score += 1 if has_numbered_list else 0
    score += 1 if has_code_block else 0
    score += 2 if has_purpose else 0
    score += min(section_hits, 3)

    return {
        "score": min(score, 15),
        "quality": "high" if score >= 11 else "medium" if score >= 7 else "low",
        "length": len(text),
        "word_count": word_count,
        "line_count": text.count("\n") + 1,
        "heading_count": len(headings),
        "has_headings": len(headings) >= 2,
        "has_bullets": bullet_count > 0,
        "has_code_block": has_code_block,
        "has_purpose_section": has_purpose,
        "important_sections_found": section_hits,
    }


def _is_stub(entry: Dict[str, Any]) -> bool:
    return _is_map_first_stub_entry(entry) or (
        "🔴" in str(entry.get("status", "")) and "stub" in str(entry.get("reason", "")).lower()
    )


def heal_with_policy(
    root: RootLike,
    policy: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Policy-driven heal.

    policy (all optional)::

        {"targets": ["stubs", "stale"],
         "stub": {"min_wiki_length": 350, "auto_green_on": "high", "auto_yellow_on": "medium"},
         "stale": {"min_confidence": 0.65, "action": "mark_yellow_with_note"},
         "provenance_tag": "policy-heal-v1"}
    """
    root = _coerce_root(root)
    policy = policy or {}
    targets = policy.get("targets", ["stubs"])
    stub_policy = policy.get("stub", {})
    min_len = int(stub_policy.get("min_wiki_length", 350))
    green_on = stub_policy.get("auto_green_on", "high")
    yellow_on = stub_policy.get("auto_yellow_on", "medium")
    stale_policy = policy.get("stale", {})
    stale_conf = float(stale_policy.get("min_confidence", 0.65))
    tag = policy.get("provenance_tag", "policy-heal-v1")

    changes: List[Dict[str, Any]] = []
    healed = stale_checked = stale_healed = 0
    with locking.file_lock(root):
        health = load_health(root)
        entries = list(health.get("entries", {}).items())
        for rel_path, entry in entries:
            status = entry.get("status", "")
            if "stubs" in targets and _is_stub(entry):
                wiki_file = _find_existing_wiki_file(root, rel_path)
                if wiki_file:
                    quality = _assess_wiki_quality(wiki_file)
                    new_status = None
                    if quality["quality"] == "high" and green_on != "never":
                        new_status = GREEN
                        new_reason = f"Auto-healed via policy (high-quality wiki, was {status})"
                    elif quality["quality"] == "medium" and quality["length"] >= min_len and yellow_on == "medium":
                        new_status = YELLOW
                        new_reason = f"Auto-healed via policy (meaningful wiki now exists, was {status})"
                    if new_status:
                        if not dry_run:
                            base = normalize_entry(entry)
                            base.update({
                                "status": new_status,
                                "last_updated": _timestamp(),
                                "reason": new_reason,
                                "freshness_provenance": f"{base.get('freshness_provenance') or ''}; {tag}:stub q={quality['quality']}",
                            })
                            health["entries"][rel_path] = base
                        changes.append({
                            "file": rel_path, "old_status": status, "new_status": new_status,
                            "quality": quality["quality"], "wiki_size": quality["length"],
                            "diagnostics": {"wiki_quality": quality}, "policy_target": "stubs",
                        })
                        healed += 1
            if "stale" in targets:
                diag = _is_stale_wiki(root, rel_path, entry)
                if diag and diag.get("confidence", 0) >= stale_conf:
                    stale_checked += 1
                    if stale_policy.get("action", "mark_yellow_with_note") == "mark_yellow_with_note":
                        if not dry_run:
                            base = normalize_entry(entry)
                            base.update({
                                "status": YELLOW,
                                "last_updated": _timestamp(),
                                "reason": (
                                    f"Policy-healed stale wiki (conf={diag['confidence']}; "
                                    f"reasons: {'; '.join(diag['reasons'])})"
                                ),
                                "freshness_provenance": f"{base.get('freshness_provenance') or ''}; {tag}:stale conf={diag['confidence']}",
                            })
                            health["entries"][rel_path] = base
                        changes.append({
                            "file": rel_path, "old_status": status, "new_status": YELLOW,
                            "diagnostics": {"stale": diag}, "policy_target": "stale",
                        })
                        stale_healed += 1
                        healed += 1
        if healed and not dry_run:
            _do_save_health(root, health)

    if changes:
        recommendation = (
            f"Healed {healed} under policy (stubs:{healed - stale_healed}, stale:{stale_healed}). "
            "Review changes and re-run stale-wikis."
        )
    else:
        recommendation = "No healable items matched current policy."
    return {
        "healed_count": healed,
        "stale_checked": stale_checked,
        "stale_healed": stale_healed,
        "changes": changes[:100],
        "policy_used": policy or {"targets": ["stubs"]},
        "diagnostics": {"total_candidates_considered": len(entries)},
        "recommendation": recommendation,
        "dry_run": dry_run,
    }


def heal_outdated_stubs(root: RootLike, min_wiki_length: int = 350, dry_run: bool = False) -> int:
    """Stubs-only heal; returns the number healed."""
    res = heal_with_policy(
        root,
        policy={"targets": ["stubs"], "stub": {"min_wiki_length": min_wiki_length}},
        dry_run=dry_run,
    )
    return int(res.get("healed_count", 0))


def get_healable_stubs(
    root: RootLike,
    min_wiki_length: int = 350,
    directory: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Stub rows whose wiki is now substantial enough to heal (best first)."""
    root = _coerce_root(root)
    candidates = []
    for rel_path, entry in load_health(root).get("entries", {}).items():
        if not _in_directory(rel_path, directory) or not _is_stub(entry):
            continue
        wiki_file = _find_existing_wiki_file(root, rel_path)
        if not wiki_file:
            continue
        quality = _assess_wiki_quality(wiki_file)
        if quality["length"] >= min_wiki_length and quality["quality"] != "low":
            candidates.append({
                "file": rel_path,
                "current_status": entry.get("status", ""),
                "wiki_file": str(wiki_file.relative_to(root)),
                "wiki_size": quality["length"],
                "quality": quality["quality"],
                "quality_score": quality["score"],
                "has_headings": quality["has_headings"],
                "has_purpose": quality["has_purpose_section"],
                "reason": entry.get("reason", ""),
            })
    return sorted(candidates, key=lambda x: (-x["quality_score"], x["file"]))


def get_healing_statistics(root: RootLike) -> Dict[str, Any]:
    """Stub counts and how many could be healed now, by wiki quality."""
    root = _coerce_root(root)
    entries = load_health(root).get("entries", {})
    stubs = high = medium = low = 0
    for rel_path, entry in entries.items():
        if not _is_stub(entry):
            continue
        stubs += 1
        wiki_file = _find_existing_wiki_file(root, rel_path)
        if not wiki_file:
            continue
        quality = _assess_wiki_quality(wiki_file)["quality"]
        if quality == "high":
            high += 1
        elif quality == "medium":
            medium += 1
        else:
            low += 1
    return {
        "total_health_entries": len(entries),
        "current_initial_stubs": stubs,
        "healable_stubs": {"total": high + medium + low, "high_quality": high, "medium_quality": medium, "low_quality": low},
        "stub_pollution_ratio": round(stubs / max(len(entries), 1), 3),
        "recommendation": _generate_healing_recommendation(stubs, high, medium),
    }


def _generate_healing_recommendation(initial_stubs: int, high: int, medium: int) -> str:
    if initial_stubs == 0:
        return "No Initial stubs remaining."
    if high >= 5:
        return f"{high} high-quality wikis can be promoted to Green now (heal-stubs)."
    if high + medium >= 8:
        return f"{high + medium} stubs can be healed (heal-stubs)."
    if initial_stubs > 15:
        return "Many stubs without wikis. Normal for map-first; wiki a file when you edit it."
    return "A few stubs remain; low urgency."
