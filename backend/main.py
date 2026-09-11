import os
from dotenv import load_dotenv
from agents import Runner

from backend.agents.atlas import build_atlas


def main() -> None:
    load_dotenv()

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is missing. Copy .env.example to .env and add your key locally."
        )

    atlas = build_atlas()
    prompt = (
        "Darwin Industries is starting from zero. "
        "Choose one realistic digital service we can validate within 48 hours "
        "with minimal upfront cost and no financial transactions."
    )

    result = Runner.run_sync(atlas, prompt)
    print("\n=== ATLAS DECISION MEMO ===\n")
    print(result.final_output)


if __name__ == "__main__":
    main()
