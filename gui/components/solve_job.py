"""Runs run_analysis.py as a QProcess so CalculiX solving never blocks the GUI.

Writes the exact turbine config the viewport rendered (not the bare
data/default_turbine.json default) so the solve always matches what's on
screen, then streams stdout/stderr into the caller via signals.
"""
import json
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal


class SolveRunner(QObject):

    progress = Signal(str)
    finished = Signal(bool, str)   # success, out_dir (as str)

    def __init__(self, project_path, config_dict, v_ref, bearing_deg, mesh_size=1.0, ccx_path=None, parent=None):
        super().__init__(parent)
        self.project_path = Path(project_path)
        self.config_dict = config_dict
        self.v_ref = v_ref
        self.bearing_deg = bearing_deg
        self.ccx_path = ccx_path
        self.mesh_size = mesh_size
        self.process = None
        self.out_dir = self.project_path / "out"

    def start(self):
        import shutil
        if not self.ccx_path and not shutil.which("ccx") and not __import__("os").environ.get("CCX_PATH"):
            self.progress.emit(
                "CalculiX (ccx) was not found. Set CCX_PATH, or pass a path "
                "explicitly, before solving."
            )
            self.finished.emit(False, str(self.out_dir))
            return
        config_dir = self.project_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "solve_turbine.json"
        config_path.write_text(json.dumps(self.config_dict, indent=2), encoding="utf-8")

        root = Path(__file__).resolve().parents[2]  # repo root
        args = [
            str(root / "run_analysis.py"),
            "--config", str(config_path),
            "--mesh-size", str(self.mesh_size),
            "--wind-speed", str(self.v_ref),
            "--wind-direction", str(self.bearing_deg),
            "--output", str(self.out_dir),
        ]
        if self.ccx_path:
            args += ["--ccx", self.ccx_path]

        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(root))
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_output)
        self.process.finished.connect(self._on_finished)
        self.process.start(sys.executable, args)

    def cancel(self):
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            self.process.kill()

    def _on_output(self):
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            if line.strip():
                self.progress.emit(line)

    def _on_finished(self, exit_code, exit_status):
        success = exit_code == 0 and exit_status == QProcess.NormalExit
        self.finished.emit(success, str(self.out_dir))