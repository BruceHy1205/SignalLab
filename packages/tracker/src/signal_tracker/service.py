"""导入流水线:解析 → 抽取 → 消歧 → 入库;以及锚定与 event study 重算。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from signal_tracker import repo
from signal_tracker.event_study import (
    WINDOWS,
    anchor_baseline,
    compute_windows,
    trading_days_ahead,
)
from signal_tracker.extract import ExtractedRec, LlmExtractor, rule_extract
from signal_tracker.parser import ChatMessage, parse_paste, parse_wechat_txt
from signal_tracker.ports import BarsReader
from signal_tracker.resolve import build_name_index, resolve_name

logger = logging.getLogger(__name__)
CN_TZ = ZoneInfo("Asia/Shanghai")
BENCHMARK = "000300.SH"


class ImportService:
    def __init__(
        self,
        bars: BarsReader,
        extractor: LlmExtractor | None = None,
        extract_fn: Callable[[str], list[ExtractedRec]] | None = None,
    ) -> None:
        self._bars = bars
        self._extractor = extractor
        self._extract_fn = extract_fn or rule_extract

    def _extract(self, text: str, speaker: str) -> list[ExtractedRec]:
        if self._extractor is not None:
            try:
                return self._extractor.extract(text, speaker)
            except Exception:
                logger.exception("LLM 抽取失败,回退规则抽取")
        return self._extract_fn(text)

    def import_text(
        self,
        session: Session,
        content: str,
        *,
        source_name: str,
        channel: str = "paste",
        format: str = "paste",  # paste | wechat
    ) -> dict:
        messages = (
            parse_wechat_txt(content) if format == "wechat" else parse_paste(content, source_name)
        )
        return self.import_messages(session, messages, source_name=source_name, channel=channel)

    def import_messages(
        self,
        session: Session,
        messages: list[ChatMessage],
        *,
        source_name: str,
        channel: str = "wechat",
    ) -> dict:
        source = repo.get_or_create_source(session, source_name, channel)
        # 消歧索引:从 BarsReader 拉全量
        instruments = []
        aliases = self._bars.list_aliases()
        # list_aliases 应包含正式名与口语别名 → symbol
        for name, symbol in aliases.items():
            instruments.append((symbol, name))
        index = build_name_index(aliases, instruments)

        created = skipped = pending = 0
        for msg in messages:
            extracted = self._extract(msg.text, msg.speaker)
            for item in extracted:
                if repo.find_duplicate(session, source.id, msg.message_time, msg.raw_block):
                    skipped += 1
                    continue
                resolved = resolve_name(item.symbol_name, index)
                status = "active" if resolved.status == "resolved" else "pending"
                if status == "pending":
                    pending += 1
                ts = msg.message_time or datetime.now(CN_TZ)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=CN_TZ)
                rec = repo.insert_recommendation(
                    session,
                    source_id=source.id,
                    message_time=ts,
                    symbol=resolved.symbol,
                    symbol_name=item.symbol_name,
                    action=item.action,
                    target_price=item.target_price,
                    stop_loss=item.stop_loss,
                    horizon=item.horizon,
                    confidence=item.confidence,
                    reason=item.reason,
                    raw_text=msg.raw_block,
                    status=status,
                )
                created += 1
                if status == "active" and item.confidence == "explicit":
                    self.refresh_recommendation(session, rec.id)
        session.commit()
        return {"created": created, "skipped": skipped, "pending": pending}

    def resolve_pending(self, session: Session, rec_id: str, symbol: str) -> None:
        rec = repo.get_recommendation(session, rec_id)
        if not rec:
            raise KeyError(rec_id)
        rec.symbol = symbol
        rec.status = "active"
        session.commit()
        self.refresh_recommendation(session, rec_id)

    def refresh_recommendation(self, session: Session, rec_id: str) -> None:
        rec = repo.get_recommendation(session, rec_id)
        if not rec or not rec.symbol:
            return
        end = trading_days_ahead(rec.message_time.date(), max(WINDOWS))
        start = rec.message_time.date()
        bars = self._bars.get_qfq_bars(rec.symbol, start, end)
        if bars.empty:
            return
        baseline = anchor_baseline(rec.message_time, bars)
        if baseline is None:
            return
        rec.baseline_date = baseline.date
        rec.baseline_price = baseline.price
        rec.baseline_rule = baseline.rule
        bench = self._bars.get_qfq_bars(BENCHMARK, baseline.date, end)
        perfs = compute_windows(bars, baseline, bench, rec.target_price, rec.stop_loss)
        rows = [
            {
                "window_days": p.window_days,
                "abs_return": p.abs_return,
                "excess_return": p.excess_return,
                "max_drawdown": p.max_drawdown,
                "max_runup": p.max_runup,
                "hit_target_first": p.hit_target_first,
                "hit_stop_first": p.hit_stop_first,
                "as_of_date": p.as_of_date,
            }
            for p in perfs
        ]
        repo.upsert_performance(session, rec.id, rows)
        session.commit()

    def refresh_all_active(self, session: Session) -> int:
        recs = repo.list_recommendations(session, status="active", limit=10_000)
        n = 0
        for rec in recs:
            if rec.confidence != "explicit":
                continue
            self.refresh_recommendation(session, rec.id)
            n += 1
        return n
