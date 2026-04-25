from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

_SEOUL_GU_ITEMS: tuple[tuple[str, str], ...] = (
    ("11110", "종로구"),
    ("11140", "중구"),
    ("11170", "용산구"),
    ("11200", "성동구"),
    ("11215", "광진구"),
    ("11230", "동대문구"),
    ("11260", "중랑구"),
    ("11290", "성북구"),
    ("11305", "강북구"),
    ("11320", "도봉구"),
    ("11350", "노원구"),
    ("11380", "은평구"),
    ("11410", "서대문구"),
    ("11440", "마포구"),
    ("11470", "양천구"),
    ("11500", "강서구"),
    ("11530", "구로구"),
    ("11545", "금천구"),
    ("11560", "영등포구"),
    ("11590", "동작구"),
    ("11620", "관악구"),
    ("11650", "서초구"),
    ("11680", "강남구"),
    ("11710", "송파구"),
    ("11740", "강동구"),
)

SEOUL_GU_CODES: tuple[str, ...] = tuple(code for code, _ in _SEOUL_GU_ITEMS)
SEOUL_GU_CODE_TO_NAME: Mapping[str, str] = MappingProxyType(dict(_SEOUL_GU_ITEMS))
SEOUL_GU_NAME_TO_CODE: Mapping[str, str] = MappingProxyType({name: code for code, name in _SEOUL_GU_ITEMS})

__all__ = ["SEOUL_GU_CODES", "SEOUL_GU_CODE_TO_NAME", "SEOUL_GU_NAME_TO_CODE"]
