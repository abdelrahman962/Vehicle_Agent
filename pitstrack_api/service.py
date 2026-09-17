import os
import time
from typing import Any, Literal

import requests
from dotenv import load_dotenv


load_dotenv()


FilterOperator = Literal[
    "=",
    "!=",
    ">",
    ">=",
    "<",
    "<=",
    "like",
    "not like",
    "in",
    "not in",
]


def _get_field_value(row: dict[str, Any], field: str) -> Any:
    if "." not in field:
        return row.get(field)

    value: Any = row

    for part in field.split("."):
        if not isinstance(value, dict):
            return None

        value = value.get(part)

    return value


def _select_fields(
    rows: list[dict[str, Any]],
    fields: list[str] | None,
) -> list[dict[str, Any]]:
    if not fields:
        return rows

    return [
        {field: _get_field_value(row, field) for field in fields}
        for row in rows
    ]


def _extract_vehicles(response: Any) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        return []

    result = response.get("result")

    if isinstance(result, dict):
        data = result.get("data")

        if isinstance(data, list):
            return data

    data = response.get("data")

    if isinstance(data, list):
        return data

    return []


def _loose_equals(actual: Any, expected: Any) -> bool:
    if actual == expected:
        return True

    if isinstance(actual, bool):
        if isinstance(expected, str):
            lowered = expected.strip().lower()
            if lowered in {"true", "1"}:
                return actual is True
            if lowered in {"false", "0"}:
                return actual is False
        return actual == bool(expected)

    try:
        return float(actual) == float(expected)
    except (TypeError, ValueError):
        return False


def _matches(actual: Any, operator: str, expected: Any) -> bool:
    if actual is None:
        return False

    if operator in {"like", "not like"}:
        result = str(expected).lower() in str(actual).lower()
        return result if operator == "like" else not result

    if operator in {"in", "not in"}:
        expected_list = [v.strip() for v in str(expected).split(",")]
        result = any(_loose_equals(actual, v) for v in expected_list)
        return result if operator == "in" else not result

    if operator == "=":
        return _loose_equals(actual, expected)

    if operator == "!=":
        return not _loose_equals(actual, expected)

    try:
        actual_number = float(actual)
        expected_number = float(expected)
    except (TypeError, ValueError):
        return False

    if operator == ">":
        return actual_number > expected_number
    if operator == ">=":
        return actual_number >= expected_number
    if operator == "<":
        return actual_number < expected_number
    if operator == "<=":
        return actual_number <= expected_number

    return False


def _filter_rows(
    rows: list[dict[str, Any]],
    field: str | None,
    operator: str | None,
    value: Any,
) -> list[dict[str, Any]]:
    if not field:
        return rows

    operator = operator or "="

    return [row for row in rows if _matches(row.get(field), operator, value)]


def _has_numeric_value(rows: list[dict[str, Any]], field: str) -> bool:
    for row in rows:
        value = _get_field_value(row, field)

        if value is None:
            continue

        if isinstance(value, str) and value.strip() in {"", "-"}:
            continue

        try:
            float(value)
        except (TypeError, ValueError):
            continue

        return True

    return False


def _sort_rows(
    rows: list[dict[str, Any]],
    field: str | None,
    direction: str,
) -> list[dict[str, Any]]:
    if not field:
        return rows

    reverse = direction == "desc"

    numeric_rows: list[tuple[float, dict[str, Any]]] = []
    other_rows: list[tuple[str, dict[str, Any]]] = []

    for row in rows:
        value = row.get(field)

        if isinstance(value, str) and value.strip() in {"", "-"}:
            value = None

        if value is None:
            other_rows.append(("", row))
            continue

        try:
            numeric_rows.append((float(value), row))
        except (TypeError, ValueError):
            other_rows.append((str(value), row))

    # Rows with an actual usable value are ranked by that value and always
    # placed before rows missing the value, regardless of sort direction —
    # `reverse=True` must not be allowed to push missing values to the top.
    numeric_rows.sort(key=lambda item: item[0], reverse=reverse)
    other_rows.sort(key=lambda item: item[0], reverse=reverse)

    return [row for _, row in numeric_rows] + [row for _, row in other_rows]


CACHE_TTL_SECONDS = 90


class VehicleService:
    def __init__(self):
        api_url = os.getenv("PITSTRACK_API_URL")
        token = os.getenv("PITSTRACK_TOKEN")
        account = os.getenv("PITSTRACK_ACCOUNT")

        if not api_url:
            raise ValueError("PITSTRACK_API_URL is not configured.")

        if not token:
            raise ValueError("PITSTRACK_TOKEN is not configured.")

        if not account:
            raise ValueError("PITSTRACK_ACCOUNT is not configured.")

        self.api_url: str = api_url
        self.token: str = token
        self.account: str = account

        self._vehicles_cache: list[dict[str, Any]] | None = None
        self._vehicles_cached_at: float = 0.0

    def _fetch_vehicles(self) -> list[dict[str, Any]]:
        if (
            self._vehicles_cache is not None
            and time.monotonic() - self._vehicles_cached_at < CACHE_TTL_SECONDS
        ):
            return self._vehicles_cache

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "selected-account": self.account,
        }

        api_response = requests.get(
            self.api_url,
            headers=headers,
            timeout=30,
        )

        api_response.raise_for_status()

        rows = _extract_vehicles(api_response.json())

        self._vehicles_cache = rows
        self._vehicles_cached_at = time.monotonic()

        return rows

    def get_vehicles(
        self,
        filter_field: str | None = None,
        filter_operator: FilterOperator | None = None,
        filter_value: Any = None,
        sort_field: str | None = None,
        sort_direction: Literal["asc", "desc"] = "asc",
        limit: int | None = None,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        rows = self._fetch_vehicles()

        rows = _filter_rows(rows, filter_field, filter_operator, filter_value)
        count = len(rows)

        sort_field_has_data = (
            _has_numeric_value(rows, sort_field) if sort_field else None
        )

        rows = _sort_rows(rows, sort_field, sort_direction)

        if limit is None:
            limit = 10
        else:
            limit = max(1, min(limit, 50))

        rows = rows[:limit]

        rows = _select_fields(rows, fields)

        result: dict[str, Any] = {
            "count": count,
            "records": rows,
        }

        if sort_field_has_data is False:
            result["sort_field_unavailable"] = (
                f"'{sort_field}' has no usable value for any matching "
                "vehicle, so this order is not meaningful."
            )

        return result

    def count_by_field(
        self,
        field: str,
        filter_field: str | None = None,
        filter_operator: FilterOperator | None = None,
        filter_value: Any = None,
    ) -> dict[str, Any]:
        rows = self._fetch_vehicles()

        rows = _filter_rows(rows, filter_field, filter_operator, filter_value)

        groups: dict[str, int] = {}

        for row in rows:
            value = _get_field_value(row, field)

            if value is None or value == "":
                key = "(unavailable)"
            else:
                key = str(value)

            groups[key] = groups.get(key, 0) + 1

        return {
            "field": field,
            "total": len(rows),
            "groups": groups,
        }

    def group_vehicles_by_field(
        self,
        field: str,
        fields: list[str] | None = None,
        limit_per_group: int | None = None,
        filter_field: str | None = None,
        filter_operator: FilterOperator | None = None,
        filter_value: Any = None,
    ) -> dict[str, Any]:
        rows = self._fetch_vehicles()

        rows = _filter_rows(rows, filter_field, filter_operator, filter_value)

        groups: dict[str, list[dict[str, Any]]] = {}

        for row in rows:
            value = _get_field_value(row, field)
            key = "(unavailable)" if value is None or value == "" else str(value)
            groups.setdefault(key, []).append(row)

        result_groups: dict[str, dict[str, Any]] = {}

        for key, group_rows in groups.items():
            total = len(group_rows)

            if limit_per_group is not None:
                group_rows = group_rows[: max(1, limit_per_group)]

            result_groups[key] = {
                "total": total,
                "vehicles": _select_fields(group_rows, fields),
            }

        return {
            "field": field,
            "total": len(rows),
            "groups": result_groups,
        }
