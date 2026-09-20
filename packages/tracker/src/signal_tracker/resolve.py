"""本地消歧:股票名称 → 代码。LLM 不产代码。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolveResult:
    status: str  # resolved / ambiguous / unresolved
    symbol: str | None
    candidates: list[tuple[str, str]]  # [(symbol, name), ...]


def build_name_index(
    aliases: dict[str, str], instruments: list[tuple[str, str]]
) -> dict[str, list[tuple[str, str]]]:
    """构建 规范化名称 → [(symbol, name)] 索引。

    aliases: 别名 → symbol
    instruments: [(symbol, name)]
    """
    index: dict[str, list[tuple[str, str]]] = {}
    name_by_symbol = {s: n for s, n in instruments}

    def add(key: str, symbol: str, name: str) -> None:
        k = _norm(key)
        if not k:
            return
        bucket = index.setdefault(k, [])
        if (symbol, name) not in bucket:
            bucket.append((symbol, name))

    for symbol, name in instruments:
        add(name, symbol, name)
    for alias, symbol in aliases.items():
        add(alias, symbol, name_by_symbol.get(symbol, alias))
    return index


def resolve_name(name: str, index: dict[str, list[tuple[str, str]]]) -> ResolveResult:
    key = _norm(name)
    hits = index.get(key, [])
    if not hits:
        # 后缀模糊:索引 key 以查询结尾,或查询以索引 key 结尾(茅台 ↔ 贵州茅台)
        fuzzy = [
            item
            for k, items in index.items()
            if k.endswith(key) or key.endswith(k)
            for item in items
        ]
        hits = fuzzy
    # 按 symbol 去重(同一股票多个别名不算歧义)
    seen: set[str] = set()
    uniq: list[tuple[str, str]] = []
    for s, n in hits:
        if s not in seen:
            seen.add(s)
            uniq.append((s, n))
    hits = uniq
    if len(hits) == 1:
        return ResolveResult("resolved", hits[0][0], hits)
    if len(hits) > 1:
        return ResolveResult("ambiguous", None, hits)
    return ResolveResult("unresolved", None, [])


def _norm(s: str) -> str:
    return s.strip().replace(" ", "").replace("Ａ", "A").replace("Ｂ", "B").lower()
