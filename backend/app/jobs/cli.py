"""CLI for ingest and health checks."""

import argparse
import asyncio
import sys

from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger
from app.db.session import SessionLocal
from app.services.briefing_service import generate_briefing
from app.services.ingest_service import run_ingest
from app.sources.registry import get_adapters

setup_logging()
logger = get_logger(__name__)


async def cmd_ingest(sources: list[str] | None) -> int:
    settings = get_settings()
    logger.info("Starting ingest (demo_mode=%s)", settings.demo_mode)
    db = SessionLocal()
    try:
        run = await run_ingest(db, sources=sources)
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

    sub.add_parser("health", help="Check database and source health")

    briefing_parser = sub.add_parser("generate-briefing", help="Generate rule-based briefing")
    briefing_parser.add_argument(
        "--type",
        choices=["auto", "rule_based", "llm"],
        default="auto",
        help="Briefing type (auto=rule_based until Phase 6)",
    )

    args = parser.parse_args()
    if args.command == "ingest":
        code = asyncio.run(cmd_ingest(args.sources))
    elif args.command == "health":
        code = asyncio.run(cmd_health())
    elif args.command == "generate-briefing":
        code = asyncio.run(cmd_generate_briefing(args.type))
    else:
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
