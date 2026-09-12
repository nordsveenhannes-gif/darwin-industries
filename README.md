# Darwin Industries

Darwin Industries is an experimental multi-agent company runtime designed to do bounded, auditable business work with persistent state.

## Current business loop

The runtime can now:

- research real local-service businesses on the public web,
- score prospects with Mercury,
- produce an evidence-based website audit with Forge,
- QA the audit and outreach with Sentinel,
- draft short personalized outreach,
- verify only explicitly published generic business/role email addresses,
- send controlled outreach through Resend when the owner enables it,
- enforce a small daily send cap, one-contact-only behavior, and local suppression,
- put the 10-agent operating company on shift for a bounded multi-hour workday,
- expose a separate 3-agent experimental trading desk (Raptor, Apex, Circuit) in PAPER mode,
- run Oracle, Mercury, Forge, and Sentinel as the core revenue crew every cycle,
- rotate Atlas, Ledger, Nova, Freya, Midas, and Satoshi through one department shift each cycle,
- persist pipeline, email, task, and work-session state in SQLite.

Cash spending remains disabled. The trading desk is simulation-only and does not place real-money orders.

## Run a workday

After local setup:

```bat
python -m backend.workday --hours 6
```

Defaults:

- 6-hour bounded session
- one cycle per hour
- 50-model-call local guardrail
- 4 researched prospects per cycle
- all 10 agents placed on shift
- core revenue crew works every cycle
- one support department completes a focused company task each cycle
- minimum sales score 70 before contact verification
- controlled email daily cap 3 when sending is enabled
- no automatic follow-up sequence
- no cash spending

Stop safely at any time with Ctrl+C.

Useful zero-model-call views:

```bat
python -m backend.status
python -m backend.prospects
python -m backend.emailer
python -m backend.dashboard
python -m backend.board
```

## Full-company workday

A normal six-cycle workday uses the roster this way:

- **Oracle** researches prospects and verifies safe public business contacts every cycle.
- **Mercury** scores prospects, drafts outreach, and executes guarded sales every cycle.
- **Forge** produces evidence-based audits every cycle.
- **Sentinel** QA-checks audits, outreach, and outbound safety every cycle.
- **Atlas, Ledger, Nova, Freya, Midas, and Satoshi** rotate through one focused department assignment per cycle so all six complete work during a normal 6-hour session.

The rotation is deliberate: all agents are on shift, but Darwin does not burn six extra model calls every hour just to make them look busy. Department outputs are persisted and can be read with `python -m backend.board`. The status screen also tracks each agent's last action plus simulated confidence, stress, motivation, and job security.

## Live Mission Control + owner customer demo

Darwin now includes a local live monitoring screen. It reads SQLite state only, auto-refreshes every two seconds, and does not trigger model calls.

Start it in one Command Prompt window:

```bat
python -m backend.dashboard
```

Open:

```text
http://127.0.0.1:8765
```

The screen shows the full agent floor, current actions, simulated confidence/stress/motivation/job security, sales-pipeline state, company events, and a step-by-step customer journey.

To experience Darwin as the customer, use a second Command Prompt window:

```bat
python -m backend.demo_customer --business-name "Uptrend" --website "https://uptrend.live" --email "hannes@uptrend.live" --pace-seconds 5
```

That run performs live public research, creates a focused audit, Sentinel QA-checks it, Mercury writes the actual customer approach, and Sentinel QA-checks the email. It stops before sending by default.

To send the final approved demo email to the explicitly supplied address:

```bat
python -m backend.demo_customer --business-name "Uptrend" --website "https://uptrend.live" --email "hannes@uptrend.live" --pace-seconds 5 --send
```

The demo deliberately stops at the payment boundary because Stripe checkout/webhook is not wired into Darwin yet. The dashboard labels that gap instead of fabricating a sale.

## Experimental Trading Desk — PAPER mode

Darwin now has a separate experimental trading department:

- **Raptor** scans Moonshot public market data for meme-token momentum setups. It prefers repeated support that has actually been observed in Darwin's stored price history plus strengthening momentum. Default action is WAIT.
- **Apex** reviews owner-configured liquid equities using Alpaca paper market data. It requires a defined entry, stop, target, and same-day exit.
- **Circuit** is an independent risk gate. It can block a setup even when Raptor or Apex wants it.

The desk currently supports **paper trading only**. There is no Moonshot account signing, wallet private key handling, or live stock order endpoint in Darwin. This is deliberate while the strategy is being measured.

Run a bounded paper session:

```bat
python -m backend.trading_desk --hours 6 --interval-minutes 5
```

Raptor can read the public Moonshot data API without account credentials. Apex stays in `WAITING_CONFIG` until an Alpaca **paper** API key/secret and an owner-selected stock watchlist are added to the private `.env`.

Example private configuration:

```text
DARWIN_TRADING_MODE=paper
DARWIN_MEME_PAPER_NOTIONAL_USD=10
DARWIN_MEME_PAPER_DAILY_STOP_USD=5

ALPACA_PAPER_API_KEY=...
ALPACA_PAPER_API_SECRET=...
DARWIN_STOCK_WATCHLIST=YOUR,TICKERS,HERE
DARWIN_STOCK_PAPER_NOTIONAL_USD=100
DARWIN_STOCK_PAPER_DAILY_STOP_USD=20
```

Mission Control shows open simulated positions, realized net P&L, estimated fees, win rate, profit factor, max drawdown, latest Raptor/Apex signals, and all three trading agents. Paper P&L is tracked separately from operating revenue. The simulation uses observed market prices plus configurable fake slippage and costs rather than trusting the agent's proposed fill price.

### Trader scoreboard and live-trading graduation

You can read the zero-model-call scoreboard at any time:

```bat
python -m backend.trading_stats
```

Each trader is tracked separately for signals, BUY/WAIT decisions, closed trades, wins/losses, win rate, gross P&L, estimated fees, net P&L, profit factor, average trade, best/worst trade, and maximum drawdown. Fewer than 20 closed trades is labelled `INSUFFICIENT_SAMPLE`; after that Darwin can label a profitable, profit-factor >= 1.20 run as `PROMISING`. This label never unlocks real money automatically.

The intended graduation path is:

```text
live market data -> fake trades -> measured statistics -> owner review
-> isolated low-balance signer -> hard deterministic limits -> live transactions
```

For a future Moonshot-wallet connection, never paste or commit the Moonshot secret phrase. The signer must be configured locally or through a dedicated secrets/signing system, and the live wallet should have a deliberately small balance and hard loss limits.

## Controlled outbound email

Email sending is OFF by default. Put these values only in your private `.env` or cloud secret store:

```text
RESEND_API_KEY=your_restricted_resend_key
DARWIN_EMAIL_FROM=your_verified_sender@yourdomain.com
DARWIN_EMAIL_REPLY_TO=your_real_inbox@yourdomain.com
DARWIN_ALLOW_EMAIL_SEND=true
DARWIN_EMAIL_DAILY_CAP=3
DARWIN_EMAIL_MIN_SALES_SCORE=70
```

Darwin will only send when all local gates pass: the prospect has a QA-passed draft, the score meets the threshold, the contact is a verified public generic role address on the business domain, the address is not suppressed or previously contacted, the daily cap has room, and sending is explicitly enabled.

To inspect without sending:

```bat
python -m backend.emailer
```

To send eligible messages manually through the same guardrails:

```bat
python -m backend.emailer --send-ready --limit 1
```

To suppress an address after an opt-out:

```bat
python -m backend.emailer --suppress info@example.com --reason "opt out"
```

## Target markets

Optional environment variables can override the defaults:

```text
DARWIN_MARKETS=Stockholm, Sweden;Gothenburg, Sweden;Oslo, Norway
DARWIN_CATEGORIES=plumbers,electricians,roofers
```

## Tests

Run local guardrail tests with:

```bat
python -m unittest discover -s tests -v
```

## Remaining production connections

The outbound sales path is implemented. The next production milestones are:

1. hosted deployment so workdays run without a local PC,
2. email delivery/bounce webhooks on a public endpoint,
3. Stripe hosted payment flow plus verified payment webhooks,
4. verified revenue/profit ledger and paid-audit delivery.

## Safety rules

- Never commit secrets, API keys, private keys, seed phrases, or customer credentials.
- Agents may not self-report revenue as fact; revenue must come from verified payment/accounting sources.
- No guessed personal emails, data-broker contacts, mass blasting, or automatic cold follow-up chains.
- External sends are permissioned, capped, QA-gated, and logged.
- Failed sends are held for review rather than automatically retried.
- Cash spending remains disabled unless a separate owner-controlled permission system is added.
- Dashboard/status rendering must not trigger model calls.

## Local setup

1. Copy `.env.example` to `.env` if needed.
2. Add your OpenAI API key to the local `.env` file.
3. Install dependencies with `python -m pip install -r requirements.txt`.
4. Configure the Resend variables above if you want real controlled outreach.
5. Run `python -m backend.workday --hours 6`.

### Moonshot / Solana market data note

Moonshot's legacy public Data API at `api.moonshot.cc` is no longer treated as a runtime dependency. Raptor uses public Solana market data for discovery by default. Moonshot is a self-custodial Solana wallet and its swaps route on-chain through Jupiter; future live execution should use a secure local signer plus a supported on-chain/Jupiter path rather than scraping or automating the Moonshot app UI. The exact proprietary Moonshot in-app trending/listing feed is not assumed to be publicly reproducible.
