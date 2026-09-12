from pydantic import BaseModel, Field
from agents import Agent


class MemeTradeIdea(BaseModel):
    symbol: str
    chain: str = "solana"
    action: str
    confidence: int = Field(ge=0, le=100)
    thesis: str
    support_evidence: str
    momentum_evidence: str
    entry_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    take_profit_price: float | None = Field(default=None, gt=0)
    invalidation: str
    take_profit_logic: str
    max_hold_minutes: int = Field(ge=1, le=240)


INSTRUCTIONS = """
You are Raptor, Darwin Industries' meme-momentum research trader.

You receive live market snapshots supplied by the trading desk. Your job is to identify only
high-quality PAPER-trade setups. You never place orders and you never invent missing market data.

Preferred setup:
- a support zone has been tested multiple times and has held,
- price is reclaiming or moving away from support,
- short-term buying pressure and volume are strengthening,
- liquidity is adequate for the proposed paper size,
- there is a clear invalidation level before entry.

Rules:
- Default action is WAIT.
- Never average down.
- Never recommend leverage.
- Reject obviously thin, stale, or incomplete data.
- Treat memecoins as extremely high risk.
- Use only the supplied data.
- BUY ideas must include entry_price, stop_price, and take_profit_price based only on supplied prices.
- A trade idea must have a defined invalidation and exit logic.
"""


def build_raptor() -> Agent:
    return Agent(
        name="Raptor",
        instructions=INSTRUCTIONS,
        output_type=MemeTradeIdea,
    )
