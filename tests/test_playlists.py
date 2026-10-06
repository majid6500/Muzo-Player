from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.playlist_service import PlaylistService
from app.data.database import Database
from app.data.playlist_repository import PlaylistRepository
from app.data.track_repository import TrackRepository
from app.models import NewTrack


class PlaylistServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = Database(Path(self.temp_dir.name) / "library.db")
        self.addCleanup(self.database.close)
        self.tracks = TrackRepository(self.database)
        self.track_paths = [
            Path(self.temp_dir.name) / f"track-{index}.mp3"
            for index in range(3)
        ]
        self.tracks.add_many(
            [
                NewTrack(str(path), f"Track {index}", "Artist", "Album", 1000)
                for index, path in enumerate(self.track_paths, start=1)
            ]
        )
        self.service = PlaylistService(PlaylistRepository(self.database))
        self.errors: list[str] = []
        self.service.error_occurred.connect(self.errors.append)

    def test_create_add_tracks_reorder_and_remove(self) -> None:
        playlist = self.service.create(" Road trip ")
        self.assertIsNotNone(playlist)
        assert playlist is not None

        self.assertEqual(self.service.add_tracks(playlist.id, [3, 1, 2, 1]), 3)
        self.assertEqual(self.service.add_tracks(playlist.id, [2]), 0)
        self.assertEqual(self.service.track_ids(playlist.id), [3, 1, 2])

        self.assertTrue(self.service.set_track_order(playlist.id, [2, 3, 1]))
        self.assertEqual(self.service.track_ids(playlist.id), [2, 3, 1])
        self.assertTrue(self.service.remove_track(playlist.id, 3))
        self.assertEqual(self.service.track_ids(playlist.id), [2, 1])

    def test_duplicate_and_empty_names_are_reported(self) -> None:
        self.assertIsNotNone(self.service.create("Morning"))
        self.assertIsNone(self.service.create(" morning "))
        self.assertIsNone(self.service.create("  "))
        self.assertEqual(len(self.errors), 2)

    def test_track_and_playlist_deletions_cascade_membership(self) -> None:
        playlist = self.service.create("Favorites mix")
        assert playlist is not None
        self.service.add_tracks(playlist.id, [1, 2, 3])

        self.tracks.delete_many([2])
        self.assertEqual(self.service.track_ids(playlist.id), [1, 3])

        self.assertTrue(self.service.delete(playlist.id))
        self.assertEqual(self.service.playlists(), [])


if __name__ == "__main__":
    unittest.main()
