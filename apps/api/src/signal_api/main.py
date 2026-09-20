from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from signal_datahub.config import DatahubSettings, build_providers
from signal_datahub.sync import SyncService, market_today
from starlette.middleware.base import BaseHTTPMiddleware

from signal_api.config import ApiSettings
from signal_api.db import init_engine, make_session
from signal_api.routes import (
    agents_routes,
    datahub_routes,
    health,
    live_routes,
    notify_routes,
    papertrade_routes,
    research_routes,
    tracker_routes,
)

logger = logging.getLogger(__name__)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """可选 Bearer token;api_token 为空时不鉴权(本地开发)。"""

    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        expected = f"Bearer {self._token}"
        if auth != expected:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)


def _run_daily_incremental() -> None:
    try:
        svc = SyncService(build_providers(DatahubSettings()))
        with make_session() as session:
            result = svc.daily_incremental(session)
        logger.info("每日增量同步完成: %s", result)
    except Exception:
        logger.exception("每日增量同步失败")
    try:
        from signal_tracker.service import ImportService

        from signal_api.adapters.datahub_bars import DatahubBarsReader

        tracker = ImportService(DatahubBarsReader(make_session))
        with make_session() as session:
            n = tracker.refresh_all_active(session)
        logger.info("推荐窗口刷新完成: %s", n)
    except Exception:
        logger.exception("推荐窗口刷新失败")
    try:
        from signal_papertrade.service import PaperService

        from signal_api.adapters.datahub_prices import DatahubPriceReader

        paper = PaperService(DatahubPriceReader(make_session))
        trade_date = market_today()
        with make_session() as session:
            r = paper.run_day(session, trade_date)
        logger.info("模拟盘日终 %s: %s", trade_date, r)
    except Exception:
        logger.exception("模拟盘日终失败")
    try:
        from signal_research.service import ResearchService, ResearchSettings

        from signal_api.adapters.research_market import ResearchMarketAdapter
        from signal_api.config import ApiSettings as _S

        s = _S()
        research = ResearchService(
            ResearchMarketAdapter(make_session),
            settings=ResearchSettings(heartbeat_timeout_sec=s.research_heartbeat_timeout_sec),
        )
        with make_session() as session:
            lost = research.probe_lost_jobs(session)
        if lost:
            logger.warning("标记失联任务: %s", lost)
    except Exception:
        logger.exception("研究任务失联探测失败")


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or ApiSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_engine(settings.database_url)
        scheduler: BackgroundScheduler | None = None
        if settings.scheduler_enabled:
            scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)
            scheduler.add_job(
                _run_daily_incremental,
                CronTrigger(
                    hour=settings.scheduler_cron_hour,
                    minute=settings.scheduler_cron_minute,
                    timezone=settings.scheduler_timezone,
                ),
                id="daily_incremental",
            )
            scheduler.start()
            logger.info(
                "定时同步已启用: %02d:%02d %s",
                settings.scheduler_cron_hour,
                settings.scheduler_cron_minute,
                settings.scheduler_timezone,
            )
        yield
        if scheduler:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="signal", version="0.1.0", lifespan=lifespan)
    if settings.api_token:
        app.add_middleware(BearerAuthMiddleware, token=settings.api_token)
    app.include_router(health.router)
    app.include_router(datahub_routes.router, prefix="/api/datahub", tags=["datahub"])
    app.include_router(tracker_routes.router, prefix="/api/tracker", tags=["tracker"])
    app.include_router(papertrade_routes.router, prefix="/api/papertrade", tags=["papertrade"])
    app.include_router(agents_routes.router, prefix="/api/agents", tags=["agents"])
    app.include_router(research_routes.router, prefix="/api/research", tags=["research"])
    app.include_router(notify_routes.router, prefix="/api/notify", tags=["notify"])
    app.include_router(live_routes.router, prefix="/api/live", tags=["live"])
    return app


app = create_app()
