"""LLM 结构化抽取:把聊天消息变成推荐候选。

LLM 只输出股票名称,不输出代码(代码由本地消歧完成)。
无 LLM key 时可用 rule_extract 做关键词粗抽(测试/离线兜底)。
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential


class ExtractedRec(BaseModel):
    symbol_name: str = Field(description="股票中文名或常见简称,不要输出代码")
    action: Literal["buy", "sell", "hold", "watch"]
    confidence: Literal["explicit", "mention", "review"]
    target_price: float | None = None
    stop_loss: float | None = None
    horizon: Literal["short", "mid", "long"] = "short"
    reason: str = ""


class ExtractBatch(BaseModel):
    recommendations: list[ExtractedRec]


_SYSTEM = """你是投资聊天记录分析助手。从消息中抽取股票推荐。
规则:
1. 只抽取明确涉及具体股票的内容;闲聊、宏观评论不要输出。
2. symbol_name 只填中文名或市场常用简称(如"茅台""宁德时代"),绝不填代码。
3. confidence:
   - explicit:明确建议买入/卖出/关注(含目标价/仓位)
   - mention:顺带提及,无操作建议
   - review:复盘旧票或已持仓评论
4. 一条消息可能含多只股票,全部列出。无推荐则 recommendations 为空数组。
5. 严格按 JSON schema 输出。"""


class LlmExtractor:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
    ) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    def extract(self, text: str, speaker: str = "") -> list[ExtractedRec]:
        user = f"发言人:{speaker}\n消息:\n{text}" if speaker else text
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        # 兼容模型直接返回数组或包在 recommendations 里
        if isinstance(data, list):
            data = {"recommendations": data}
        batch = ExtractBatch.model_validate(data)
        return batch.recommendations


# ---- 规则粗抽(无 LLM / 测试用)----

# 常见口语 → 规范名,仅作规则抽取提示;真正消歧走 instruments 表
_KNOWN = {
    "茅台": "贵州茅台",
    "五粮液": "五粮液",
    "宁德时代": "宁德时代",
    "比亚迪": "比亚迪",
    "招商银行": "招商银行",
    "平安银行": "平安银行",
    "中国平安": "中国平安",
    "隆基": "隆基绿能",
    "中芯国际": "中芯国际",
}
_BUY = re.compile(r"(买入|建仓|加仓|逢低吸纳|重点关注|强烈推荐|建议关注)")
_SELL = re.compile(r"(卖出|减仓|止盈|清仓)")
_TARGET = re.compile(r"目标[价位]?[：:\s]*(\d+(?:\.\d+)?)")
_STOP = re.compile(r"止损[：:\s]*(\d+(?:\.\d+)?)")


def rule_extract(text: str) -> list[ExtractedRec]:
    """关键词粗抽:命中已知股票名 + 买卖动词 → explicit,仅命中名 → mention。"""
    hits: list[ExtractedRec] = []
    for alias, name in _KNOWN.items():
        if alias not in text and name not in text:
            continue
        if _SELL.search(text):
            action, conf = "sell", "explicit"
        elif _BUY.search(text):
            action, conf = "buy", "explicit"
        else:
            action, conf = "watch", "mention"
        tp = float(m.group(1)) if (m := _TARGET.search(text)) else None
        sl = float(m.group(1)) if (m := _STOP.search(text)) else None
        hits.append(
            ExtractedRec(
                symbol_name=name,
                action=action,  # type: ignore[arg-type]
                confidence=conf,  # type: ignore[arg-type]
                target_price=tp,
                stop_loss=sl,
                reason=text[:120],
            )
        )
    return hits
