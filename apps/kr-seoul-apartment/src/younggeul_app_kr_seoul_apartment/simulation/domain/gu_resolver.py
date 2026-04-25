"""Utilities for resolving Seoul district identifiers from user hints."""

from __future__ import annotations

from younggeul_app_kr_seoul_apartment.canonical import SEOUL_GU_CODE_TO_NAME, SEOUL_GU_NAME_TO_CODE


def resolve_gu_codes(
    geography_hint: str | None,
    available_gu_codes: list[str],
) -> tuple[list[str], list[str]]:
    """Resolve target district codes from a free-form geography hint.

    Args:
        geography_hint: Free-form district hint from the user query.
        available_gu_codes: District codes available in snapshot coverage.

    Returns:
        A tuple of resolved district codes and warning messages.
    """
    if geography_hint is None:
        return list(available_gu_codes), []

    hint = geography_hint.strip()
    if not hint:
        return list(available_gu_codes), ["Geography hint was empty; using all available districts."]

    warnings: list[str] = []
    available_set = set(available_gu_codes)

    if hint in SEOUL_GU_CODE_TO_NAME:
        if hint in available_set:
            return [hint], warnings
        return list(available_gu_codes), [f"Requested gu code '{hint}' is unavailable in snapshot coverage."]

    direct_code = SEOUL_GU_NAME_TO_CODE.get(hint)
    if direct_code is not None:
        if direct_code in available_set:
            return [direct_code], warnings
        return list(available_gu_codes), [f"Requested district '{hint}' is unavailable in snapshot coverage."]

    matched_codes = [
        code
        for code in available_gu_codes
        if SEOUL_GU_CODE_TO_NAME.get(code) is not None and SEOUL_GU_CODE_TO_NAME[code] in hint
    ]
    if matched_codes:
        return matched_codes, warnings

    warnings.append(f"Could not resolve geography hint '{geography_hint}'; using all available districts.")
    return list(available_gu_codes), warnings
