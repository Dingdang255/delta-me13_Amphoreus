"""Read-only agent cards and a deterministic decision step.

A card is a record from the compiled corpus: goals, beliefs, decision rules,
relations, speech profile and out-of-character guards. This module only
*reads* them and answers one question -- "given this percept, which rule
fires?" -- without mutating anything.

Rules are matched on the exact ``when`` string. That is deliberate: the corpus
is prose, and pretending to understand it would be inventing a parser. A rule
whose ``when`` is ``UNKNOWN`` is treated as **not executable**, never as a
wildcard.

No titles, no names, no prose constants live here.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

UNKNOWN = "UNKNOWN"
_RULE_ID = re.compile(r"R-\d+(?:-\d+)?")
DEFAULT_CARD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lore", "canon", "characters"
)


class AgentError(RuntimeError):
    """Raised when a card is malformed."""


@dataclass(frozen=True)
class Rule:
    id: str
    when: str
    then: str
    priority: int
    source: str
    conflict: str = ""

    @property
    def executable(self) -> bool:
        return bool(self.when) and self.when != UNKNOWN


@dataclass(frozen=True)
class Card:
    id: str
    rules: tuple[Rule, ...] = ()
    goals: tuple[dict, ...] = ()
    beliefs: tuple[dict, ...] = ()
    emotions: tuple[dict, ...] = ()
    relations: tuple[dict, ...] = ()
    behavior: tuple[dict, ...] = ()
    arc: tuple[dict, ...] = ()
    guards: tuple[str, ...] = ()
    speech: dict = field(default_factory=dict)
    identity: dict = field(default_factory=dict)
    confidence: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def executable_rules(self) -> tuple[Rule, ...]:
        return tuple(r for r in self.rules if r.executable)


def from_dict(obj: dict) -> Card:
    if not isinstance(obj, dict) or not obj.get("id"):
        raise AgentError("card has no id")
    rules = []
    for raw in obj.get("decision_rules") or []:
        rules.append(Rule(
            id=str(raw.get("id", "")),
            when=str(raw.get("when", "") or ""),
            then=str(raw.get("then", "") or ""),
            priority=int(raw.get("priority", 99)),
            source=str(raw.get("source", "") or ""),
            conflict=str(raw.get("conflict", "") or ""),
        ))
    return Card(
        id=obj["id"],
        rules=tuple(rules),
        goals=tuple(obj.get("goals") or []),
        beliefs=tuple(obj.get("beliefs") or []),
        emotions=tuple(obj.get("emotions") or []),
        relations=tuple(obj.get("relations") or []),
        behavior=tuple(obj.get("behavior_patterns") or []),
        arc=tuple(obj.get("arc") or []),
        guards=tuple(obj.get("ooc_guards") or []),
        speech=dict(obj.get("speech") or {}),
        identity=dict(obj.get("identity") or {}),
        confidence=str(obj.get("confidence", "") or ""),
        raw=obj,
    )


def load_cards(root: str | None = None) -> dict[str, Card]:
    """Load every card from a compiled bundle (or a plain directory)."""
    root = root or DEFAULT_CARD_DIR
    cards: dict[str, Card] = {}
    if os.path.exists(os.path.join(root, "manifest.json")):
        from apps import canon  # local import: avoids a hard dependency at import time
        bundle = canon.CanonBundle.load(root)
        for entry in bundle.of_kind("character"):
            cards[entry.id] = from_dict(entry.data)
        return cards
    for name in sorted(os.listdir(root)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(root, name), "r", encoding="utf-8") as f:
            card = from_dict(json.load(f))
        cards[card.id] = card
    return cards


def decide(card: Card, percept: str) -> dict | None:
    """Return the firing rule, or None when nothing executable matches.

    When several rules share the same ``when``, all of them are reported and
    ``ambiguous`` is set -- the caller decides, this module does not guess.
    """
    if not percept:
        return None
    matches = [r for r in card.rules if r.executable and r.when == percept]
    if not matches:
        return None
    matches.sort(key=lambda r: (r.priority, r.id))
    best = matches[0]
    return {
        "character": card.id,
        "rule": best.id,
        "action": best.then,
        "priority": best.priority,
        "source": best.source,
        "candidates": [r.id for r in matches],
        "ambiguous": len(matches) > 1,
        "matched_by": "exact",
    }


def relation_update(card: Card, target: str, delta: float,
                    low: float = 0.0, high: float = 1.0) -> float | None:
    """Pure relation arithmetic; returns the new intensity, never mutates the card."""
    for rel in card.relations:
        if rel.get("target") == target:
            base = float(rel.get("intensity", 0.0))
            return round(max(low, min(high, base + float(delta))), 6)
    return None


def emotion_for(card: Card, trigger: str) -> dict | None:
    """Exact trigger match on the card's emotion table; None when absent."""
    for emo in card.emotions:
        if emo.get("trigger") == trigger:
            return dict(emo)
    return None


def speech_profile(card: Card) -> dict:
    """The data the renderer needs; no text is generated here."""
    return {
        "character": card.id,
        "tone": card.speech.get("tone", ""),
        "style": card.speech.get("sentence_style", ""),
        "catchphrases": list(card.speech.get("catchphrases") or []),
        "taboo": list(card.speech.get("taboo_topics") or []),
    }


def expected_rule_id(scenario: dict) -> str:
    """The corpus stores the expectation as prose (``reason``); pull the rule id out."""
    expect = scenario.get("expect") or {}
    explicit = str(expect.get("rule_id") or "")
    if explicit:
        return explicit
    match = _RULE_ID.search(str(expect.get("reason", "") or ""))
    return match.group(0) if match else ""


def scenario_check(card: Card, scenario: dict) -> dict:
    """Compare one scenario against one card. Never raises on missing data."""
    given = scenario.get("given") or {}
    percept = str(given.get("percept", "") or "")
    expected_id = expected_rule_id(scenario)
    result = decide(card, percept)
    if result is None:
        unknown = percept in ("", UNKNOWN) or any(
            r.when == percept and not r.executable for r in card.rules)
        return {
            "scenario": scenario.get("id"),
            "status": "unknown" if unknown else "no_rule",
            "percept": percept,
            "expected": expected_id,
            "got": None,
        }
    status = "pass"
    if expected_id and expected_id not in result["candidates"]:
        status = "mismatch"
    return {
        "scenario": scenario.get("id"),
        "status": status,
        "percept": percept,
        "expected": expected_id,
        "got": result["rule"],
        "candidates": result["candidates"],
        "ambiguous": result["ambiguous"],
    }
