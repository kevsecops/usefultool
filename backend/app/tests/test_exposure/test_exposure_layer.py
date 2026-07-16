"""Exposure layer tests."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.analysis.exposure_analysis import (
    analyze_event_exposure,
    count_assets_in_geometry,
    count_assets_near_point,
    earthquake_radius_km,
)
from app.models.canonical_event import CanonicalEvent
from app.models.canonical_event_link import CanonicalEventLink
from app.models.exposure_asset import ExposureAsset
from app.models.observed_event import ObservedEvent
from app.normalization.geometry import geojson_to_wkt_element
from app.services.exposure_service import (
    calculate_exposure_for_event,
    import_exposure_fixtures,
    run_calculate_exposure,
)


def _now() -> datetime:
    return datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _seed_demo_assets(db_session) -> list[ExposureAsset]:
    result = import_exposure_fixtures(db_session)
    db_session.flush()
    assert result.total_assets >= 30
    return list(db_session.scalars(select(ExposureAsset)).all())


def test_import_exposure_fixtures(db_session) -> None:
    result = import_exposure_fixtures(db_session)
    assert result.total_assets >= 30
    assert (result.assets_created + result.assets_updated) >= 30

    second = import_exposure_fixtures(db_session)
    assert second.assets_created == 0
    assert second.assets_updated >= 30


def test_earthquake_point_distance_detection(db_session) -> None:
    _seed_demo_assets(db_session)
    now = _now()

    # M6.5 near Tokyo — should expose Tokyo port and Haneda airport
    observed = ObservedEvent(
        id=uuid4(),
        source="usgs",
        source_event_id="us7000tokyo",
        title="M6.5 Earthquake near Tokyo",
        category="earthquake",
        event_type="earthquake",
        severity="severe",
        status="automatic",
        confidence="high",
        latitude=35.5,
        longitude=139.7,
        geometry_json={"type": "Point", "coordinates": [139.7, 35.5]},
        geometry=geojson_to_wkt_element({"type": "Point", "coordinates": [139.7, 35.5]}),
        spatial_scope="local",
        issued_at=now,
        ingested_at=now,
        last_seen_at=now,
        raw_payload={"id": "us7000tokyo"},
        source_metadata={"magnitude": 6.5, "depth_km": 30},
        fingerprint="eq-tokyo-fp",
        is_active=True,
    )
    db_session.add(observed)
    db_session.flush()

    event = CanonicalEvent(
        id=uuid4(),
        event_type="earthquake",
        title="M6.5 Earthquake near Tokyo",
        status="active",
        severity="severe",
        geometry_json={"type": "Point", "coordinates": [139.7, 35.5]},
        geometry=geojson_to_wkt_element({"type": "Point", "coordinates": [139.7, 35.5]}),
        spatial_scope="local",
        started_at=now,
        updated_at=now,
        confidence="high",
        primary_source_id=observed.id,
        is_active=True,
    )
    db_session.add(event)
    db_session.add(
        CanonicalEventLink(
            canonical_event_id=event.id,
            member_type="observed_event",
            member_id=observed.id,
            link_confidence="high",
            link_reason="primary",
            created_at=now,
        )
    )
    db_session.flush()

    radius = earthquake_radius_km(6.5, 30, "severe")
    assert radius > 20

    candidates = analyze_event_exposure(db_session, event)
    assert len(candidates) >= 2

    asset_names = set()
    for candidate in candidates:
        asset = db_session.get(ExposureAsset, candidate.asset_id)
        assert asset is not None
        asset_names.add(asset.name)
        assert candidate.exposure_type in (
            "inside_event_area",
            "near_event_area",
        )

    assert any("Tokyo" in name or "Haneda" in name for name in asset_names)

    near_count = count_assets_near_point(db_session, 35.5, 139.7, radius + 50)
    assert near_count >= 2


def test_polygon_inside_detection(db_session) -> None:
    _seed_demo_assets(db_session)
    now = _now()

    # Storm polygon covering Netherlands — Amsterdam Schiphol + Rotterdam port
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [3.5, 51.0],
                [5.5, 51.0],
                [5.5, 52.5],
                [3.5, 52.5],
                [3.5, 51.0],
            ]
        ],
    }
    event = CanonicalEvent(
        id=uuid4(),
        event_type="storm",
        title="North Sea Storm Warning",
        status="active",
        severity="severe",
        geometry_json=polygon,
        geometry=geojson_to_wkt_element(polygon),
        spatial_scope="regional",
        started_at=now,
        updated_at=now,
        confidence="high",
        is_active=True,
    )
    db_session.add(event)
    db_session.flush()

    inside_count = count_assets_in_geometry(db_session, polygon)
    assert inside_count >= 2

    candidates = analyze_event_exposure(db_session, event)
    assert len(candidates) >= 2
    inside = [c for c in candidates if c.exposure_type == "inside_event_area"]
    assert len(inside) >= 2


def test_space_weather_system_level_exposure(db_session) -> None:
    _seed_demo_assets(db_session)
    now = _now()

    observed = ObservedEvent(
        id=uuid4(),
        source="noaa_swpc",
        source_event_id="swpc-g4-demo",
        title="G4 Geomagnetic Storm",
        category="environmental",
        event_type="geomagnetic_storm",
        severity="severe",
        status="actual",
        confidence="high",
        spatial_scope="global",
        affected_latitude_min=50.0,
        affected_latitude_max=90.0,
        issued_at=now,
        ingested_at=now,
        last_seen_at=now,
        raw_payload={"product_id": "K09A"},
        source_metadata={
            "potential_systems": ["power_grid", "satellite_operations"],
            "scale_type": "G",
            "scale_level": 4,
        },
        fingerprint="swpc-g4-fp",
        is_active=True,
    )
    db_session.add(observed)
    db_session.flush()

    event = CanonicalEvent(
        id=uuid4(),
        event_type="geomagnetic_storm",
        title="G4 Geomagnetic Storm",
        status="active",
        severity="severe",
        spatial_scope="global",
        started_at=now,
        updated_at=now,
        confidence="high",
        primary_source_id=observed.id,
        is_active=True,
    )
    db_session.add(event)
    db_session.add(
        CanonicalEventLink(
            canonical_event_id=event.id,
            member_type="observed_event",
            member_id=observed.id,
            link_confidence="high",
            link_reason="primary",
            created_at=now,
        )
    )
    db_session.flush()

    candidates = analyze_event_exposure(db_session, event)
    assert len(candidates) >= 3

    types = set()
    for candidate in candidates:
        assert candidate.exposure_type == "system_level_exposure"
        asset = db_session.get(ExposureAsset, candidate.asset_id)
        assert asset is not None
        types.add(asset.asset_type)
        if asset.latitude is not None:
            assert asset.latitude >= 50.0

    assert "power_plant" in types
    assert "airport" in types or "port" in types


def test_calculate_exposure_persists_records(db_session) -> None:
    _seed_demo_assets(db_session)
    now = _now()

    event = CanonicalEvent(
        id=uuid4(),
        event_type="earthquake",
        title="M5.0 Earthquake near Piraeus",
        status="active",
        severity="moderate",
        geometry_json={"type": "Point", "coordinates": [23.65, 37.94]},
        geometry=geojson_to_wkt_element({"type": "Point", "coordinates": [23.65, 37.94]}),
        spatial_scope="local",
        started_at=now,
        updated_at=now,
        confidence="medium",
        is_active=True,
    )
    db_session.add(event)
    db_session.flush()

    created, updated = calculate_exposure_for_event(db_session, event.id)
    assert created >= 1
    assert updated == 0

    created2, updated2 = calculate_exposure_for_event(db_session, event.id)
    assert created2 == 0
    assert updated2 >= 1


def test_api_list_assets(client, db_session) -> None:
    import_exposure_fixtures(db_session)
    db_session.commit()

    response = client.get("/api/v1/assets?asset_type=port&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 10
    assert len(data["items"]) == 5
    assert all(item["asset_type"] == "port" for item in data["items"])


def test_api_get_asset(client, db_session) -> None:
    import_exposure_fixtures(db_session)
    db_session.commit()

    listing = client.get("/api/v1/assets?asset_type=airport&limit=1").json()
    asset_id = listing["items"][0]["id"]

    response = client.get(f"/api/v1/assets/{asset_id}")
    assert response.status_code == 200
    assert response.json()["id"] == asset_id


def test_api_event_exposures(client, db_session) -> None:
    _seed_demo_assets(db_session)
    now = _now()

    event = CanonicalEvent(
        event_type="earthquake",
        title="M6.0 Earthquake near Singapore",
        status="active",
        severity="severe",
        geometry_json={"type": "Point", "coordinates": [103.82, 1.26]},
        geometry=geojson_to_wkt_element({"type": "Point", "coordinates": [103.82, 1.26]}),
        spatial_scope="local",
        started_at=now,
        updated_at=now,
        confidence="high",
        is_active=True,
    )
    db_session.add(event)
    db_session.flush()
    run_calculate_exposure(db_session, event_id=event.id)
    db_session.commit()

    response = client.get(f"/api/v1/events/{event.id}/exposures")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["event_id"] == str(event.id)


def test_api_admin_calculate_exposure(client, db_session) -> None:
    _seed_demo_assets(db_session)
    now = _now()

    event = CanonicalEvent(
        event_type="storm",
        title="Mediterranean Storm",
        status="active",
        severity="moderate",
        geometry_json={
            "type": "Polygon",
            "coordinates": [
                [
                    [23.0, 37.5],
                    [24.5, 37.5],
                    [24.5, 38.5],
                    [23.0, 38.5],
                    [23.0, 37.5],
                ]
            ],
        },
        geometry=geojson_to_wkt_element(
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [23.0, 37.5],
                        [24.5, 37.5],
                        [24.5, 38.5],
                        [23.0, 38.5],
                        [23.0, 37.5],
                    ]
                ],
            }
        ),
        spatial_scope="regional",
        started_at=now,
        updated_at=now,
        confidence="medium",
        is_active=True,
    )
    db_session.add(event)
    db_session.commit()

    response = client.post(
        "/api/v1/admin/calculate-exposure",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"event_id": str(event.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["events_processed"] == 1
    assert data["exposures_created"] >= 1


def test_api_exposure_analysis(client, db_session) -> None:
    _seed_demo_assets(db_session)
    now = _now()

    event = CanonicalEvent(
        event_type="earthquake",
        title="M5.5 Earthquake near Frankfurt",
        status="active",
        severity="moderate",
        geometry_json={"type": "Point", "coordinates": [8.56, 50.04]},
        geometry=geojson_to_wkt_element({"type": "Point", "coordinates": [8.56, 50.04]}),
        spatial_scope="local",
        started_at=now,
        updated_at=now,
        confidence="medium",
        is_active=True,
    )
    db_session.add(event)
    db_session.flush()
    run_calculate_exposure(db_session, event_id=event.id)
    db_session.commit()

    response = client.get(f"/api/v1/exposure/analysis?event_id={event.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["event_id"] == str(event.id)
    assert data["total"] >= 1


def test_airports_fixture_includes_cgn(db_session) -> None:
    """Demo airport fixture must include Cologne/Bonn (CGN) and major EU hubs."""
    import json
    from pathlib import Path

    fixture_path = Path(__file__).resolve().parents[4] / "fixtures" / "exposure" / "airports.json"
    airports = json.loads(fixture_path.read_text())
    iata_codes = {a["metadata"]["iata"] for a in airports}

    assert "CGN" in iata_codes
    for code in ("MUC", "DUS", "BER", "FRA"):
        assert code in iata_codes
    assert len(airports) >= 25
