from datetime import UTC, datetime

from db_table_functions.db_tbl_da_requests import create_request, get_request, list_requests

OCT_2026 = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)


def test_first_request_of_the_year_gets_number_0001(db_path):
    request = create_request(db_path, "Change A", "dev-0001", now=OCT_2026)

    assert request.request_id == "CVDA-2026-0001"
    assert request.status == "NEW"


def test_request_numbers_go_up_by_one(db_path):
    create_request(db_path, "Change A", "dev-0001", now=OCT_2026)
    second = create_request(db_path, "Change B", "dev-0002", now=OCT_2026)

    assert second.request_id == "CVDA-2026-0002"


def test_new_year_restarts_at_0001(db_path):
    create_request(db_path, "Change A", "dev-0001", now=OCT_2026)
    next_year = create_request(
        db_path, "Change B", "dev-0001", now=datetime(2027, 3, 1, tzinfo=UTC)
    )

    assert next_year.request_id == "CVDA-2027-0001"


def test_id_year_uses_singapore_time(db_path):
    # 17:00 UTC on 31 Dec is already 01:00 on 1 Jan in Singapore (UTC+8).
    late_new_years_eve_utc = datetime(2026, 12, 31, 17, 0, tzinfo=UTC)

    request = create_request(db_path, "Change A", "dev-0001", now=late_new_years_eve_utc)

    assert request.request_id == "CVDA-2027-0001"
    # The stored time itself stays in UTC.
    assert request.created_at == late_new_years_eve_utc


def test_just_before_singapore_midnight_stays_in_old_year(db_path):
    # 15:59 UTC on 31 Dec is 23:59 in Singapore, still 2026.
    request = create_request(
        db_path, "Change A", "dev-0001", now=datetime(2026, 12, 31, 15, 59, tzinfo=UTC)
    )

    assert request.request_id == "CVDA-2026-0001"


def test_get_request_returns_what_was_saved(db_path):
    saved = create_request(db_path, "Change A", "dev-0001", now=OCT_2026)

    loaded = get_request(db_path, saved.request_id)

    assert loaded == saved


def test_get_unknown_request_returns_none(db_path):
    assert get_request(db_path, "CVDA-2026-9999") is None


def test_list_requests_returns_all_oldest_first(db_path):
    create_request(db_path, "Change A", "dev-0001", now=OCT_2026)
    create_request(db_path, "Change B", "dev-0002", now=datetime(2026, 10, 26, tzinfo=UTC))

    titles = [request.title for request in list_requests(db_path)]

    assert titles == ["Change A", "Change B"]


def test_list_requests_on_empty_database_is_empty(db_path):
    assert list_requests(db_path) == []


def test_missing_data_folder_is_created(tmp_path):
    db_path = tmp_path / "new_folder" / "devassist.db"

    create_request(db_path, "Change A", "dev-0001", now=OCT_2026)

    assert db_path.exists()
