"""search 리포트 → 앱 DB 행 변환 검증."""

from services.profile_repository import (
    has_complete_scores,
    profile_row_from_search_csv,
    profile_row_from_search_profile,
)


def _csv_row(**overrides):
    row = {
        "restaurant_name": "우래옥",
        "meat_aroma_score": "5",
        "umami_score": "4",
        "buckwheat_aroma_score": "2",
        "acidity_score": "1",
        "review_status": "pending",
        "legacy_category": "우래옥",
        "special_note": "육향이 또렷하다",
        "profile_version": "phase2-v1",
    }
    row.update(overrides)
    return row


def test_legacy_category_maps_to_type_key():
    pairs = {
        "우래옥": "uraeok",
        "의정부": "uijeongbu",
        "장충동": "jangchungdong",
        "동치미": "dongchimi",
    }
    for legacy, expected in pairs.items():
        assert profile_row_from_search_csv(_csv_row(legacy_category=legacy))["type_key"] == expected


def test_unknown_legacy_category_becomes_none():
    assert profile_row_from_search_csv(_csv_row(legacy_category="평양"))["type_key"] is None
    assert profile_row_from_search_csv(_csv_row(legacy_category=""))["type_key"] is None


def test_address_and_map_url_are_taken_from_availability():
    row = profile_row_from_search_csv(
        _csv_row(),
        availability={
            "operating_status": "open",
            "address": "서울 중구 창경궁로 62-29",
            "map_url": "https://map.naver.com/p/entry/place/11665",
        },
    )

    assert row["operating_status"] == "open"
    assert row["address"] == "서울 중구 창경궁로 62-29"
    assert row["map_url"] == "https://map.naver.com/p/entry/place/11665"


def test_blank_availability_fields_become_none():
    row = profile_row_from_search_csv(
        _csv_row(),
        availability={"operating_status": "", "address": "  ", "map_url": ""},
    )

    assert row["operating_status"] == "unknown"
    assert row["address"] is None
    assert row["map_url"] is None


def test_missing_scores_are_detected():
    assert has_complete_scores(profile_row_from_search_csv(_csv_row()))
    assert not has_complete_scores(profile_row_from_search_csv(_csv_row(acidity_score="")))
    assert not has_complete_scores(profile_row_from_search_csv(_csv_row(umami_score="N/A")))


def test_needs_more_evidence_becomes_low_confidence():
    assert profile_row_from_search_csv(_csv_row(review_status="needs_more_evidence"))["profile_confidence"] == "low"
    assert profile_row_from_search_csv(_csv_row(review_status="pending"))["profile_confidence"] == "medium"


def test_json_profile_carries_type_key():
    row = profile_row_from_search_profile(
        {
            "restaurant_name": "장충동평양면옥",
            "legacy_category": "장충동",
            "traits": {
                "meat_aroma": {"score": 1},
                "umami": {"score": 1},
                "buckwheat_aroma": {"score": 5},
                "acidity": {"score": 1},
            },
        }
    )

    assert row["type_key"] == "jangchungdong"
    assert has_complete_scores(row)
