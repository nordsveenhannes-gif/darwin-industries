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
- run the loop for a bounded multi-hour workday,
- persist pipeline, email, task, and work-session state in SQLite.

Cash spending remains disabled.

## Run a workday

After local setup:

```bat
python -m backend.workday --hours 6
```

Defaults:

- 6-hour bounded session
- one cycle per hour
- 42-model-call local guardrail
- 4 researched prospects per cycle
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
```

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
