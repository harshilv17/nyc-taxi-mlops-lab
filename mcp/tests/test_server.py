"""predict_duration and query_zone_stats, with serving and the warehouse faked (S7)."""

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError

import labmcp.server as s


async def test_predict_duration_sends_features_yaml_encodings(monkeypatch):
    seen = []

    async def champion(method, path, body=None):
        seen.append((method, path, body))
        return {"duration_minutes": 31.5, "model": {"name": "trip-duration", "version": "2", "alias": "champion"}}

    monkeypatch.setattr(s, "champion", champion)
    out = json.loads((await s.mcp.call_tool("predict_duration", {"pickup_zone": "JFK Airport", "dropoff_zone": "Times Sq/Theatre District",
                                                                 "hour": 17, "day_of_week": "friday"}))[0].text)
    assert seen == [("POST", "/predict", {"pickup_zone_id": 132, "dropoff_zone_id": 230, "pickup_hour": 17, "pickup_dow": 5})]
    assert out["duration_minutes"] == 31.5 and out["model"]["alias"] == "champion"


async def test_predict_duration_unknown_zone_is_an_error_with_suggestions():
    with pytest.raises(ToolError, match="did you mean 'jfk airport'"):
        await s.mcp.call_tool("predict_duration", {"pickup_zone": "JFK Airprot", "dropoff_zone": "JFK Airport", "hour": 1, "day_of_week": "monday"})


class FakeWarehouse:
    calls: list = []

    def query(self, sql, params=None, timeout_s=30):
        FakeWarehouse.calls.append((sql, params))
        return [{"pickup_hour": "17", "value": "812.0", "first_month": "2024-01", "last_month": "2024-04"}]


async def test_query_zone_stats_uses_named_parameters_only(monkeypatch):
    FakeWarehouse.calls = []
    monkeypatch.setattr(s, "Warehouse", FakeWarehouse)
    out = json.loads((await s.mcp.call_tool("query_zone_stats", {"zone": "JFK Airport", "metric": "trip_count", "hour": 17}))[0].text)
    sql, params = FakeWarehouse.calls[0]
    assert params == {"zid": 132, "hour": 17} and ":zid" in sql and ":hour" in sql
    assert "JFK" not in sql and "132" not in sql  # nothing from the call is formatted into the SQL
    assert out["rows"] == [{"hour": 17, "value": 812}] and out["months"] == "2024-01..2024-04"


async def test_query_zone_stats_rejects_a_metric_outside_the_list_and_sql_in_the_zone(monkeypatch):
    monkeypatch.setattr(s, "Warehouse", FakeWarehouse)
    FakeWarehouse.calls = []
    for args in ({"zone": "JFK Airport", "metric": "trip_count; drop table marts.zone_hour_stats"},
                 {"zone": "JFK Airport'; drop table marts.zone_hour_stats; --", "metric": "trip_count"}):
        with pytest.raises(ToolError):
            await s.mcp.call_tool("query_zone_stats", args)
    assert FakeWarehouse.calls == []
