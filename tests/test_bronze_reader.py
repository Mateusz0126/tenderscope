
import json

import pytest

from tenderscope.transformations.bronze_reader import (
    load_bronze_run,
)


def test_load_bronze_pages(tmp_path):
    run_dir = tmp_path / "test_run"
    run_dir.mkdir()

    manifest = {
        "status": "partial",
        "pages": [
            {"file": "page_001.json", "record_count": 2},
            {"file": "page_002.json", "record_count": 1},
        ],
    }

    (run_dir / "manifest.json").write_text(
        json.dumps(manifest)
    )

    for number, ids in [
        (1, ["001-2026", "002-2026"]),
        (2, ["003-2026"]),
    ]:
        data = {
            "notices": [
                {"publication-number": notice_id}
                for notice_id in ids
            ],
            "timedOut": False,
        }

        (run_dir / f"page_{number:03d}.json").write_text(
            json.dumps(data)
        )

    with pytest.raises(ValueError, match="partial"):
        load_bronze_run(run_dir)

    notices = load_bronze_run(
        run_dir,
        allow_partial=True,
    )

    assert len(notices) == 3

    assert [
        n["publication-number"] for n in notices
    ] == ["001-2026", "002-2026", "003-2026"]
