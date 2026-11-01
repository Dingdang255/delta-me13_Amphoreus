"""Read-only mind layer: memory stream, value vector, rule-first decisions.

This module adds a *mind* on top of the card reader in :mod:`apps.agents`
without touching the kernel:

  · :class:`MindState`  -- autobiographical memories (event -> emotional
    residue), a configurable value vector, the current emotion and the
    commitments / goals the self is holding.
  · :func:`decide`      -- persona rules first; when several rules conflict,
    candidates are scored by ``value gap * memory weight * emotion``.  The
    returned dict always carries ``action``, ``reason``, ``evidence`` and
    ``scores``; every piece of evidence names a rule or memory id.
  · :class:`MindShadow` -- an optional read-only frame observer.  It may be
    attached as a ``watch`` callable, but it never writes ``st`` and never
    returns ``False``, so the trajectory fingerprint is unchanged.

Persona parameters live in an optional ``presets/<name>/mind.json`` file.  A
missing or broken file falls back to the defaults below, which leave the old
rule-priority behaviour intact (all scores tie, so the lowest priority wins).

Standard library only; no global mutable state.
"""
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field, replace

PERSONA_FILE = "mind.json"
DEFAULT_VALUE_WEIGHT = 1.0

DEFAULT_PERSONA = {
    "id": "default",
    "value_weights": {},
    "memory_weight": 0.5,
    "emotion_weight": 0.5,
    "rules": (),
    "event_values": {},
    "event_emotions": {},
}

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _clamp01(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:          # NaN
        return 0.0
    return max(0.0, min(1.0, number))


def _as_int(value, default: int = 99) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _axis_map(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    return {str(axis): _clamp01(value) for axis, value in raw.items()}


# ---- persona ----------------------------------------------------------------
def default_persona() -> dict:
    """A fresh copy of the neutral persona (all old behaviour preserved)."""
    return copy.deepcopy(DEFAULT_PERSONA)


def _normalize_rules(raw) -> tuple:
    if not isinstance(raw, (list, tuple)):
        return ()
    out = []
    for index, row in enumerate(raw):
        if not isinstance(row, dict):
            continue
        out.append({
            "id": str(row.get("id") or f"P-{index + 1}"),
            "when": str(row.get("when") or ""),
            "then": str(row.get("then") or ""),
            "priority": _as_int(row.get("priority"), 99),
            "source": str(row.get("source") or ""),
            "values": _axis_map(row.get("values") or row.get("value_weights")),
        })
    return tuple(out)


def normalize_persona(raw) -> dict:
    """Coerce an untrusted persona dict into the documented shape (0..1)."""
    persona = default_persona()
    if not isinstance(raw, dict):
        return persona
    if raw.get("id"):
        persona["id"] = str(raw["id"])
    for key in ("memory_weight", "emotion_weight"):
        if key in raw:
            persona[key] = _clamp01(raw[key])

    weights = raw.get("value_weights")
    if weights is None:
        weights = raw.get("values")
    if weights is None:
        weights = raw.get("weights")
    persona["value_weights"].update(_axis_map(weights))
    persona["rules"] = _normalize_rules(raw.get("rules") or raw.get("decision_rules"))

    events = raw.get("event_values")
    if isinstance(events, dict):
        for event, axes in events.items():
            persona["event_values"][str(event)] = _axis_map(axes)

    emotions = raw.get("event_emotions")
    if isinstance(emotions, dict):
        for event, spec in emotions.items():
            if not isinstance(spec, dict):
                continue
            persona["event_emotions"][str(event)] = {
                "emotion": str(spec.get("emotion") or ""),
                "level": _clamp01(spec.get("level", 0.0)),
            }
    return persona


def load_persona(path: str | None = None, *, preset=None, root: str | None = None) -> dict:
    """Read a persona file; any failure returns the neutral defaults.

    ``preset`` may be a preset name (looks under ``presets/<name>/mind.json``)
    or a ready-made persona dict.  This function never raises.
    """
    if isinstance(preset, dict):
        return normalize_persona(preset)
    if path is None and preset is not None:
        root = root or _ROOT
        path = os.path.join(str(root), "presets", str(preset), PERSONA_FILE)
    if not path:
        return default_persona()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError, TypeError):
        return default_persona()
    try:
        return normalize_persona(raw)
    except Exception:              # a malformed file must never break a run
        return default_persona()


def persona_for_preset(name: str, root: str | None = None) -> dict:
    return load_persona(preset=name, root=root)


def persona_from_card(card) -> dict:
    """Build a persona whose rule table is the card's rule table."""
    persona = default_persona()
    persona["id"] = f"card:{card.id}"
    persona["rules"] = tuple({
        "id": str(rule.id),
        "when": str(rule.when),
        "then": str(rule.then),
        "priority": int(rule.priority),
        "source": str(rule.source),
        "values": {},
    } for rule in card.rules)
    return persona


# ---- state ------------------------------------------------------------------
@dataclass(frozen=True)
class Memory:
    """One autobiographical event: what happened, how heavy, what it left."""

    id: str
    event: str
    weight: float = 0.0
    residue: tuple = ()            # ((axis, delta), ...)
    frame: int = -1

    def __post_init__(self):
        object.__setattr__(self, "weight", _clamp01(self.weight))
        object.__setattr__(self, "frame", _as_int(self.frame, -1))
        residue = self.residue
        if isinstance(residue, dict):
            residue = tuple(sorted((str(k), _clamp01(v)) for k, v in residue.items()))
        else:
            residue = tuple(sorted((str(k), _clamp01(v)) for k, v in (residue or ())))
        object.__setattr__(self, "residue", residue)

    @property
    def axes(self) -> tuple:
        return tuple(axis for axis, _value in self.residue)


@dataclass(frozen=True)
class MindState:
    """A pure snapshot of a mind; every ``with_*`` helper returns a new one."""

    character: str = ""
    memories: tuple = ()
    values: dict = field(default_factory=dict)
    emotion: str = "calm"
    emotion_level: float = 0.0
    commitments: tuple = ()
    goals: tuple = ()
    card: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "character", str(self.character or ""))
        object.__setattr__(self, "memories", tuple(self.memories or ()))
        object.__setattr__(self, "values", _axis_map(self.values))
        object.__setattr__(self, "emotion", str(self.emotion or "calm"))
        object.__setattr__(self, "emotion_level", _clamp01(self.emotion_level))
        object.__setattr__(self, "commitments", tuple(self.commitments or ()))
        object.__setattr__(self, "goals", tuple(self.goals or ()))
        object.__setattr__(self, "card", dict(self.card or {}))

    # -- read-only views ------------------------------------------------------
    @property
    def memory_stream(self) -> tuple:
        return self.memories

    @property
    def value_vector(self) -> dict:
        return dict(self.values)

    @property
    def current_emotion(self) -> str:
        return self.emotion

    def value(self, axis: str) -> float:
        return float(self.values.get(str(axis), 0.0))

    def memory_ids(self) -> tuple:
        return tuple(memory.id for memory in self.memories)

    def describe(self) -> dict:
        return {
            "character": self.character,
            "memories": len(self.memories),
            "values": dict(sorted(self.values.items())),
            "emotion": self.emotion,
            "emotion_level": round(self.emotion_level, 6),
            "commitments": len(self.commitments),
            "goals": len(self.goals),
        }

    # -- pure updates ---------------------------------------------------------
    def with_values(self, values: dict) -> "MindState":
        return replace(self, values=_axis_map(values))

    def with_emotion(self, emotion: str, level: float) -> "MindState":
        return replace(self, emotion=str(emotion or "calm"), emotion_level=_clamp01(level))

    def remember(self, event: str, *, weight: float = 0.5, frame: int = -1,
                 persona: dict | None = None, residue=None) -> "MindState":
        """Append one event; returns a new state with its emotional residue."""
        persona = normalize_persona(persona) if persona is not None else default_persona()
        event = str(event)
        if residue is None:
            residue = (persona.get("event_values") or {}).get(event, {})
        memory = Memory(
            id=f"M-{len(self.memories) + 1:04d}-{event}",
            event=event,
            weight=weight,
            residue=residue,
            frame=frame,
        )
        spec = (persona.get("event_emotions") or {}).get(event) or {}
        emotion = str(spec.get("emotion") or self.emotion)
        if "level" in spec:
            level = spec["level"]
        else:
            gain = float(persona.get("emotion_weight", 0.5))
            level = self.emotion_level + memory.weight * gain * 0.5
        return replace(self, memories=self.memories + (memory,),
                       emotion=emotion, emotion_level=_clamp01(level))

    # -- card bridge ----------------------------------------------------------
    def to_card(self):
        """Rebuild the :class:`apps.agents.Card` this state was derived from."""
        from apps import agents

        snapshot = self.card
        if not snapshot:
            return agents.from_dict({
                "id": self.character or "MIND-000",
                "goals": [dict(goal) for goal in self.goals],
            })
        rules = tuple(agents.Rule(*row) for row in snapshot.get("rules", ()))
        return agents.Card(
            id=str(snapshot.get("id") or self.character),
            rules=rules,
            goals=tuple(dict(item) for item in snapshot.get("goals", ())),
            beliefs=tuple(dict(item) for item in snapshot.get("beliefs", ())),
            emotions=tuple(dict(item) for item in snapshot.get("emotions", ())),
            relations=tuple(dict(item) for item in snapshot.get("relations", ())),
            behavior=tuple(dict(item) for item in snapshot.get("behavior", ())),
            arc=tuple(dict(item) for item in snapshot.get("arc", ())),
            guards=tuple(snapshot.get("guards", ())),
            speech=dict(snapshot.get("speech") or {}),
            identity=dict(snapshot.get("identity") or {}),
            confidence=str(snapshot.get("confidence") or ""),
            raw=dict(snapshot.get("raw") or {}),
        )


def _card_snapshot(card) -> dict:
    """Everything needed to rebuild the card bit for bit."""
    return {
        "id": str(card.id),
        "rules": tuple((r.id, r.when, r.then, int(r.priority), r.source, r.conflict)
                       for r in card.rules),
        "goals": tuple(dict(item) for item in card.goals),
        "beliefs": tuple(dict(item) for item in card.beliefs),
        "emotions": tuple(dict(item) for item in card.emotions),
        "relations": tuple(dict(item) for item in card.relations),
        "behavior": tuple(dict(item) for item in card.behavior),
        "arc": tuple(dict(item) for item in card.arc),
        "guards": tuple(card.guards),
        "speech": dict(card.speech),
        "identity": dict(card.identity),
        "confidence": str(card.confidence),
        "raw": dict(card.raw),
    }


def from_card(card) -> MindState:
    """Read a card into a fresh mind (no memories yet, neutral emotion)."""
    return MindState(
        character=str(card.id),
        memories=(),
        values={},
        emotion="calm",
        emotion_level=0.0,
        commitments=(),
        goals=tuple(dict(goal) for goal in card.goals),
        card=_card_snapshot(card),
    )


def to_card(state: MindState):
    return state.to_card()


# ---- options ----------------------------------------------------------------
def _normalize_option(raw) -> dict | None:
    if isinstance(raw, str):
        action = raw.strip()
        if not action:
            return None
        return {"action": action, "id": action, "rule": "", "priority": 99,
                "values": {}, "emotions": {}, "when": "", "percept": ""}
    if not isinstance(raw, dict):
        return None
    action = str(raw.get("action") or raw.get("then") or raw.get("id") or "").strip()
    if not action:
        return None
    return {
        "action": action,
        "id": str(raw.get("id") or action),
        "rule": str(raw.get("rule") or raw.get("rule_id") or ""),
        "priority": _as_int(raw.get("priority"), 99),
        "values": _axis_map(raw.get("values")),
        "emotions": _axis_map(raw.get("emotions")),
        "when": str(raw.get("when") or ""),
        "percept": str(raw.get("percept") or ""),
    }


def _applicable_rules(option: dict, rules: tuple) -> tuple:
    rule_id = option.get("rule") or ""
    if rule_id:
        exact = tuple(rule for rule in rules if rule["id"] == rule_id)
        if exact:
            return exact
    keys = {option.get("action"), option.get("id"), option.get("when"),
            option.get("percept")}
    keys.discard("")
    matched = tuple(rule for rule in rules if rule["when"] and rule["when"] in keys)
    if matched:
        return matched
    return tuple(rule for rule in rules
                 if not rule["when"] and rule["then"] == option["action"])


def _best_rule(option: dict) -> dict | None:
    rules = option.get("_rules") or ()
    if not rules:
        return None
    return min(rules, key=lambda rule: (rule["priority"], rule["id"]))


def _score_row(index: int, option: dict, rule: dict | None,
               state: MindState, persona: dict) -> dict:
    values = dict(option["values"])
    if rule:
        for axis, value in (rule.get("values") or {}).items():
            values.setdefault(axis, value)

    weights = persona.get("value_weights") or {}
    axes = set(values) | set(state.values) | set(weights)
    gap = 0.0
    for axis in sorted(axes):
        weight = float(weights.get(axis, DEFAULT_VALUE_WEIGHT))
        gap += weight * (values.get(axis, 0.0) - state.values.get(axis, 0.0))

    axis_set = set(values) | set(state.values)
    relevant = tuple(sorted(
        (memory for memory in state.memories
         if memory.residue and axis_set & set(memory.axes)),
        key=lambda memory: memory.id))
    memory_weight = sum(memory.weight for memory in relevant)
    memory_factor = 1.0 + float(persona.get("memory_weight", 0.5)) * memory_weight

    emotion_factor = 1.0 + (float(persona.get("emotion_weight", 0.5))
                            * state.emotion_level
                            * option["emotions"].get(state.emotion, 0.0))
    score = gap * memory_factor * emotion_factor

    return {
        "index": index,
        "option": option["action"],
        "rule": rule["id"] if rule else (option.get("rule") or ""),
        "priority": rule["priority"] if rule else option["priority"],
        "score": round(score, 6),
        "value": round(gap, 6),
        "memory": round(memory_factor, 6),
        "emotion": round(emotion_factor, 6),
        "memories": tuple((memory.id, round(memory.weight, 6)) for memory in relevant),
    }


def decide(state: MindState, options, *, persona: dict | None = None) -> dict | None:
    """Choose one option.  Returns ``None`` when there is nothing to choose.

    Rules from the persona table win first.  If several options carry matching
    rules, they are scored by ``value gap * memory weight * emotion``; ties
    fall back to the rule priority (lower wins) and then to the rule id, which
    keeps the historical card behaviour bit for bit.
    """
    if state is None:
        state = MindState()
    persona = normalize_persona(persona) if persona is not None else default_persona()

    choices = [option for option in (
        _normalize_option(raw)
        for raw in ((options,) if isinstance(options, (str, dict)) else (options or ())))
        if option is not None]
    if not choices:
        return None

    rules = persona.get("rules") or ()
    for option in choices:
        option["_rules"] = _applicable_rules(option, rules)

    pairs = sum(len(option["_rules"]) for option in choices)
    rows = [_score_row(index, option, _best_rule(option), state, persona)
            for index, option in enumerate(choices)]

    if pairs == 1:
        chosen_index = next(index for index, option in enumerate(choices)
                            if option["_rules"])
    else:
        allowed = ({index for index, option in enumerate(choices) if option["_rules"]}
                   if pairs else set(range(len(choices))))
        chosen_index = min(
            (row for row in rows if row["index"] in allowed),
            key=lambda row: (-row["score"], row["priority"],
                             row["rule"] or row["option"]))["index"]

    chosen_row = rows[chosen_index]
    chosen_option = choices[chosen_index]
    chosen_rule = _best_rule(chosen_option)

    evidence = []
    if chosen_rule is not None:
        evidence.append({
            "kind": "rule",
            "id": chosen_rule["id"],
            "source": chosen_rule.get("source", ""),
            "priority": chosen_rule["priority"],
        })
    elif chosen_option.get("rule"):
        evidence.append({"kind": "rule", "id": chosen_option["rule"],
                         "source": "", "priority": chosen_option["priority"]})
    for memory_id, weight in chosen_row["memories"]:
        evidence.append({"kind": "memory", "id": memory_id, "weight": weight})
    if state.emotion_level > 0.0:
        evidence.append({"kind": "emotion", "id": state.emotion,
                         "level": round(state.emotion_level, 6)})
    if not evidence:
        evidence.append({"kind": "option", "id": chosen_option["action"],
                         "priority": chosen_option["priority"]})

    signal = (f"value {chosen_row['value']:.6f} * memory "
              f"{chosen_row['memory']:.6f} * emotion {chosen_row['emotion']:.6f}")
    if chosen_rule is None:
        reason = signal
    elif pairs == 1:
        reason = f"rule {chosen_rule['id']}"
    else:
        reason = f"rule conflict -> {chosen_rule['id']} ({signal})"

    return {
        "action": chosen_option["action"],
        "reason": reason,
        "evidence": evidence,
        "scores": [{
            "option": row["option"],
            "rule": row["rule"],
            "priority": row["priority"],
            "score": row["score"],
            "value": row["value"],
            "memory": row["memory"],
            "emotion": row["emotion"],
        } for row in rows],
    }


# ---- shadow observer --------------------------------------------------------
class MindShadow:
    """A read-only per-frame observer for the mind layer.

    ``__call__`` always returns ``True`` and never writes ``st``; it only reads
    ``st.score`` for ``emitted_*`` keys and appends events to its own memory
    stream.  Attaching it therefore cannot change the trajectory fingerprint.
    """

    PREFIX = "emitted_"

    def __init__(self, *, persona: dict | None = None, state: MindState | None = None,
                 options=(), trace: bool = False):
        self.persona = normalize_persona(persona) if persona is not None else default_persona()
        self.state = state if state is not None else MindState()
        self.options = tuple(options)
        self._seen = set()
        self._trace = []
        self._trace_enabled = bool(trace)
        self._frames = 0

    def __call__(self, frame, st, traj=None) -> bool:
        self._frames += 1
        score = getattr(st, "score", None)
        if isinstance(score, dict):
            for key in sorted(score, key=str):
                name = str(key)
                if not name.startswith(self.PREFIX) or name in self._seen:
                    continue
                self._seen.add(name)
                event = name[len(self.PREFIX):]
                try:
                    weight = abs(float(score[key]))
                except (TypeError, ValueError):
                    weight = 0.0
                self.state = self.state.remember(
                    event, weight=weight, frame=frame, persona=self.persona)
        if self._trace_enabled and self.options:
            decision = decide(self.state, self.options, persona=self.persona)
            if decision is not None:
                self._trace.append({"frame": _as_int(frame, -1), "decision": decision})
        return True

    # -- optional switches ----------------------------------------------------
    def record_trace(self, enabled: bool = True) -> "MindShadow":
        """Turn decision tracing on/off; returning ``self`` allows chaining."""
        self._trace_enabled = bool(enabled)
        return self

    @property
    def trace(self) -> tuple:
        return tuple(self._trace)

    @property
    def frames(self) -> int:
        return self._frames

    def summary(self) -> dict:
        return {
            "character": self.state.character,
            "memories": len(self.state.memories),
            "emotion": self.state.emotion,
            "emotion_level": round(self.state.emotion_level, 6),
            "frames": self._frames,
            "traced": len(self._trace),
        }

    def describe(self) -> list:
        """A short, deterministic readout; no state is written anywhere."""
        summary = self.summary()
        values = ",".join(f"{axis}:{value:.4f}"
                          for axis, value in sorted(self.state.values.items()))
        return [
            f"character={summary['character'] or '-'}",
            f"memories={summary['memories']} frames={summary['frames']}",
            f"emotion={summary['emotion']}:{summary['emotion_level']:.4f}",
            f"values={values or '-'}",
            f"traced={summary['traced']}",
        ]
