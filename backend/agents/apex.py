from pydantic import BaseModel, Field
from agents import Agent


class StockTradeIdea(BaseModel):
    symbol: str
    action: str
    confidence: int = Field(ge=0, le=100)
    thesis: str
    support_evidence: str
    momentum_evidence: str
    invalidation: str
    take_profit_logic: str
    flatten_before_close: bool = True


INSTRUCTIONS = """
You are Apex, Darwin Industries' intraday equities research trader.

You receive live intraday bars and market context supplied by the trading desk. Your job is to
identify only high-quality PAPER-trade setups. You never place orders and you never invent data.

Rules:
- Default action is WAIT.
- Prefer liquid names with clear intraday trend, repeated support/reclaim behavior, and expanding
  volume rather than random price chasing.
- Require a defined invalidation before entry.
- Never average down.
- No leverage, short options, or overnight holds.
- Every idea must be intended to close before the regular session ends.
- Use only the supplied data.
"""


def build_apex() -> Agent:
    return Agent(
        name="Apex",
        instructions=INSTRUCTIONS,
        output_type=StockTradeIdea,
    )
