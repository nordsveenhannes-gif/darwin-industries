# Darwin Industries

Darwin Industries is an experimental multi-agent company runtime.

## Current milestone

Build the first real Atlas runtime locally, then add persistent state, workers, email, verified revenue, and only later controlled treasury access.

## Safety rules

- Never commit secrets, API keys, private keys, seed phrases, or customer credentials.
- Agents may not self-report revenue as fact; revenue must come from verified payment/accounting sources.
- Real-money actions require explicit limits and owner-controlled recovery/administration.
- Dashboard rendering must not trigger model calls.

## Local setup

1. Copy `.env.example` to `.env`.
2. Add your own OpenAI API key to the local `.env` file.
3. Install dependencies with `python -m pip install -r requirements.txt`.
4. Start with `python -m backend.main`.

