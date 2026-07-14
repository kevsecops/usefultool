"""Implications engine and API tests."""

from datetime import UTC, datetime
from uuid import uuid4

from app.analysis.implications import (
    generate_implications_for_event,
    is_conservative_language,
    validate_implication_text,
)
from app.models.canonical_event import CanonicalEvent
from app.models.canonical_event_link import CanonicalEventLink
from app.models.implication_candidate import ImplicationCandidate
from app.models.observed_event import ObservedEvent
from app.normalization.geometry import geojson_to_wkt_element
from app.services.exposure_service import import_exposure_fixtures, run_calculate_exposure
from app.services.implication_service import (
    generate_implications_for_event_id,
    list_event_implications,
    run_generate_implications,
)


def _now() -> datetime:
    return datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _seed_assets(db_session) -> None:
    import_exposure_fixtures(db_session)
    db_session.flush()


def test_conservative_language_validator() -> None:
    assert is_conservative_language("Mögliche Beeinträchtigung regionaler Transportwege")
    assert is_conservative_language("Potenzielle Belastung von Entwässerungssystemen.")
    assert not is_conservative_language("Häfen geschlossen")
    assert not is_conservative_language("Die Lieferkette bricht zusammen")
    assert not is_conservative_language("Aktien fallen stark")


def test_validate_rejects_forbidden_phrases() -> None:
    try:
        validate_implication_text("Häfen geschlossen in der Region")
        raise AssertionError("Expected ValueError")
    except ValueError:
        pass


def test_storm_ports_logistics_implication(db_session) -> None:
    _seed_assets(db_session)
    now = _now()

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

    run_calculate_exposure(db_session, event_id=event.id)
    db_session.flush()

    drafts = generate_implications_for_event(db_session, event)
    logistics = [d for d in drafts if d.category == "logistics"]
    assert len(logistics) >= 1

    primary = logistics[0]
    assert primary.evidence_level == "inferred_from_exposure"
    assert primary.confidence in ("medium", "high")
    assert "Mögliche" in primary.title
    assert "geschlossen" not in (primary.title + (primary.description or "")).lower()
    assert len(primary.related_asset_ids) >= 2


def test_space_weather_technology_implication(db_session) -> None:
    _seed_assets(db_session)
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
        fingerprint="swpc-g4-impl-fp",
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

    run_calculate_exposure(db_session, event_id=event.id)
    db_session.flush()

    drafts = generate_implications_for_event(db_session, event)
    tech = [d for d in drafts if d.category in ("technology", "energy")]
    assert len(tech) >= 1
    assert any(d.evidence_level == "inferred_from_exposure" for d in tech)
    for draft in drafts:
        combined = f"{draft.title} {draft.description or ''}"
        assert "geschlossen" not in combined.lower()
        assert is_conservative_language(draft.title)


def test_earthquake_airport_implications(db_session) -> None:
    _seed_assets(db_session)
    now = _now()

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
        fingerprint="eq-tokyo-impl-fp",
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

    run_calculate_exposure(db_session, event_id=event.id)
    drafts = generate_implications_for_event(db_session, event)

    categories = {d.category for d in drafts}
    assert "logistics" in categories or "infrastructure" in categories


def test_persist_and_replace_implications(db_session) -> None:
    _seed_assets(db_session)
    now = _now()

    event = CanonicalEvent(
        id=uuid4(),
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
    db_session.flush()

    run_calculate_exposure(db_session, event_id=event.id)
    created, replaced = generate_implications_for_event_id(db_session, event.id)
    assert created >= 1
    assert replaced == 0

    created2, replaced2 = generate_implications_for_event_id(db_session, event.id)
    assert created2 >= 1
    assert replaced2 >= 1


def test_api_event_implications(client, db_session) -> None:
    _seed_assets(db_session)
    now = _now()

    event = CanonicalEvent(
        event_type="storm",
        title="North Sea Storm Warning",
        status="active",
        severity="severe",
        geometry_json={
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
        },
        geometry=geojson_to_wkt_element(
            {
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
        ),
        spatial_scope="regional",
        started_at=now,
        updated_at=now,
        confidence="high",
        is_active=True,
    )
    db_session.add(event)
    db_session.flush()
    run_calculate_exposure(db_session, event_id=event.id)
    run_generate_implications(db_session, event_id=event.id)
    db_session.commit()

    response = client.get(f"/api/v1/events/{event.id}/implications")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["event_id"] == str(event.id)
    item = data["items"][0]
    assert "id" in item
    assert item["evidence_level"] in (
        "observed",
        "officially_reported",
        "inferred_from_exposure",
        "hypothesis",
    )
    assert item["generated_by"] == "rule_based"


def test_api_admin_generate_implications(client, db_session) -> None:
    _seed_assets(db_session)
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

    response = client.post(
        "/api/v1/admin/generate-implications",
        headers={"X-Admin-Token": "test-admin-token"},
        json={"event_id": str(event.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["events_processed"] == 1
    assert data["implications_created"] >= 1
    assert data["engine_version"] == "1"

    listed = list_event_implications(db_session, event.id)
    assert listed is not None
    assert listed.total >= 1


def test_briefing_includes_implication_refs(db_session) -> None:
    from app.analysis.clustering import detect_hotspots
    from app.analysis.risk_score import compute_global_risk_score
    from app.analysis.rule_briefing import generate_rule_briefing
    from app.models.alert import Alert

    _seed_assets(db_session)
    now = _now()

    event = CanonicalEvent(
        event_type="storm",
        title="North Sea Storm Warning",
        status="active",
        severity="severe",
        geometry_json={
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
        },
        geometry=geojson_to_wkt_element(
            {
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
        ),
        spatial_scope="regional",
        started_at=now,
        updated_at=now,
        confidence="high",
        is_active=True,
    )
    db_session.add(event)
    db_session.flush()
    run_calculate_exposure(db_session, event_id=event.id)
    generate_implications_for_event_id(db_session, event.id)
    db_session.flush()

    from sqlalchemy import select

    candidates = list(
        db_session.scalars(
            select(ImplicationCandidate).where(
                ImplicationCandidate.canonical_event_id == event.id
            )
        ).all()
    )
    assert len(candidates) >= 1

    alerts = [
        Alert(
            id=uuid4(),
            source="noaa",
            source_alert_id="test-1",
            title="Storm Warning",
            category="weather",
            severity="severe",
            status="actual",
            country_code="NL",
            issued_at=now,
            ingested_at=now,
            last_seen_at=now,
            raw_payload={},
            fingerprint="fp-storm",
            is_active=True,
        )
    ]
    risk = compute_global_risk_score(alerts, cluster_bonuses=[], rolling_avg_active=1)
    briefing = generate_rule_briefing(
        alerts,
        risk=risk,
        hotspots=detect_hotspots(alerts),
        implication_candidates=candidates,
    )

    assert "implication_refs" in briefing
    refs = briefing["implication_refs"]["logistics"]
    assert len(refs) >= 1
    assert refs[0]["id"] == str(candidates[0].id)
    assert refs[0]["text"] == candidates[0].title
    assert refs[0]["canonical_event_id"] == str(event.id)

    logistics_texts = briefing["potential_implications"]["logistics"]
    assert candidates[0].title in logistics_texts
