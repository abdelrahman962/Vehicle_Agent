from typing import Any, Literal

from fastapi import FastAPI, Query

from pitstrack_api.service import VehicleService


app = FastAPI(title="Pitstrack Vehicle API")

vehicle_service = VehicleService()


FilterOperator = Literal[
    "=", "!=", ">", ">=", "<", "<=", "like", "not like", "in", "not in"
]


@app.get("/vehicles")
def get_vehicles(
    filter_field: str | None = None,
    filter_operator: FilterOperator | None = None,
    filter_value: str | None = None,
    sort_field: str | None = None,
    sort_direction: Literal["asc", "desc"] = "asc",
    limit: int | None = Query(default=None, gt=0),
    fields: list[str] | None = Query(default=None),
) -> dict[str, Any]:
    return vehicle_service.get_vehicles(
        filter_field=filter_field,
        filter_operator=filter_operator,
        filter_value=filter_value,
        sort_field=sort_field,
        sort_direction=sort_direction,
        limit=limit,
        fields=fields,
    )


@app.get("/vehicles/count-by")
def get_vehicles_count_by(
    field: str,
    filter_field: str | None = None,
    filter_operator: FilterOperator | None = None,
    filter_value: str | None = None,
) -> dict[str, Any]:
    return vehicle_service.count_by_field(
        field=field,
        filter_field=filter_field,
        filter_operator=filter_operator,
        filter_value=filter_value,
    )


@app.get("/vehicles/group-by")
def get_vehicles_group_by(
    field: str,
    fields: list[str] | None = Query(default=None),
    limit_per_group: int | None = Query(default=None, gt=0),
    filter_field: str | None = None,
    filter_operator: FilterOperator | None = None,
    filter_value: str | None = None,
) -> dict[str, Any]:
    return vehicle_service.group_vehicles_by_field(
        field=field,
        fields=fields,
        limit_per_group=limit_per_group,
        filter_field=filter_field,
        filter_operator=filter_operator,
        filter_value=filter_value,
    )
