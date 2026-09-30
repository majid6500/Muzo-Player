from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from app.core.video_library_service import VideoLibraryService
from app.data.database import Database
from app.data.video_repository import VideoRepository


class VideoLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.video_path = root / "sample.mp4"
        self.video_path.touch()
        self.unsupported_path = root / "notes.txt"
        self.unsupported_path.touch()

        self.database = Database(root / "library.db")
        self.service = VideoLibraryService(VideoRepository(self.database))
        self.addCleanup(self.database.close)
        self.addCleanup(self.service.shutdown)

    def test_import_deduplicates_rejects_unsupported_and_removes_entry(self) -> None:
        loop = QEventLoop()
        results: list[tuple[int, int, int]] = []
        self.service.import_finished.connect(
            lambda added, duplicates, unreadable: (
                results.append((added, duplicates, unreadable)), loop.quit()
            )
        )
        self.service.add_files(
            [
                str(self.video_path),
                str(self.video_path),
                str(self.unsupported_path),
            ]
        )
        QTimer.singleShot(3000, loop.quit)
        loop.exec()

        self.assertEqual(results, [(1, 1, 1)])
        videos = self.service.videos()
        self.assertEqual(len(videos), 1)
        self.assertEqual(videos[0].title, "sample")

        self.service.remove_many([videos[0].id])
        self.assertEqual(self.service.videos(), [])


if __name__ == "__main__":
    unittest.main()