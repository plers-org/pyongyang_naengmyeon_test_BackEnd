"""search restaurant_places.csv → 프로필 테이블 UPDATE 파라미터 변환 검증."""

from services.profile_repository import place_row_from_search_csv


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
