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


## Website Studio — accepted quotation to staging site

Darwin has a post-sale website fulfillment path that is separate from the audit/outreach demo.

For the Fire & Ice fake-customer run on Windows, pull the latest repo and launch:

```bat
run_fire_ice_demo.bat
```

The launcher starts Mission Control in a second CMD, opens the dashboard, simulates an accepted quotation, lets the agents research/review/QA the project, builds the staging website, validates it, and opens the finished preview in the default browser. Demo mode never records payment or revenue.

The direct command is:

```bat
python -m backend.website_job --demo --business-name "Fire & Ice Wellbeing" --website "https://www.fireandicewellbeing.com/"
```

Website Studio currently:
- creates a fixed-scope quotation with deposit, revision, exclusion and ownership terms,
- opens a browser-based client discovery questionnaire before design (goal, audience, CTA, brand direction, functionality, commercial facts, staging asset permission, approver/deadline),
- checks the accepted quote against the client's answers and pauses for a change order instead of silently doing unquoted work,
- records launch-only questions separately so privacy/cookies, domain access, production routing and SEO migration do not block a safe private staging build,
- has Forge research the first-party customer site and create a factual structured build specification,
- has Nova review the private staging UX, then re-review the revised specification instead of carrying forward a rejected first-pass score,
- has Sentinel perform staging-specific QA rather than demanding production/legal completion too early,
- gives Forge one bounded self-repair when QA finds a genuine staging issue,
- if research/QA still finds something it should not guess, opens a targeted client follow-up questionnaire and automatically continues when the client answers,
- builds a client-specific premium design system (palette/typography direction) instead of using the exact same theme for every business,
- builds responsive core pages plus staging privacy and branded 404 pages,
- reuses suitable source-site imagery in demo mode on a best-effort basis while keeping production asset-rights confirmation separate,
- validates generated pages, internal links, form wiring, favicon, staging noindex and required assets,
- provides a functional enquiry form with validation, acknowledgement, a spam honeypot, rate limiting and baseline security headers,
- exports a standalone runnable Python website app and Dockerfile,
- supports two included revision rounds and explicit staging approval,
- keeps staging approval separate from production launch authorization,
- records a launch questionnaire for legal identity, production form routing, asset rights, privacy/cookies, SEO migration/analytics and owner-controlled hosting/domain access,
- can create a separate production release package only after real launch gates pass; the release copy removes staging noindex, adds canonical URLs, robots/sitemap and preserves the branded 404 page.


Generated project files are written under `builds/<business>-<project-id>/` and are gitignored. Each project contains the quote, build spec, UX review, QA report, customer handoff checklist, staging site and standalone deploy package.

The local staging server is intentionally not a public deployment. Darwin must not replace a customer's live site until staging is approved, real payment requirements are satisfied, asset rights are confirmed, and a customer-controlled production hosting/domain target is configured securely. Never ask a customer to email passwords, private keys or seed phrases.

Mission Control:

```bat
python -m backend.dashboard
```

Open `http://127.0.0.1:8765`.

### Website revisions and customer approval

Apply one of the two included customer revision rounds with:

```bat
python -m backend.website_revision --project-id 1 --feedback "Make the first product page more concise and move delivery details higher." --serve
```

Darwin preserves the current staging build if QA fails and refuses a silent third included revision; work beyond the quoted two rounds should become an explicit change order.

When the customer approves the current staging build:

```bat
python -m backend.website_approval --project-id 1 --approve-staging
```

Approval records the customer decision but does **not** publish the site. For a real commercial project, launch remains gated by verified payment, confirmed asset rights, explicit staging approval and a customer-controlled production target.

In demo mode Darwin may reuse image assets already published on the source website to make the staging preview realistic. That demo reuse is not production rights confirmation. For a real customer, use `--confirm-asset-rights` only after the customer has explicitly confirmed they control or license those assets.


Launch-only customer questions can be collected later with:

```bat
python -m backend.website_launch_intake --project-id 1
```

Staging approval and public launch approval are separate commands. A production release package can only be created after the real commercial gates are complete:

```bat
python -m backend.website_launch_approval --project-id 1 --approve-launch
python -m backend.website_release --project-id 1 --domain "https://www.example.com"
```

Neither command changes DNS or publishes a customer's domain by itself.


### Current website offer and delivery

Default website offer:
- **$179 one-time build**
- **$39/month hosting & care after launch**
- monthly care includes hosting, SSL, backups, uptime monitoring, and one small content/update request per month (roughly 30 minutes)
- larger changes require a separate quote before work begins
- customer retains domain control and can take the website files if they cancel care

The client onboarding brief now asks for the email address where Darwin should deliver the finished proposal. It also allows categorized image uploads for:
- logo / brand mark,
- homepage hero,
- products/services,
- about/team/location.

Client-uploaded images take priority. If no client images are supplied, Darwin uses at most one conservative first-party hero candidate and does not guess which scraped image belongs to which product card.

When staging is ready, Mercury automatically sends the proposal email through the configured Resend account. Demo mode includes the local staging URL. A real customer email uses DARWIN_PUBLIC_STAGING_URL when a public/private staging deployment has been configured; otherwise it sends the commercial proposal without pretending the localhost URL is accessible to the customer.

Mission Control highlights WORKING and WAITING agents, shows their current action, and gives each agent a lightweight character/persona so active work is easier to read at a glance.
