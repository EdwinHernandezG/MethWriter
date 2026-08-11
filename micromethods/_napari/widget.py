"""napari dock widget.

The widget is deliberately thin: it is just another Prompter implementation.
All extraction, checklist logic and rendering are shared with the CLI, so the
plugin can never drift from the command-line behaviour.
"""

from __future__ import annotations

from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QGroupBox,
                            QHBoxLayout, QLabel, QLineEdit, QPushButton,
                            QScrollArea, QTextEdit, QVBoxLayout, QWidget)

from .. import profiles as profile_store
from .. import readers, render
from ..gaps import Question, find_gaps
from ..prompt import coerce
from ..schema import Source, Value, path_set


class QtFormPrompter:
    """Collects answers from Qt widgets instead of stdin."""

    def __init__(self, fields: dict[str, QWidget]):
        self.fields = fields

    def intro(self, questions, record) -> None:
        return None

    def ask(self, question: Question) -> str | None:
        widget = self.fields.get(question.path)
        if widget is None:
            return None
        text = widget.currentText() if isinstance(widget, QComboBox) else widget.text()
        return text.strip() or None


class MethodsWidget(QWidget):
    def __init__(self, viewer=None):
        super().__init__()
        self.viewer = viewer
        self.record = None
        self.fields: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)

        picker = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Path to .lif / .czi / .ome.tif ...")
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse)
        load = QPushButton("Read metadata")
        load.clicked.connect(self._load)
        picker.addWidget(self.path_edit)
        picker.addWidget(browse)
        picker.addWidget(load)
        layout.addLayout(picker)

        self.status = QLabel("No file loaded.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.form_box = QGroupBox("Missing metadata")
        self.form_layout = QFormLayout(self.form_box)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form_box)
        layout.addWidget(scroll, stretch=2)

        buttons = QHBoxLayout()
        generate = QPushButton("Generate methods")
        generate.clicked.connect(self._generate)
        copy = QPushButton("Copy")
        copy.clicked.connect(self._copy)
        save = QPushButton("Save report")
        save.clicked.connect(self._save)
        buttons.addWidget(generate)
        buttons.addWidget(copy)
        buttons.addWidget(save)
        layout.addLayout(buttons)

        self.output = QTextEdit()
        self.output.setReadOnly(False)
        layout.addWidget(self.output, stretch=3)

    # -- actions ---------------------------------------------------------
    def _browse(self) -> None:
        exts = " ".join(f"*{e}" for e in readers.SUPPORTED)
        path, _ = QFileDialog.getOpenFileName(self, "Select image", "",
                                              f"Microscopy images ({exts})")
        if path:
            self.path_edit.setText(path)
            self._load()

    def _current_path(self) -> Path | None:
        text = self.path_edit.text().strip()
        if text:
            return Path(text)
        if self.viewer is not None and self.viewer.layers.selection:
            layer = list(self.viewer.layers.selection)[0]
            source = getattr(layer, "source", None)
            if source is not None and getattr(source, "path", None):
                return Path(source.path)
        return None

    def _load(self) -> None:
        path = self._current_path()
        if path is None:
            self.status.setText("Select a file, or a layer that was opened from disk.")
            return
        try:
            self.record = readers.read(path)
        except Exception as exc:
            self.status.setText(f"Could not read metadata: {exc}")
            return
        profile = profile_store.apply_best(self.record)
        report = find_gaps(self.record)
        self._build_form(report.questions)
        note = f" | profile: {profile.key}" if profile else ""
        self.status.setText(
            f"{self.record.file_format}{note} | "
            f"{report.completeness * 100:.0f}% of required fields found in the file | "
            f"{len(report.blocking)} to complete below")

    def _build_form(self, questions: list[Question]) -> None:
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.fields.clear()
        for question in questions:
            req = question.requirement
            if req.choices:
                widget: QWidget = QComboBox()
                widget.setEditable(True)
                widget.addItems([""] + list(req.choices))
            else:
                widget = QLineEdit()
                widget.setPlaceholderText(req.example or "")
            widget.setToolTip(f"{req.category} - {req.item}\nLiMi: {req.limi or 'n/a'}")
            label = QLabel(question.label)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.form_layout.addRow(label, widget)
            self.fields[question.path] = widget

    def _generate(self) -> None:
        if self.record is None:
            self.status.setText("Read a file first.")
            return
        prompter = QtFormPrompter(self.fields)
        for path, widget in self.fields.items():
            text = (widget.currentText() if isinstance(widget, QComboBox)
                    else widget.text()).strip()
            if not text:
                continue
            from ..checklist import BY_PATH
            template = path
            if "channels[" in path:
                index = path.split("[", 1)[1].split("]", 1)[0]
                template = path.replace(f"[{index}]", "[{c}]")
            req = BY_PATH.get(template)
            value = coerce(text, req.kind if req else "str")
            path_set(self.record, path,
                     Value(value, Source.USER, "entered in napari",
                           req.unit if req else None), force=True)
        report = find_gaps(self.record)
        self.output.setPlainText(render.report_markdown(self.record, report))
        self.status.setText(
            f"{report.completeness * 100:.0f}% complete | "
            f"{len(report.blocking)} field(s) still missing")

    def _copy(self) -> None:
        from qtpy.QtWidgets import QApplication
        QApplication.clipboard().setText(self.output.toPlainText())
        self.status.setText("Report copied to clipboard.")

    def _save(self) -> None:
        if self.record is None:
            return
        default = str(Path(self.record.file_path).with_suffix("")) + "_methods.md"
        path, _ = QFileDialog.getSaveFileName(self, "Save report", default,
                                              "Markdown (*.md)")
        if not path:
            return
        Path(path).write_text(self.output.toPlainText())
        report = find_gaps(self.record)
        Path(path).with_suffix(".json").write_text(
            render.metadata_json(self.record, report))
        self.status.setText(f"Saved {path}")


def methods_widget(viewer=None):  # napari hook target
    return MethodsWidget(viewer)
