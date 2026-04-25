from __future__ import annotations

from types import MappingProxyType

from younggeul_app_kr_seoul_apartment.canonical.regions import (
    SEOUL_GU_CODES,
    SEOUL_GU_CODE_TO_NAME,
    SEOUL_GU_NAME_TO_CODE,
)


def test_seoul_gu_codes_are_complete_and_sorted() -> None:
    assert SEOUL_GU_CODES == (
        "11110",
        "11140",
        "11170",
        "11200",
        "11215",
        "11230",
        "11260",
        "11290",
        "11305",
        "11320",
        "11350",
        "11380",
        "11410",
        "11440",
        "11470",
        "11500",
        "11530",
        "11545",
        "11560",
        "11590",
        "11620",
        "11650",
        "11680",
        "11710",
        "11740",
    )
    assert len(SEOUL_GU_CODES) == 25
    assert tuple(sorted(SEOUL_GU_CODES)) == SEOUL_GU_CODES
    assert len(set(SEOUL_GU_CODES)) == 25
    assert all(code.startswith("11") for code in SEOUL_GU_CODES)


def test_region_maps_are_frozen_and_bidirectional() -> None:
    assert isinstance(SEOUL_GU_CODE_TO_NAME, MappingProxyType)
    assert isinstance(SEOUL_GU_NAME_TO_CODE, MappingProxyType)
    assert tuple(SEOUL_GU_CODE_TO_NAME) == SEOUL_GU_CODES
    assert set(SEOUL_GU_CODE_TO_NAME) == set(SEOUL_GU_CODES)
    assert set(SEOUL_GU_NAME_TO_CODE.values()) == set(SEOUL_GU_CODES)
    assert SEOUL_GU_CODE_TO_NAME["11680"] == "강남구"
    assert SEOUL_GU_NAME_TO_CODE["강남구"] == "11680"
    assert SEOUL_GU_NAME_TO_CODE[SEOUL_GU_CODE_TO_NAME["11440"]] == "11440"
