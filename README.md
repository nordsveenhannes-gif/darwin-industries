# Darwin Industries

Darwin Industries is an experimental multi-agent company runtime designed to do bounded, auditable business work with persistent state.

## Current business loop

The current runtime can:

- plan and execute internal work,
- retry failed tasks and QA the result,
- research real businesses on the public web,
- score prospects,
- produce an evidence-based website audit draft,
- draft personalized outreach,
- run the loop for a bounded multi-hour workday,
- persist all pipeline state locally in SQLite.

External email sending and cash spending remain disabled until dedicated provider accounts and explicit permissions are connected.

## Run a workday

After local setup:

```bat
python -m backend.workday --hours 6
```

Defaults:

- 6-hour bounded session
- one cycle per hour
- 36-model-call local guardrail
- 4 researched prospects per cycle
- no email sending
- no cash spending

Stop safely at any time with Ctrl+C.

Useful zero-model-call views:

```bat
python -m backend.status
python -m backend.prospects
```

## Target markets

Optional environment variables can override the defaults:

```text
DARWIN_MARKETS=Stockholm, Sweden;Gothenburg, Sweden;Oslo, Norway
DARWIN_CATEGORIES=plumbers,electricians,roofers
```

## Remaining production connections

To turn prepared sales work into verified revenue, Darwin still needs:

1. a company email provider for controlled outbound/inbound email,
2. a payment provider/webhook for verified payment events,
3. cloud deployment so workdays run without a local PC.

Those integrations should preserve owner control, rate limits, audit logs, opt-out handling, and verified revenue accounting.

## Safety rules

- Never commit secrets, API keys, private keys, seed phrases, or customer credentials.
- Agents may not self-report revenue as fact; revenue must come from verified payment/accounting sources.
- Real-money actions require explicit limits and owner-controlled recovery/administration.
- External actions must be permissioned and logged.
- Dashboard/status rendering must not trigger model calls.

## Local setup

1. Copy `.env.example` to `.env`.
2. Add your own OpenAI API key to the local `.env` file.
3. Install dependencies with `python -m pip install -r requirements.txt`.
4. Run `python -m backend.workday --hours 6`.
