"""Capture the desktop app on an isolated, offscreen Qt surface."""

import ctypes
import os
from pathlib import Path
from tempfile import TemporaryDirectory

ctypes.windll.user32.SetProcessDPIAware()
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from spot2ytmusic import __version__
from spot2ytmusic.gui import MainWindow
from spot2ytmusic.models import Candidate, PlanEntry, Track
from spot2ytmusic.planner import save_plan, save_review


def main() -> None:
    app = QApplication([])
    for font_name in ("segoeui.ttf", "segoeuib.ttf"):
        QFontDatabase.addApplicationFont(str(Path("C:/Windows/Fonts") / font_name))
    with TemporaryDirectory() as temporary:
        plan_path = Path(temporary) / "road-trip.json"
        samples = [
            PlanEntry(
                Track("Road Trip", 1, "Midnight City", "M83", "Hurry Up, We're Dreaming", 243),
                "auto",
                "abcdefghijk",
                [
                    Candidate(
                        "abcdefghijk", "Midnight City", "M83", "Hurry Up, We're Dreaming", 243, "song", 0.98
                    )
                ],
            ),
            PlanEntry(
                Track("Road Trip", 2, "Kids", "MGMT", "Oracular Spectacular", 302),
                "review",
                "lmnopqrstuv",
                [
                    Candidate("lmnopqrstuv", "Kids", "MGMT", "Oracular Spectacular", 302, "song", 0.86),
                    Candidate("mnopqrstuvw", "Kids (Live)", "MGMT", "", 331, "video", 0.69),
                ],
                "Check this recording",
            ),
            PlanEntry(
                Track("Road Trip", 3, "Electric Feel", "MGMT", "Oracular Spectacular", 229),
                "auto",
                "opqrstuvwxy",
                [
                    Candidate(
                        "opqrstuvwxy", "Electric Feel", "MGMT", "Oracular Spectacular", 229, "song", 0.96
                    )
                ],
            ),
            PlanEntry(
                Track("Road Trip", 4, "[Unavailable track]", "", source_type="Unavailable"),
                "skip",
                note="Source track is unavailable on Spotify",
            ),
            PlanEntry(
                Track("Morning Mix", 1, "Dreams", "Fleetwood Mac", "Rumours", 257),
                "auto",
                "bcdefghijkl",
                [
                    Candidate(
                        "bcdefghijkl", "Dreams", "Fleetwood Mac", "Rumours", 257, "song", 0.98
                    )
                ],
            ),
        ]
        plan = {"schema": 1, "tool_version": __version__, "entries": [item.to_dict() for item in samples]}
        save_plan(plan_path, plan)
        save_review(plan_path.with_suffix(".review.csv"), plan)
        window = MainWindow()
        window.output_edit.setText("Documents\\Spot2YTMusic")
        window.tracks = [entry.track for entry in samples]
        window.sources_label.setText("Export_All.zip, 5 songs, 2 playlists")
        window._load_plan(plan_path, from_scan=True)
        window.playlist_list.item(1).setCheckState(Qt.Unchecked)
        window.table.selectRow(1)
        window.auth_edit.setPlaceholderText("Choose your local browser.json")
        window.show()
        app.processEvents()
        target = Path(__file__).resolve().parents[1] / "docs" / "screenshots" / "desktop.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(target)):
            raise RuntimeError("Screenshot capture failed")
        window.close()
        print(target)


if __name__ == "__main__":
    main()
