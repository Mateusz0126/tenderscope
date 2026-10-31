
from copy import deepcopy

import pytest

from tenderscope.transformations.silver import transform_notices


@pytest.fixture
def sample_notice():
    return {
        "publication-number": "123456-2026",
        "publication-date": "2026-10-30+01:00",
        "notice-title": {
            "pol": "Testowy przetarg",
            "eng": "Test tender",
        },
        "buyer-name": {
            "pol": ["Firma A", "Firma A"],
        },
        "classification-cpv": [
            "72267000",
            "72267000",
            "72262000",
        ],
        "notice-type": "can-standard",
        "links": {"xml": {"MUL": "https://example.com/test.xml"}},
    }


def test_transform_notice(sample_notice):
    notices, cpvs, buyers = transform_notices([sample_notice])

    assert len(notices) == 1
    assert len(cpvs) == 2
    assert len(buyers) == 1

    assert notices[0]["notice_id"] == "123456-2026"
    assert notices[0]["publication_date"].isoformat() == "2026-10-30"
    assert notices[0]["title_pl"] == "Testowy przetarg"


def test_duplicate_notice_rejected(sample_notice):
    duplicate = deepcopy(sample_notice)

    with pytest.raises(ValueError, match="Duplicate notice"):
        transform_notices([sample_notice, duplicate])


def test_invalid_publication_date_rejected(sample_notice):
    sample_notice["publication-date"] = None

    with pytest.raises(TypeError, match="Invalid publication date type"):
        transform_notices([sample_notice])


def test_cpv_deduplication(sample_notice):
    _, cpvs, _ = transform_notices([sample_notice])

    codes = {row["cpv_code"] for row in cpvs}

    assert codes == {"72267000", "72262000"}
    assert len(cpvs) == len(codes)


def test_buyer_deduplication(sample_notice):
    _, _, buyers = transform_notices([sample_notice])

    assert buyers == [
        {
            "notice_id": "123456-2026",
            "buyer_name": "Firma A",
        }
    ]
