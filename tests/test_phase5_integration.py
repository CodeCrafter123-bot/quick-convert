"""Phase 5: safe drops, Shift+drag gesture, drop bubble, single instance, Send to, quit/close."""

from __future__ import annotations

import os
import sys
import uuid

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDragEnterEvent, QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.integration import windows  # noqa: E402
from app.integration.gesture import DragGestureDetector, GestureState  # noqa: E402
from app.integration.single_instance import InstanceServer, send_to_running  # noqa: E402
from app.models import ConversionRequest, FileType  # noqa: E402
from app.storage.settings import UserSettings  # noqa: E402
from app.ui.app import QuickConvertApp  # noqa: E402
from app.ui.drop_bubble import DropBubble, GlobalDragWatcher  # noqa: E402
from app.ui.main_window import DropZone, MainWindow  # noqa: E402
from tests.test_ui import wait_until  # noqa: E402

ALL = Qt.DropAction.CopyAction | Qt.DropAction.MoveAction | Qt.DropAction.LinkAction


@pytest.fixture
def no_dialogs(monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)


def drop_event(path, possible=ALL, proposed=Qt.DropAction.MoveAction,
               mods=Qt.KeyboardModifier.ShiftModifier):
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(path))])
    ev = QDropEvent(QPointF(5, 5), possible, md, Qt.MouseButton.NoButton, mods)
    ev.setDropAction(proposed)
    ev._md = md  # keep the mime data alive
    return ev


# --- drops never report "Move" (Explorer would delete the original) ------------------

@pytest.mark.parametrize("target_cls", [DropZone, DropBubble])
def test_shift_drop_is_reported_as_copy(qapp, png_file, target_cls):
    target = target_cls()
    received = []
    target.file_dropped.connect(lambda *args: received.append(args[0]))
    ev = drop_event(png_file)
    target.dropEvent(ev)
    assert ev.isAccepted()
    assert ev.dropAction() == Qt.DropAction.CopyAction
    assert received == [png_file]
    assert png_file.exists()


@pytest.mark.parametrize("target_cls", [DropZone, DropBubble])
def test_move_only_drop_is_refused(qapp, png_file, target_cls):
    target = target_cls()
    received = []
    target.file_dropped.connect(lambda *args: received.append(args[0]))
    ev = drop_event(png_file, possible=Qt.DropAction.MoveAction)
    target.dropEvent(ev)
    assert not ev.isAccepted()
    assert received == []


def test_drag_enter_also_reports_copy(qapp, png_file):
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(png_file))])
    ev = QDragEnterEvent(QPointF(5, 5), ALL, md, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.ShiftModifier)
    ev.setDropAction(Qt.DropAction.MoveAction)
    DropZone().dragEnterEvent(ev)
    assert ev.isAccepted() and ev.dropAction() == Qt.DropAction.CopyAction


def test_multiple_files_rejected(qapp, png_file, jpeg_file):
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(png_file)), QUrl.fromLocalFile(str(jpeg_file))])
    ev = QDropEvent(QPointF(5, 5), ALL, md, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    DropBubble().dropEvent(ev)
    assert not ev.isAccepted()


# --- gesture detector -----------------------------------------------------------------

def launch_second_instance(path, name):
    """Run send_to_running in a real separate process, like a second app launch."""
    import subprocess

    code = ("import sys; from pathlib import Path; "
            "from app.integration.single_instance import send_to_running; "
            "sys.exit(0 if send_to_running(Path(sys.argv[1]), sys.argv[2], 5000) else 1)")
    return subprocess.Popen([sys.executable, "-c", code, str(path), name],
                            cwd=os.path.dirname(os.path.dirname(__file__)))


def run(detector, steps):
    return [detector.update(*step) for step in steps]


def test_shift_drag_shows_then_release_hides():
    d = DragGestureDetector(threshold=10)
    out = run(d, [(True, False, (0, 0), False),    # press
                  (True, False, (5, 0), False),    # small move
                  (True, True, (6, 0), False),     # shift, not yet a drag
                  (True, True, (20, 0), False),    # drag + shift
                  (True, True, (40, 0), False),
                  (False, True, (40, 0), False)])  # release
    assert out == [None, None, None, "show", None, "hide"]
    assert d.state is GestureState.IDLE


def test_shift_pressed_after_drag_started():
    d = DragGestureDetector(threshold=10)
    out = run(d, [(True, False, (0, 0), False), (True, False, (50, 0), False),
                  (True, True, (60, 0), False)])
    assert out == [None, None, "show"]


def test_releasing_shift_hides_and_pressing_again_reshows():
    d = DragGestureDetector(threshold=10)
    out = run(d, [(True, True, (0, 0), False), (True, True, (30, 0), False),
                  (True, False, (40, 0), False), (True, True, (50, 0), False)])
    assert out == [None, "show", "hide", "show"]


def test_plain_drag_and_click_do_nothing():
    d = DragGestureDetector(threshold=10)
    assert run(d, [(True, False, (0, 0), False), (True, False, (100, 0), False),
                   (False, False, (100, 0), False)]) == [None, None, None]
    assert run(d, [(True, True, (0, 0), False), (False, True, (0, 0), False)]) == [None, None]


def test_drags_starting_on_own_window_are_ignored():
    d = DragGestureDetector(threshold=10)
    out = run(d, [(True, True, (0, 0), True), (True, True, (100, 0), False),
                  (False, True, (100, 0), False)])
    assert out == [None, None, None]
    assert d.state is GestureState.IDLE


# --- watcher + bubble -------------------------------------------------------------------

def test_watcher_shows_bubble_beside_cursor_and_hides_after_release(qapp):
    state = {"input": (False, False), "pos": QPoint(500, 400)}
    watcher = GlobalDragWatcher(lambda: state["input"], cursor_pos=lambda: state["pos"])
    watcher.hide_timer.setInterval(10)
    try:
        state["input"] = (True, False)
        watcher.poll()
        state["input"], state["pos"] = (True, True), QPoint(540, 400)
        watcher.poll()
        bubble = watcher.bubble
        assert bubble.isVisible()
        # Beside the cursor, never under it, so other apps' Shift+drags aren't intercepted.
        assert not bubble.geometry().contains(state["pos"])
        state["input"] = (False, False)
        watcher.poll()
        assert wait_until(lambda: not bubble.isVisible(), timeout=2)
    finally:
        watcher.shutdown()


def test_bubble_stays_on_screen_near_corner(qapp):
    bubble = DropBubble()
    screen = qapp.primaryScreen().availableGeometry()
    bubble.show_near(screen.bottomRight() - QPoint(2, 2))
    assert screen.contains(bubble.geometry())
    bubble.close()


def test_watcher_disables_itself_if_polling_fails(qapp):
    def broken():
        raise OSError("no input")
    watcher = GlobalDragWatcher(broken)
    watcher.set_enabled(True)
    watcher.poll()
    assert not watcher.is_enabled()
    watcher.shutdown()


# --- single instance -------------------------------------------------------------------

def test_second_launch_hands_file_to_running_instance(qapp, png_file):
    name = f"qc-test-{uuid.uuid4().hex[:8]}"
    server = InstanceServer(name)
    assert server.listen()
    received = []
    server.open_requested.connect(received.append)
    try:
        proc = launch_second_instance(png_file, name)
        assert wait_until(lambda: received, timeout=15)
        assert received == [png_file.resolve()]
        assert wait_until(lambda: proc.poll() is not None, timeout=15) and proc.returncode == 0
    finally:
        server.close()


def test_no_running_instance(qapp):
    assert not send_to_running(None, f"qc-none-{uuid.uuid4().hex[:8]}", timeout_ms=200)


# --- Send to shortcut -------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_send_to_shortcut_install_and_remove(tmp_path):
    folder = tmp_path / "SendTo with spaces & 'quotes'"
    link = windows.install_send_to(folder)
    assert link.exists() and windows.is_send_to_installed(folder)
    target, args, workdir = windows.launch_command()
    assert args == "-m app" and target.name.lower() in ("pythonw.exe", "python.exe")
    windows.uninstall_send_to(folder)
    assert not windows.is_send_to_installed(folder)


# --- closing and quitting ------------------------------------------------------------------

def test_close_hides_to_tray_when_enabled(qapp, no_dialogs):
    w = MainWindow(UserSettings())
    w.hide_on_close = True
    hidden = []
    w.hidden_to_tray.connect(lambda: hidden.append(True))
    w.show()
    w.close()
    assert hidden and not w.isVisible()
    w.hide_on_close = False
    w.close()


def test_quit_asks_when_jobs_are_running(qapp, no_dialogs, monkeypatch, jpeg_file, out_dir):
    import threading

    from app.services import conversion
    from app.services.jobs import JobManager

    gate = threading.Event()

    def slow(req, cc, jid):
        gate.wait(10)
        return conversion.run(req, cc, jid)

    w = MainWindow(UserSettings())
    w.jobs.shutdown()
    w.jobs = JobManager(runner=slow, on_update=w.signals.updated.emit)
    w.submit(ConversionRequest(jpeg_file, FileType.PNG, out_dir / "a.png"))
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.No)
    assert not w.confirm_quit()
    assert "1 job(s) are still running" in asked[0]
    gate.set()
    assert wait_until(lambda: w.jobs.active_count() == 0)
    assert w.confirm_quit()
    w.close()


def test_app_routes_bubble_and_second_instance_to_wheel(qapp, no_dialogs, png_file, tmp_path,
                                                        monkeypatch):
    name = f"qc-app-{uuid.uuid4().hex[:8]}"
    opened = []
    monkeypatch.setattr(MainWindow, "open_wheel", lambda self, pos: opened.append(pos))
    settings_path = tmp_path / "settings.json"
    app = QuickConvertApp(qapp, UserSettings(), settings_path, server_name=name,
                          read_input=lambda: (False, False))
    try:
        assert app.watcher is not None and app.watcher.is_enabled()
        app.watcher.file_dropped.emit(png_file, QPoint(10, 10))
        assert app.window.info.path == png_file and opened == [QPoint(10, 10)]

        launch_second_instance(png_file, name)
        assert wait_until(lambda: len(opened) == 2, timeout=15)

        app.set_global_drag(False)
        assert not app.watcher.is_enabled()
        assert UserSettings.load(settings_path).global_drag is False
    finally:
        app.shutdown()
