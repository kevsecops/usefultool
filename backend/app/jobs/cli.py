"""CLI for ingest and health checks."""

import argparse
import asyncio
import sys

from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger
from app.db.session import SessionLocal
from app.services.briefing_service import generate_briefing
from app.services.correlation_service import run_correlation
from app.services.exposure_service import import_exposure_fixtures, run_calculate_exposure
from app.services.ingest_service import run_ingest
from app.sources.registry import get_adapters

setup_logging()
logger = get_logger(__name__)


async def cmd_ingest(sources: list[str] | None, generate_briefing: bool | None) -> int:
    settings = get_settings()
    should_generate = (
        generate_briefing
        if generate_briefing is not None
        else settings.auto_generate_briefing
    )
    logger.info(
        "Starting ingest (demo_mode=%s, generate_briefing=%s)",
        settings.demo_mode,
        should_generate,
    )
    db = SessionLocal()
    try:
        run = await run_ingest(db, sources=sources, generate_briefing=should_generate)
        db.commit()
        logger.info(
            "Ingest complete: status=%s fetched=%d created=%d updated=%d deactivated=%d",
            run.status,
            run.alerts_fetched,
            run.alerts_created,
            run.alerts_updated,
            run.alerts_deactivated,
        )
        if run.errors:
            for err in run.errors:
                logger.error("Source error: %s", err)
        if not should_generate and run.status in ("success", "partial"):
            logger.info(
                "Briefing not regenerated. Run "
                "`python -m app.jobs.cli generate-briefing` or set AUTO_GENERATE_BRIEFING=true."
            )
        return 0 if run.status in ("success", "partial") else 1
    finally:
        db.close()


async def cmd_health() -> int:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        logger.info("Database: connected")
    except Exception as exc:
        logger.error("Database: disconnected (%s)", exc)
        return 1
    finally:
        db.close()

    adapters = get_adapters()
    all_healthy = True
    for adapter in adapters:
        health = await adapter.health_check()
        if health.is_healthy:
            logger.info("Source %s: healthy", adapter.source_id)
        else:
            logger.warning("Source %s: unhealthy — %s", adapter.source_id, health.error_message)
            all_healthy = False
    return 0 if all_healthy else 1


async def cmd_correlate() -> int:
    settings = get_settings()
    db = SessionLocal()
    try:
        result = run_correlation(db)
        db.commit()
        logger.info(
            "Correlation complete: created=%d updated=%d links=%d possible=%d processed=%d",
            result.canonical_events_created,
            result.canonical_events_updated,
            result.links_created,
            result.possible_matches,
            result.members_processed,
        )
        if settings.exposure_auto_run:
            exp_result = run_calculate_exposure(db, active_only=True)
            db.commit()
            logger.info(
                "Exposure auto-run: events=%d created=%d updated=%d",
                exp_result.events_processed,
                exp_result.exposures_created,
                exp_result.exposures_updated,
            )
        return 0
    finally:
        db.close()


async def cmd_import_exposure() -> int:
    db = SessionLocal()
    try:
        result = import_exposure_fixtures(db)
        db.commit()
        logger.info(
            "Exposure fixtures imported: created=%d updated=%d total=%d",
            result.assets_created,
            result.assets_updated,
            result.total_assets,
        )
        return 0
    finally:
        db.close()


async def cmd_calculate_exposure(event_id: str | None = None) -> int:
    db = SessionLocal()
    try:
        from uuid import UUID

        eid = UUID(event_id) if event_id else None
        result = run_calculate_exposure(db, event_id=eid, active_only=True)
        db.commit()
        logger.info(
            "Exposure calculation: events=%d created=%d updated=%d version=%s",
            result.events_processed,
            result.exposures_created,
            result.exposures_updated,
            result.analysis_version,
        )
        return 0
    finally:
        db.close()


async def cmd_generate_briefing(briefing_type: str = "auto") -> int:
    db = SessionLocal()
    try:
        briefing = generate_briefing(db, briefing_type=briefing_type)
        db.commit()
        logger.info(
            "Briefing generated: id=%s type=%s score=%d",
            briefing.id,
            briefing.type,
            briefing.overall_risk_score,
        )
        return 0
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Global Risk Intelligence jobs")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest_parser = sub.add_parser("ingest", help="Run alert ingest")
    ingest_parser.add_argument("--sources", nargs="*", help="Limit to specific sources")
    ingest_parser.add_argument(
        "--generate-briefing",
        action="store_true",
        default=None,
        help="Generate briefing after ingest (default: AUTO_GENERATE_BRIEFING env)",
    )
    ingest_parser.add_argument(
        "--no-generate-briefing",
        action="store_true",
        help="Skip briefing generation after ingest",
    )

    sub.add_parser("health", help="Check database and source health")

    sub.add_parser("correlate", help="Run cross-source event correlation")

    sub.add_parser("import-exposure", help="Import demo exposure asset fixtures")

    calc_parser = sub.add_parser("calculate-exposure", help="Calculate event asset exposures")
    calc_parser.add_argument("--event-id", help="Limit to a single canonical event UUID")

    briefing_parser = sub.add_parser("generate-briefing", help="Generate risk briefing")
    briefing_parser.add_argument(
        "--type",
        choices=["auto", "rule_based", "llm"],
        default="auto",
        help="Briefing type (auto=LLM when LLM_ENABLED, else rule_based)",
    )

    args = parser.parse_args()
    if args.command == "ingest":
        gen_flag: bool | None = None
        if args.generate_briefing:
            gen_flag = True
        elif args.no_generate_briefing:
            gen_flag = False
        code = asyncio.run(cmd_ingest(args.sources, gen_flag))
    elif args.command == "health":
        code = asyncio.run(cmd_health())
    elif args.command == "correlate":
        code = asyncio.run(cmd_correlate())
    elif args.command == "import-exposure":
        code = asyncio.run(cmd_import_exposure())
    elif args.command == "calculate-exposure":
        code = asyncio.run(cmd_calculate_exposure(getattr(args, "event_id", None)))
    elif args.command == "generate-briefing":
        code = asyncio.run(cmd_generate_briefing(args.type))
    else:
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
