import os
import time
import unittest

from backend.meme_strategy import (
    compute_stress_level,
    required_score,
    score_candidates,
)
from backend.trading_desk import _map_open_meme_prices


def candles():
    now = int(time.time())
    rows = []
    price = 1.0
    for i in range(60):
        # Slow trend, then stronger expansion in the last 10 minutes.
        step = 0.0015 if i < 50 else 0.007
        open_ = price
        close = price * (1 + step)
        high = close * 1.003
        low = open_ * 0.997
        volume = 100.0 if i < 50 else 260.0 + (i - 50) * 20.0
        rows.append(
            {
                "timestamp": now - (59 - i) * 60,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
        price = close
    return rows


class AdaptiveMemeStrategyTests(unittest.TestCase):
    def setUp(self):
        self.old_fee_mode = os.environ.get("DARWIN_MEME_SIM_FEE_MODE")
        self.old_slippage = os.environ.get("DARWIN_MEME_SIM_SLIPPAGE_BPS")
        os.environ["DARWIN_MEME_SIM_FEE_MODE"] = "dex_route"
        os.environ["DARWIN_MEME_SIM_SLIPPAGE_BPS"] = "35"

    def tearDown(self):
        if self.old_fee_mode is None:
            os.environ.pop("DARWIN_MEME_SIM_FEE_MODE", None)
        else:
            os.environ["DARWIN_MEME_SIM_FEE_MODE"] = self.old_fee_mode
        if self.old_slippage is None:
            os.environ.pop("DARWIN_MEME_SIM_SLIPPAGE_BPS", None)
        else:
            os.environ["DARWIN_MEME_SIM_SLIPPAGE_BPS"] = self.old_slippage

    def test_stress_responds_to_missing_opportunity_not_losses(self):
        self.assertEqual(
            compute_stress_level(
                minutes_since_trade=90,
                active_market=True,
                consecutive_losses=0,
                defensive_mode=False,
            ),
            2,
        )
        self.assertEqual(
            compute_stress_level(
                minutes_since_trade=90,
                active_market=False,
                consecutive_losses=0,
                defensive_mode=False,
            ),
            0,
        )
        self.assertEqual(
            compute_stress_level(
                minutes_since_trade=90,
                active_market=True,
                consecutive_losses=2,
                defensive_mode=False,
            ),
            1,
        )
        self.assertEqual(required_score(4), 55)

    def test_active_multi_signal_candidate_can_pass_adaptive_entry(self):
        candidate = {
            "symbol": "TEST",
            "token_address": "mint-address",
            "pool_address": "pool-address",
            "price_usd": candles()[-1]["close"],
            "liquidity_usd": 120000,
            "market_cap_usd": 900000,
            "fdv_usd": 900000,
            "pair_created_at": (time.time() - 3 * 3600) * 1000,
            "volume_m5": 7000,
            "volume_h1": 18000,
            "volume_h24": 180000,
            "buys_m5": 24,
            "sells_m5": 8,
            "buys_h1": 90,
            "sells_h1": 45,
            "price_change_m5": 5.0,
            "price_change_h1": 18.0,
            "ohlcv_1m": candles(),
        }

        scored = score_candidates(
            [candidate],
            stress_level=2,
            account_equity_usd=100,
            defensive_mode=False,
            max_notional_usd=40,
        )[0]

        self.assertTrue(scored["hard_gate_pass"])
        self.assertGreaterEqual(scored["signal_count"], 2)
        self.assertGreaterEqual(scored["setup_score"], scored["required_score"])
        self.assertTrue(scored["friction_pass"])
        self.assertTrue(scored["technical_pass"])
        self.assertLessEqual(scored["recommended_risk_pct"], 2.0)

    def test_open_position_price_uses_contract_and_most_liquid_pair(self):
        rows = [
            {"symbol": "MEME", "token_address": "mint-1"},
            {"symbol": "OTHER", "token_address": "mint-2"},
        ]
        pairs = [
            {
                "baseToken": {"address": "mint-1"},
                "priceUsd": "1.23",
                "liquidity": {"usd": 10000},
            },
            {
                "baseToken": {"address": "mint-1"},
                "priceUsd": "1.25",
                "liquidity": {"usd": 50000},
            },
            {
                "baseToken": {"address": "mint-2"},
                "priceUsd": "0.42",
                "liquidity": {"usd": 20000},
            },
        ]
        prices = _map_open_meme_prices(rows, pairs)
        self.assertEqual(prices["MEME"], 1.25)
        self.assertEqual(prices["OTHER"], 0.42)

    def test_hard_gate_never_relaxes_for_thin_token(self):
        candidate = {
            "symbol": "THIN",
            "token_address": "mint-address",
            "pool_address": "pool-address",
            "price_usd": 1.0,
            "liquidity_usd": 1200,
            "pair_created_at": (time.time() - 3600) * 1000,
            "volume_m5": 10000,
            "volume_h1": 20000,
            "volume_h24": 200000,
            "buys_m5": 30,
            "sells_m5": 10,
            "buys_h1": 100,
            "sells_h1": 50,
            "price_change_m5": 8,
            "price_change_h1": 25,
            "ohlcv_1m": candles(),
        }
        scored = score_candidates(
            [candidate],
            stress_level=4,
            account_equity_usd=100,
            defensive_mode=False,
            max_notional_usd=40,
        )[0]
        self.assertFalse(scored["hard_gate_pass"])
        self.assertFalse(scored["technical_pass"])
        self.assertIn("liquidity", scored["hard_gate_reason"])


if __name__ == "__main__":
    unittest.main()
