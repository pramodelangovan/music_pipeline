from scripts.metadata_enricher import resolve_track_metadata


def test_resolve_track_metadata_falls_back_to_hints():
    meta = resolve_track_metadata(
        title="Ala Bolelo",
        artist_hint="Artist Name",
        album_hint="Album Name",
        api_response={}
    )
    assert meta["title"] == "Ala Bolelo"
    assert meta["artist"] == "Artist Name"
    assert meta["album"] == "Album Name"


def test_resolve_track_metadata_uses_api_artist_and_album_when_available():
    meta = resolve_track_metadata(
        title="Some Song",
        artist_hint="Fallback Artist",
        album_hint="Fallback Album",
        api_response={
            "artist": "Real Artist",
            "album": "Real Album",
            "title": "Some Song",
        },
    )
    assert meta["artist"] == "Real Artist"
    assert meta["album"] == "Real Album"
