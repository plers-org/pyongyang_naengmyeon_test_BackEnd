"""search restaurant_places.csv → 프로필 테이블 UPDATE 파라미터 변환 검증."""

from services.profile_repository import (
    fill_incomplete_scores,
    has_complete_scores,
    place_row_from_search_csv,
    select_place_targets,
)


def _place_row(**overrides):
    row = {
        "restaurant_name": "우래옥",
        "place_url": "https://map.naver.com/p/entry/place/11679381",
        "place_id": "11679381",
        "matched_name": "우래옥",
        "category": "냉면",
        "road_address": "서울 중구 창경궁로 62-29",
        "phone": "02-2265-0151",
        "latitude": "37.5681693",
        "longitude": "126.9987278",
        "match_status": "matched",
        "match_score": "1.0",
    }
    row.update(overrides)
    return row


def test_maps_csv_columns_to_update_parameters():
    row = place_row_from_search_csv(_place_row())

    assert row["restaurant_name"] == "우래옥"
    assert row["map_url"] == "https://map.naver.com/p/entry/place/11679381"
    assert row["address"] == "서울 중구 창경궁로 62-29"


def test_coordinates_become_floats():
    row = place_row_from_search_csv(_place_row())

    assert row["latitude"] == 37.5681693
    assert row["longitude"] == 126.9987278


def test_blank_values_become_none_so_existing_values_survive():
    row = place_row_from_search_csv(
        _place_row(road_address="", place_url="", latitude="", longitude="")
    )

    assert row["address"] is None
    assert row["map_url"] is None
    assert row["latitude"] is None
    assert row["longitude"] is None


def test_non_numeric_coordinate_is_dropped():
    assert place_row_from_search_csv(_place_row(latitude="없음"))["latitude"] is None


# --- 적재 대상 고르기 ---------------------------------------------------


def _places():
    return [
        _place_row(restaurant_name="우래옥", match_status="matched"),
        _place_row(restaurant_name="강서면옥", match_status="review"),
        _place_row(restaurant_name="만포면옥(구산동 본점)", match_status="manual"),
        _place_row(restaurant_name="없는집", match_status="failed"),
    ]


def test_manual_rows_are_always_imported():
    """사람이 place_overrides.csv로 고친 행이 버려지면 안 된다."""
    targets, skipped = select_place_targets(_places())

    assert [row["restaurant_name"] for row in targets] == ["우래옥", "만포면옥(구산동 본점)"]
    assert "만포면옥(구산동 본점)" not in skipped


def test_review_rows_wait_for_a_human():
    _, skipped = select_place_targets(_places())

    assert "강서면옥" in skipped


def test_include_review_adds_them_without_dropping_manual():
    targets, skipped = select_place_targets(_places(), include_review=True)

    assert [row["restaurant_name"] for row in targets] == [
        "우래옥",
        "강서면옥",
        "만포면옥(구산동 본점)",
    ]
    assert skipped == ["없는집"]


# --- 임시 점수로 강제 적재 -----------------------------------------------


def _profile_row(**overrides):
    row = {
        "restaurant_name": "서관면옥(삼성점)",
        "meat_aroma_score": 5.0,
        "umami_score": 2.0,
        "buckwheat_aroma_score": 5.0,
        "acidity_score": None,
        "profile_confidence": "low",
        "profile_version": "phase2-v1",
    }
    row.update(overrides)
    return row


def test_missing_axis_is_filled_and_reported():
    filled, missing = fill_incomplete_scores(_profile_row())

    assert missing == ["acidity_score"]
    assert filled["acidity_score"] == 3.0
    assert has_complete_scores(filled)


def test_filled_profile_stays_low_so_it_never_reaches_recommendations():
    filled, _ = fill_incomplete_scores(_profile_row(profile_confidence="medium"))

    assert filled["profile_confidence"] == "low"


def test_provisional_rows_are_marked_in_version():
    filled, _ = fill_incomplete_scores(_profile_row())

    assert filled["profile_version"] == "phase2-v1+provisional"


def test_suffix_is_not_doubled_on_rerun():
    once, _ = fill_incomplete_scores(_profile_row())
    twice, _ = fill_incomplete_scores(once)

    assert twice["profile_version"] == "phase2-v1+provisional"


def test_complete_profile_is_untouched():
    filled, missing = fill_incomplete_scores(_profile_row(acidity_score=2.0, profile_confidence="medium"))

    assert missing == []
    assert filled["profile_confidence"] == "medium"
    assert filled["profile_version"] == "phase2-v1"
