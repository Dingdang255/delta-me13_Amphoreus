"""Read-only dialogue runner over the compiled corpus.

A scene is a set of ordered lines linked by ``next``. The runner walks those
links and never mutates the records. When a line has more than one successor,
the caller must pick one -- the runner refuses to guess.

    runner = DialogueRunner.from_bundle(bundle, "SCN-001")
    while runner.current() is not None:
        line = runner.current()
        runner.advance()
"""
from __future__ import annotations

from dataclasses import dataclass, field


class DialogueError(RuntimeError):
    """Raised for unknown scenes, dangling links or an ambiguous step."""


@dataclass(frozen=True)
class Line:
    id: str
    scene: str
    order: int
    text: str
    speaker: str | None
    form: str
    next: tuple[str, ...]
    condition: str
    confidence: str
    source: str
    locator: str
    raw: dict = field(default_factory=dict)


def line_from_dict(obj: dict) -> Line:
    return Line(
        id=str(obj.get("id", "")),
        scene=str(obj.get("scene_id", "")),
        order=int(obj.get("order", 0)),
        text=str(obj.get("verbatim", "") or ""),
        speaker=obj.get("speaker_inferred") or obj.get("speaker"),
        form=str(obj.get("form", "") or ""),
        next=tuple(obj.get("next") or ()),
        condition=str(obj.get("condition", "") or ""),
        confidence=str(obj.get("confidence", "") or ""),
        source=str(obj.get("source", "") or ""),
        locator=str(obj.get("locator", "") or ""),
        raw=obj,
    )


class DialogueRunner:
    def __init__(self, scene_id: str, lines: list[dict], start: str | None = None):
        self.scene_id = scene_id
        self._lines = [line_from_dict(row) for row in lines]
        self._lines.sort(key=lambda line: line.order)
        self._by_id = {line.id: line for line in self._lines}
        if not self._lines:
            self._current = None
        elif start:
            if start not in self._by_id:
                raise DialogueError(f"start line {start!r} not in scene {scene_id!r}")
            self._current = self._by_id[start]
        else:
            self._current = self._lines[0]
        self.trace: list[str] = []
        if self._current is not None:
            self.trace.append(self._current.id)

    @classmethod
    def from_bundle(cls, bundle, scene_id: str, start: str | None = None) -> "DialogueRunner":
        rows = [entry.data for entry in bundle.of_kind("dialogue")
                if entry.get("scene_id") == scene_id]
        if not rows:
            raise DialogueError(f"scene {scene_id!r} has no dialogue lines")
        return cls(scene_id, rows, start)

    def current(self) -> Line | None:
        return self._current

    def finished(self) -> bool:
        return self._current is None

    def advance(self, choice: str | None = None) -> Line | None:
        if self._current is None:
            return None
        targets = self._current.next
        if not targets:
            self._current = None
            return None
        if len(targets) == 1:
            target = targets[0]
        elif choice is None:
            raise DialogueError(
                f"{self._current.id} has {len(targets)} successors; choose one of {targets}")
        elif choice in targets:
            target = choice
        else:
            raise DialogueError(f"choice {choice!r} not in {targets}")
        if target not in self._by_id:
            raise DialogueError(f"{self._current.id} -> {target} is dangling")
        self._current = self._by_id[target]
        self.trace.append(target)
        return self._current

    def lines(self) -> list[Line]:
        return list(self._lines)

    def reset(self) -> None:
        self._current = self._lines[0] if self._lines else None
        self.trace = [self._current.id] if self._current else []
