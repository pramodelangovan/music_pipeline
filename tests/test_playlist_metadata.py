import os

from scripts.playlist_utils import build_ytdlp_download_command, build_tag_map


def test_build_ytdlp_download_command_uses_max_quality_settings():
    cmd = build_ytdlp_download_command(
        playlist_url="https://www.youtube.com/playlist?list=PL123",
        output_dir="/tmp/playlist_downloads",
        cookies_path="/tmp/cookies.txt",
        album_name="Album Name",
        artist_name="Artist Name",
    )
    assert cmd[0] == "yt-dlp"
    assert "-x" in cmd
    assert "--audio-format" in cmd
    assert cmd[cmd.index("--audio-format") + 1] == "mp3"
    assert "--audio-quality" in cmd
    assert cmd[cmd.index("--audio-quality") + 1] == "0"
    assert "--embed-thumbnail" in cmd
    assert "--cookies" in cmd
    assert cmd[cmd.index("--cookies") + 1] == "/tmp/cookies.txt"


def test_build_tag_map_includes_album_artist_and_cover_hint():
    tags = build_tag_map(
        title="Song Title",
        artist="Artist Name",
        album="Album Name",
        track_number=3,
        cover_path="/tmp/cover.jpg",
    )
    assert tags["title"] == "Song Title"
    assert tags["artist"] == "Artist Name"
    assert tags["album"] == "Album Name"
    assert tags["track_number"] == 3
    assert tags["cover_path"] == "/tmp/cover.jpg"
