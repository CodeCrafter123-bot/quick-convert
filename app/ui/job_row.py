"""One row per job: status, progress, cancel, and Open File / Show in Folder when done."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from app.models import ConversionJob, JobStatus

STATUS_TEXT = {
    JobStatus.QUEUED: "Queued",
    JobStatus.RUNNING: "Converting…",
    JobStatus.COMPLETED: "Done",
    JobStatus.FAILED: "Failed",
    JobStatus.CANCELLED: "Cancelled",
}


def show_in_folder(path: Path) -> None:
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


class JobRow(QFrame):
    cancel_requested = Signal(str)

    def __init__(self, job: ConversionJob):
        super().__init__()
        self.job_id = job.id
        self.setFrameShape(QFrame.Shape.StyledPanel)
        req = job.request

        self.title = QLabel(f"<b>{req.source_path.name}</b> → {req.destination_path.name}")
        self.title.setTextFormat(Qt.TextFormat.RichText)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(6)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.job_id))
        self.open_btn = QPushButton("Open File")
        self.folder_btn = QPushButton("Show in Folder")
        self.open_btn.hide()
        self.folder_btn.hide()

        top = QHBoxLayout()
        top.addWidget(self.title, 1)
        top.addWidget(self.open_btn)
        top.addWidget(self.folder_btn)
        top.addWidget(self.cancel_btn)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        self.update_job(job)

    def update_job(self, job: ConversionJob) -> None:
        text = STATUS_TEXT[job.status]
        if job.status is JobStatus.RUNNING:
            self.progress.setRange(0, 0)  # busy indicator
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(1 if job.status is JobStatus.COMPLETED else 0)
        self.progress.setVisible(not job.status.is_final)
        self.cancel_btn.setVisible(not job.status.is_final)

        if job.status is JobStatus.FAILED and job.error_message:
            text = f"Failed: {job.error_message}"
        elif job.status is JobStatus.COMPLETED and job.result:
            output = job.result.output_paths[0]
            size_kb = job.result.output_sizes[0] / 1024
            text = f"Saved {output} ({size_kb:,.0f} KB)"
            for warning in job.result.warnings:
                text += f"\n⚠ {warning}"
            self._wire_output_buttons(output)
        self.status.setText(text)

    def _wire_output_buttons(self, output: Path) -> None:
        if self.open_btn.isVisibleTo(self):  # a job completes only once
            return
        self.open_btn.show()
        self.folder_btn.show()
        self.open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(output))))
        self.folder_btn.clicked.connect(lambda: show_in_folder(output))
