"""Asking the user for what the file does not contain.

The prompting layer is deliberately thin and pluggable: `find_gaps` produces
Questions, a Prompter turns Questions into answers, and `apply_answers` writes
them back.  The CLI implements one Prompter; the napari widget implements
another; a YAML answer file implements a third for batch runs.
"""

from __future__ import annotations

from typing import Iterable, Protocol

from .checklist import Level, Scope
from .gaps import Question
from .schema import Record, Source, Value, path_set

SKIP_TOKENS = {"", "s", "skip"}
NA_TOKENS = {"n/a", "na", "none", "not applicable"}


class Prompter(Protocol):
    def ask(self, question: Question) -> str | None:
        """Return the raw answer, or None to leave the field unanswered."""

    def intro(self, questions: list[Question], record: Record) -> None:
        ...


class NullPrompter:
    """Non-interactive: leaves every gap unfilled (batch/CI use)."""

    def intro(self, questions, record) -> None:
        return None

    def ask(self, question: Question) -> str | None:
        return None


class MappingPrompter:
    """Answers supplied up front, keyed by checklist path.

    Accepts both exact paths ('channels[0].detector.model') and per-channel
    templates ('channels[].detector.model') that apply to every channel.
    """

    def __init__(self, answers: dict[str, object]):
        self.answers = {str(k): v for k, v in answers.items()}

    def intro(self, questions, record) -> None:
        return None

    def ask(self, question: Question) -> str | None:
        if question.path in self.answers:
            return str(self.answers[question.path])
        template = question.requirement.path.replace("[{c}]", "[]")
        if template in self.answers:
            return str(self.answers[template])
        generic = question.requirement.path.replace("[{c}]", "")
        if generic in self.answers:
            return str(self.answers[generic])
        return None


class ChainPrompter:
    """Try each prompter in turn (e.g. answer file first, then interactive)."""

    def __init__(self, *prompters: Prompter):
        self.prompters = prompters

    def intro(self, questions, record) -> None:
        for p in self.prompters:
            p.intro(questions, record)

    def ask(self, question: Question) -> str | None:
        for p in self.prompters:
            answer = p.ask(question)
            if answer is not None:
                return answer
        return None


class CLIPrompter:
    """Interactive terminal prompting, grouped by checklist category."""

    def __init__(self, show_examples: bool = True):
        self.show_examples = show_examples
        self._seen_category: str | None = None

    def intro(self, questions: list[Question], record: Record) -> None:
        blocking = [q for q in questions if q.level is not Level.RECOMMENDED]
        print(f"\n{len(questions)} field(s) could not be read from the file "
              f"({len(blocking)} required by the checklist).")
        print("Press Enter to skip a field, or type 'n/a' if it does not apply.\n")

    def ask(self, question: Question) -> str | None:
        req = question.requirement
        if req.category != self._seen_category:
            self._seen_category = req.category
            print(f"\n--- {req.category} ---")
        marker = {Level.REQUIRED: "*", Level.CONDITIONAL: "*",
                  Level.RECOMMENDED: " "}[req.level]
        print(f"\n{marker} {question.label}")
        if self.show_examples and req.example:
            print(f"    e.g. {req.example}")
        if req.choices:
            print(f"    options: {', '.join(req.choices)}")
        if req.note:
            print(f"    note: {req.note}")
        unit = f" [{req.unit}]" if req.unit else ""
        try:
            answer = input(f"  > value{unit}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n(input closed; remaining fields left unanswered)")
            raise
        return None if answer.lower() in SKIP_TOKENS else answer


# --------------------------------------------------------------------------


def coerce(answer: str, kind: str):
    text = answer.strip()
    if text.lower() in NA_TOKENS:
        return "not applicable"
    if kind in ("float", "int"):
        cleaned = text.replace(",", ".")
        import re
        m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", cleaned)
        if m:
            value = float(m.group())
            return int(round(value)) if kind == "int" else value
        return text  # keep prose like "no averaging"
    return text


def run(record: Record, questions: Iterable[Question], prompter: Prompter
        ) -> dict[str, object]:
    """Ask each question and write the answers into the record.

    Returns the answers keyed by path, so instrument-scope ones can be saved
    to a profile afterwards.
    """
    answers: dict[str, object] = {}
    questions = list(questions)
    prompter.intro(questions, record)
    for question in questions:
        try:
            answer = prompter.ask(question)
        except (EOFError, KeyboardInterrupt):
            break
        if answer is None:
            continue
        value = coerce(answer, question.requirement.kind)
        if path_set(record, question.path,
                    Value(value, Source.USER, "answered by user",
                          question.requirement.unit), force=True):
            answers[question.path] = value
    return answers


def instrument_answers(answers: dict[str, object]) -> dict[str, object]:
    """Subset of answers that are stable per microscope, for the profile."""
    from .checklist import BY_PATH

    out = {}
    for path, value in answers.items():
        template = path
        if "channels[" in path:
            index = path.split("[", 1)[1].split("]", 1)[0]
            template = path.replace(f"[{index}]", "[{c}]")
        req = BY_PATH.get(template) or BY_PATH.get(path)
        if req and req.scope is Scope.INSTRUMENT:
            out[path] = value
    return out
