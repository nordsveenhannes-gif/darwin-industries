import unittest

from backend.trading_desk import _meme_setup_features


def candle(ts, open_, high, low, close, volume):
    return {
        "timestamp": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


class MemeSetupFeatureTests(unittest.TestCase):
    def test_repeat_support_reclaim_and_momentum_pass(self):
        candles = []
        closes = [
            100.4, 100.1, 100.5, 100.2, 100.6, 100.3,
            100.7, 100.2, 100.8, 100.3, 100.9, 100.4,
            100.7, 101.2, 102.0,
        ]
        for i, close in enumerate(closes):
            low = 99.5 if i in {1, 3, 7, 9} else close - 0.35
            volume = 100.0 if i < 12 else 145.0 + i
            candles.append(
                candle(
                    1_700_000_000 + i * 300,
                    close - 0.1,
                    close + 0.25,
                    low,
                    close,
                    volume,
                )
            )

        features = _meme_setup_features(candles, buys_h1=22, sells_h1=11)
        self.assertTrue(features["passes"])
        self.assertGreaterEqual(features["support_touches"], 2)
        self.assertGreater(features["momentum_15m_pct"], 0.3)
        self.assertGreaterEqual(features["volume_ratio"], 1.05)

    def test_buy_pressure_failure_waits(self):
        candles = []
        for i in range(15):
            close = 100.0 + max(0, i - 11) * 0.7
            low = 99.4 if i in {2, 5, 8} else close - 0.3
            volume = 100.0 if i < 12 else 160.0
            candles.append(
                candle(
                    1_700_000_000 + i * 300,
                    close - 0.1,
                    close + 0.2,
                    low,
                    close,
                    volume,
                )
            )

        features = _meme_setup_features(candles, buys_h1=5, sells_h1=18)
        self.assertFalse(features["passes"])
        self.assertIn("buys/sells", features["reason"])


if __name__ == "__main__":
    unittest.main()
