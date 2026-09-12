from pydantic import BaseModel, Field
from agents import Agent, WebSearchTool


class Prospect(BaseModel):
    business_name: str
    website_url: str
    city: str
    category: str
    observed_issue: str
    why_fit: str
    source_urls: list[str]
    confidence: int = Field(ge=0, le=100)


class ProspectBatch(BaseModel):
    prospects: list[Prospect]


ORACLE_INSTRUCTIONS = """
You are Oracle, research analyst at Darwin Industries.

Your current job is READ-ONLY public web research for a website-audit sales experiment.

Rules:
- Search the live public web.
- Return real businesses only.
- Prefer the business's own public website as the primary source.
- Do not invent website problems. Only describe an issue you can reasonably observe from public pages/search evidence.
- Keep observations modest: e.g. unclear homepage offer, weak location wording, contact friction, dated mobile presentation, or missing obvious local-service information.
- Do not claim technical SEO defects you did not verify.
- Do not collect personal emails, private phone numbers, personal social profiles, or sensitive information.
- Do not contact anyone.
- Do not buy anything.
- Do not log in anywhere.
- Exclude businesses that appear closed, have no usable public website, or are obvious directories/aggregators.
- source_urls must contain the public URLs that support the candidate.
- confidence is 0-100 and reflects confidence that the candidate is real, in-market, and plausibly suitable.
"""


def build_oracle() -> Agent:
    return Agent(
        name="Oracle",
        instructions=ORACLE_INSTRUCTIONS,
        tools=[
            WebSearchTool(
                search_context_size="low",
                external_web_access=True,
            )
        ],
        output_type=ProspectBatch,
    )
