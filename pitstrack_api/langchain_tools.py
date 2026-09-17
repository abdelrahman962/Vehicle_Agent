from typing import Any, Literal

import requests
from langchain.tools import tool


API_BASE_URL = "http://127.0.0.1:8000"

FilterOperator = Literal[
    "=", "!=", ">", ">=", "<", "<=", "like", "not like", "in", "not in"
]


@tool
def get_vehicles(
    filter_field: str | None = None,
    filter_operator: FilterOperator | None = None,
    filter_value: str | None = None,
    sort_field: str | None = None,
    sort_direction: Literal["asc", "desc"] = "asc",
    limit: int | None = None,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """
    Read current vehicle and fleet information from Pitstrack.

    Use this tool for factual vehicle questions including:
    - listing vehicles
    - vehicle speed
    - odometer
    - vehicle status
    - driver
    - device information
    - location
    - counting vehicles
    - filtering vehicles
    - sorting vehicles

    Common fields:
    id
    name
    odometer
    speed
    vehicle_status
    driver_name
    device_number
    longitude
    latitude
    fuel_type              (e.g. "petrol_95", "diesel", "petrol_98")
    gear_type              (e.g. "automatic", "Regular")
    vehicle_type           (e.g. "four wheel car", "salon car", "Truck-Ramp")
    icon                   (e.g. "car", "truck", "van", "person")
    oil_consumption        (number)
    tank_capacity          (number)
    is_license_expired     (boolean: true/false)
    is_insurance_expired   (boolean: true/false)
    license_expiry_at      (date string, or missing if none)
    jawwal_requirements    (0 or 1)
    rental_price           (present only for rented vehicles)
    rental_supplier        (present only for rented vehicles)
    insurance_supplier     (present only if insured)
    manufacturer           (e.g. "Volkswagen", "IVECO", "Kia")
    color_export           (human-readable color name, e.g. "White",
                            "Gray", "Blue" -- use this for color
                            questions, NOT `color`, which is a hex
                            code like "#FFFFFF" and will never match a
                            color name)

    Never invent a field name that is not in this list or in a tool
    result you have actually seen. If the user's wording doesn't match
    any known field (e.g. "which vehicles are rented" -> rental_price
    is not null, NOT a guessed field like "is_rented"), pick the
    closest real field above rather than making one up.

    For a "does X have a driver / is X assigned" question, use:

        filter_field="driver_name"
        filter_operator="!="
        filter_value=""

    (an empty driver_name means no driver assigned).

    IMPORTANT: Always pass `fields` with only the fields needed to
    answer the question (plus "id" and "name" for context). Vehicle
    records contain many large, irrelevant nested objects (management,
    circle, suppliers, contract, etc.) that are expensive to read and
    unrelated to most questions. Only omit `fields` if the user
    explicitly asks for the full record.

    For "give me N vehicles with their details" (a LIST, even though it
    says "details"), use THIS tool with limit=N and omit `fields` to
    get full records — do not call get_vehicle_details with a guessed
    vehicle_id.

    Example, for "what is the odometer of vehicle 24?":

        filter_field="id"
        filter_operator="="
        filter_value=24
        fields=["id", "name", "odometer"]

    For filtering, use the separate parameters:

        filter_field
        filter_operator
        filter_value

    Example:

        filter_field="speed"
        filter_operator=">"
        filter_value=50

    `filter_operator` also supports "in" and "not in" for matching
    multiple values. Pass `filter_value` as a comma-separated string:

        filter_field="id"
        filter_operator="in"
        filter_value="24,25,27,32,33"

    For "give me another N vehicles" / "show me more" / "next N", do
    NOT repeat the same call (it returns identical vehicles, since
    there is no randomness or pagination). Instead use
    filter_field="id", filter_operator="not in", and filter_value set
    to the ids of every vehicle already shown so far in this
    conversation, to exclude them from this new batch.

    Never set `filter_value` to a pronoun or reference word such as
    "their", "them", "those", or "it" — these refer to vehicles
    already shown earlier in the conversation, not a literal value to
    search for. For a question like "their names", answer from the
    records already returned by the most recent call to this tool
    instead of calling it again.

    If the follow-up needs a NEW call restricted to those same
    previously-shown vehicles (e.g. "sort them by name"), use
    filter_field="id", filter_operator="in", and filter_value set to
    the comma-separated ids of exactly those vehicles (from the most
    recent tool result) — never a fresh unrestricted query.

    Never invent vehicle information.

    IMPORTANT: If the question names ONE specific value to match (e.g.
    "show me vehicles with color white", "list diesel vehicles", "which
    vehicles have an expired license"), use THIS tool with a filter —
    do NOT use get_vehicles_grouped_by_field for this. That tool is
    only for when the user wants EVERY value of a field compared side
    by side (e.g. "group vehicles by color", "break down vehicles by
    fuel type").

    Example, for "show me vehicles with color white":

        filter_field="color_export"
        filter_operator="="
        filter_value="White"
    """

    params: dict[str, Any] = {
        "filter_field": filter_field,
        "filter_operator": filter_operator,
        "filter_value": filter_value,
        "sort_field": sort_field,
        "sort_direction": sort_direction,
        "limit": limit,
        "fields": fields,
    }

    params = {
        key: value
        for key, value in params.items()
        if value is not None
    }

    response = requests.get(
        f"{API_BASE_URL}/vehicles",
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


@tool
def get_vehicles_grouped_by_field(
    field: str,
    fields: list[str] | None = None,
    limit_per_group: int | None = None,
    filter_field: str | None = None,
    filter_operator: FilterOperator | None = None,
    filter_value: str | None = None,
) -> dict[str, Any]:
    """
    List vehicles GROUPED BY a field's value, with their details.

    Use this when the user wants to see the actual vehicles that share
    a feature/attribute, not just a count. For example:

    - "show me all vehicles grouped by fuel type"
    - "break down vehicles by vehicle_status"
    - "which vehicles share the same driver?"

    Do NOT use this tool when the question names ONE specific value to
    match, such as "show me vehicles with color white", "list diesel
    vehicles", or "vehicles that are automatic" — those are single-value
    filters, so use get_vehicles instead with filter_field/filter_operator
    /filter_value. Only use this tool when the user wants to see EVERY
    value of the field compared side by side, not just one value's
    vehicles.

    Pass `field` as the attribute to group by, e.g. "fuel_type",
    "vehicle_status", "driver_name", "gear_type".

    Always pass `fields` with only the fields needed (e.g. ["id",
    "name", "fuel_type"]) — vehicle records contain many large,
    irrelevant nested objects. Only omit `fields` if the user
    explicitly asks for full details.

    Use `limit_per_group` (e.g. 5) to cap how many vehicles are shown
    per group when there could be many, unless the user asks to see
    all of them.

    The result is `{"field": ..., "total": ..., "groups": {value:
    {"total": N, "vehicles": [...]}}}`. `total` inside a group is the
    real count even if `vehicles` was capped by `limit_per_group`. A
    group key of "(unavailable)" means that value was missing for
    those vehicles.

    Optionally narrow to a subset first with filter_field /
    filter_operator / filter_value. Only pass those if the user's
    question states a condition.

    See get_vehicles' docstring for the full list of real field names
    — never invent a field name not in that list.
    """

    params: dict[str, Any] = {
        "field": field,
        "fields": fields,
        "limit_per_group": limit_per_group,
        "filter_field": filter_field,
        "filter_operator": filter_operator,
        "filter_value": filter_value,
    }

    params = {
        key: value
        for key, value in params.items()
        if value is not None
    }

    response = requests.get(
        f"{API_BASE_URL}/vehicles/group-by",
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


@tool
def get_vehicles_count(
    filter_field: str | None = None,
    filter_operator: FilterOperator | None = None,
    filter_value: str | None = None,
) -> dict[str, Any]:
    """
    Count vehicles from Pitstrack.

    Use this tool when the user asks how many vehicles there are.

    For "how many vehicles do I have?" or "total number of vehicles"
    (no stated condition), call this with NO arguments at all:

        get_vehicles_count()

    Do NOT add a filter unless the user's question states one. Never
    reuse a filter from a previous example or a previous question.

    To count only vehicles matching a condition the user actually
    stated, use:

        filter_field
        filter_operator
        filter_value

    Example, for "how many vehicles have speed greater than 50?":

        filter_field="speed"
        filter_operator=">"
        filter_value=50

    `filter_operator` also supports "in" / "not in" with a
    comma-separated `filter_value` (e.g. filter_value="24,25,27") to
    match multiple values at once.

    See get_vehicles' docstring for the full list of real field names
    (fuel_type, gear_type, icon, is_license_expired, jawwal_requirements,
    rental_price, etc.) — never invent a field name not in that list.
    """

    params: dict[str, Any] = {
        "filter_field": filter_field,
        "filter_operator": filter_operator,
        "filter_value": filter_value,
        "limit": 1,
        "fields": ["id"],
    }

    params = {
        key: value
        for key, value in params.items()
        if value is not None
    }

    response = requests.get(
        f"{API_BASE_URL}/vehicles",
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    return {"count": response.json().get("count", 0)}


@tool
def get_vehicle_details(
    vehicle_id: int | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """
    Get the FULL details of ONE specific vehicle, by id or by name.

    Use this when the user asks about a specific, single vehicle, for
    example "show me details for vehicle 24", "tell me about Ruptela
    test 501", "what is the status of vehicle 33?".

    Pass exactly one of:

        vehicle_id=24

    or:

        name="Ruptela test 501"

    Do not use this for lists of multiple vehicles — use get_vehicles
    for that, even if the user says "with their details" or "full
    details". For example, "give me the first 5 vehicles with their
    details" means get_vehicles(limit=5) (omit `fields` to get full
    records), NOT this tool with a guessed vehicle_id.

    This tool takes ONLY vehicle_id or name — never pass a `limit` or
    any other argument to it.
    """

    params: dict[str, Any]

    if vehicle_id is not None:
        params = {"filter_field": "id", "filter_operator": "=", "filter_value": vehicle_id}
    elif name is not None:
        params = {"filter_field": "name", "filter_operator": "=", "filter_value": name}
    else:
        return {"error": "Provide either vehicle_id or name."}

    params["limit"] = 1

    response = requests.get(
        f"{API_BASE_URL}/vehicles",
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    records = response.json().get("records", [])

    if not records:
        return {"found": False}

    return {"found": True, "vehicle": records[0]}


@tool
def get_vehicle_counts_by_field(
    field: str,
    filter_field: str | None = None,
    filter_operator: FilterOperator | None = None,
    filter_value: str | None = None,
) -> dict[str, Any]:
    """
    Count vehicles GROUPED BY a field's value.

    Use this when the user asks how many vehicles share the same
    value of some attribute, for example:

    - "how many vehicles are there per fuel type?"
    - "count of vehicles by status"
    - "how many vehicles does each driver have?"

    Pass `field` as the attribute to group by, e.g. "fuel_type",
    "vehicle_status", "driver_name", "gear_type".

    The result is `{"field": ..., "total": ..., "groups": {value:
    count, ...}}`. A group key of "(unavailable)" means that value was
    missing, null, or empty for those vehicles.

    Optionally narrow to a subset first with filter_field /
    filter_operator / filter_value, same as get_vehicles. Only pass
    those if the user's question states a condition.

    See get_vehicles' docstring for the full list of real field names
    — never invent a field name not in that list.
    """

    params: dict[str, Any] = {
        "field": field,
        "filter_field": filter_field,
        "filter_operator": filter_operator,
        "filter_value": filter_value,
    }

    params = {
        key: value
        for key, value in params.items()
        if value is not None
    }

    response = requests.get(
        f"{API_BASE_URL}/vehicles/count-by",
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()
