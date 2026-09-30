from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal

from app.core.audio_backend import AudioBackend, PlaybackState, volume_to_linear
from app.core.playback_queue import PlaybackQueue, RepeatMode
from app.core.player_service import PlayerService
from app.models import Track
from app.ui.screens.home_screen import matches_track_query


class FakeAudioBackend(AudioBackend):
    def __init__(self) -> None:
        super().__init__()
        self._state = PlaybackState.STOPPED
        self._position = 0
        self.loaded_paths: list[str] = []
        self.seek_positions: list[int] = []
        self.play_count = 0
        self.stop_count = 0
        self.volume = 0.0

    @property
    def state(self) -> PlaybackState:
        return self._state

    @property
    def position(self) -> int:
        return self._position

    def load(self, path: str) -> None:
        self.loaded_paths.append(path)
        self._position = 0

    def unload(self) -> None:
        self._state = PlaybackState.STOPPED

    def play(self) -> None:
        self.play_count += 1
        self._state = PlaybackState.PLAYING
        self.state_changed.emit(self._state)

    def pause(self) -> None:
        self._state = PlaybackState.PAUSED
        self.state_changed.emit(self._state)

    def stop(self) -> None:
        self.stop_count += 1
        self._state = PlaybackState.STOPPED
        self._position = 0

    def seek(self, position_ms: int) -> None:
        self.seek_positions.append(position_ms)
        self._position = position_ms

    def set_volume(self, volume: float) -> None:
        self.volume = volume


class FakeLibrary(QObject):
    library_changed = Signal()

    def __init__(self, tracks: list[Track]) -> None:
        super().__init__()
        self._tracks = tracks

    def tracks(self) -> list[Track]:
        return list(self._tracks)

    def get_track(self, track_id: int) -> Track | None:
        return next((track for track in self._tracks if track.id == track_id), None)


class FakeSettings:
    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self.values = dict(initial or {})

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.values.get(key, default)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


class PlaybackQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.queue = PlaybackQueue()

    def test_next_repeat_all_and_repeat_one(self) -> None:
        self.queue.set_tracks([1, 2, 3])
        self.assertTrue(self.queue.set_current(1))
        self.assertEqual(self.queue.next_id(auto=False), 2)
        self.assertEqual(self.queue.next_id(auto=False), 3)
        self.assertIsNone(self.queue.next_id(auto=False))

        self.queue.set_repeat(RepeatMode.ALL)
        self.assertEqual(self.queue.next_id(auto=False), 1)
        self.queue.set_repeat(RepeatMode.ONE)
        self.assertEqual(self.queue.next_id(auto=True), 1)
        self.assertEqual(self.queue.next_id(auto=False), 2)

    def test_previous_wraps_only_when_repeating(self) -> None:
        self.queue.set_tracks([1, 2])
        self.queue.set_current(1)
        self.assertEqual(self.queue.previous_id(), 1)

        self.queue.set_repeat(RepeatMode.ALL)
        self.assertEqual(self.queue.previous_id(), 2)

    def test_shuffle_preserves_current_track(self) -> None:
        self.queue.set_tracks([1, 2, 3])
        self.queue.set_current(2)
        with patch("app.core.playback_queue.random.shuffle", side_effect=lambda ids: ids.reverse()):
            self.queue.set_shuffle(True)

        self.assertEqual(self.queue.current_id, 2)
        self.assertEqual(self.queue.next_id(auto=False), 3)

    def test_removing_tracks_while_shuffled_keeps_current(self) -> None:
        self.queue.set_tracks([1, 2, 3])
        self.queue.set_current(2)
        with patch("app.core.playback_queue.random.shuffle", side_effect=lambda ids: ids.reverse()):
            self.queue.set_shuffle(True)
            self.queue.set_tracks([2, 3, 4])

        self.assertEqual(self.queue.current_id, 2)
        self.assertEqual(self.queue.next_id(auto=False), 3)
        self.assertEqual(len(self.queue), 3)

    def test_move_after_current_changes_next_track(self) -> None:
        self.queue.set_tracks([1, 2, 3, 4])
        self.queue.set_current(1)

        self.assertTrue(self.queue.move_after_current(4))

        self.assertEqual(self.queue.current_id, 1)
        self.assertEqual(self.queue.next_id(auto=False), 4)
        self.assertEqual(self.queue.track_ids, (1, 4, 2, 3))

    def test_manual_order_survives_library_refresh(self) -> None:
        self.queue.set_tracks([1, 2, 3])
        self.queue.set_current(1)
        self.queue.set_order([1, 3, 2])

        self.queue.set_tracks([1, 2, 3, 4])

        self.assertEqual(self.queue.track_ids, (1, 3, 2, 4))
        self.assertEqual(self.queue.current_id, 1)

    def test_set_order_rejects_missing_or_duplicate_tracks(self) -> None:
        self.queue.set_tracks([1, 2, 3])
        with self.assertRaises(ValueError):
            self.queue.set_order([1, 2, 2])


class TrackSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.track = Track(1, "song.mp3", "Blue Morning", "The Example", "First Light", 1000)

    def test_matches_title_artist_and_album_without_case_sensitivity(self) -> None:
        for query in ("blue", "EXAMPLE", "first light"):
            with self.subTest(query=query):
                self.assertTrue(matches_track_query(self.track, query))

    def test_blank_query_matches_and_unrelated_query_does_not(self) -> None:
        self.assertTrue(matches_track_query(self.track, "  "))
        self.assertFalse(matches_track_query(self.track, "midnight"))


class VolumeMappingTests(unittest.TestCase):
    def test_volume_slider_maps_linearly_and_clamps(self) -> None:
        self.assertEqual(volume_to_linear(0), 0.0)
        self.assertEqual(volume_to_linear(0.5), 0.5)
        self.assertEqual(volume_to_linear(0.7), 0.7)
        self.assertEqual(volume_to_linear(1), 1.0)
        self.assertEqual(volume_to_linear(-0.2), 0.0)
        self.assertEqual(volume_to_linear(1.2), 1.0)


class PlayerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.tracks = []
        for track_id in (1, 2, 3):
            path = Path(self.temp_dir.name) / f"track-{track_id}.mp3"
            path.touch()
            self.tracks.append(
                Track(track_id, str(path), f"Track {track_id}", "Artist", "Album", 1000)
            )
        self.backend = FakeAudioBackend()
        self.library = FakeLibrary(self.tracks)
        self.settings = FakeSettings()
        self.player = PlayerService(
            self.backend, self.library, PlaybackQueue(), self.settings
        )

    def test_play_after_last_track_ends_rewinds_and_resumes(self) -> None:
        self.assertTrue(self.player.play_track(3))
        self.backend.finished.emit()
        self.assertEqual(self.backend.stop_count, 1)

        self.player.play()

        self.assertEqual(self.backend.seek_positions, [0])
        self.assertEqual(self.backend.state, PlaybackState.PLAYING)

    def test_repeat_one_reloads_current_media(self) -> None:
        self.player.play_track(1)
        self.player.cycle_repeat()
        self.player.cycle_repeat()

        self.backend.finished.emit()

        self.assertEqual(self.backend.loaded_paths, [self.tracks[0].path] * 2)
        self.assertEqual(self.backend.state, PlaybackState.PLAYING)

    def test_repeat_all_advances_and_wraps(self) -> None:
        self.player.play_track(3)
        self.player.cycle_repeat()

        self.backend.finished.emit()

        self.assertEqual(self.player.current_track, self.tracks[0])
        self.assertEqual(self.backend.state, PlaybackState.PLAYING)

    def test_player_queue_actions_change_next_track(self) -> None:
        self.player.set_queue_order([2, 3, 1])
        self.player.play_track(2)

        self.assertTrue(self.player.play_next(1))
        self.assertEqual(self.player.queue_track_ids, (2, 1, 3))
        self.assertTrue(self.player.add_to_queue(1))
        self.assertEqual(self.player.queue_track_ids, (2, 3, 1))

        self.player.next()

        self.assertEqual(self.player.current_track, self.tracks[2])

    def test_mute_preserves_volume_and_restores_saved_state(self) -> None:
        self.player.set_volume(0.42)
        self.player.toggle_mute()
        self.assertTrue(self.player.is_muted)
        self.assertEqual(self.player.volume, 0.42)
        self.assertEqual(self.backend.volume, 0.0)

        self.player.save_state()
        restored_backend = FakeAudioBackend()
        restored = PlayerService(
            restored_backend,
            self.library,
            PlaybackQueue(),
            FakeSettings(self.settings.values),
        )
        restored.restore_session()

        self.assertTrue(restored.is_muted)
        self.assertEqual(restored.volume, 0.42)
        self.assertEqual(restored_backend.volume, 0.0)


if __name__ == "__main__":
    unittest.main()