from pydantic import BaseModel, Field
from agents import Agent, WebSearchTool


class CustomerDiscovery(BaseModel):
    business_name: str
    website_url: str
    observed_issue: str
    evidence_urls: list[str]
    why_it_matters: str
    confidence: int = Field(ge=0, le=100)


DISCOVERY_INSTRUCTIONS = """
You are Oracle, research analyst at Darwin Industries, running a consented owner demo.

Inspect the supplied public business website and produce one careful, evidence-based observation
that could matter for lead generation or conversion.

Rules:
- Use the live public web.
- Prefer the supplied website itself.
- Do not invent technical defects, rankings, traffic, revenue, or customer behavior.
- Keep the observation modest and specific.
- Do not collect personal data.
- Do not contact anyone.
- evidence_urls must contain public pages that support the observation.
"""


def build_customer_discovery() -> Agent:
    return Agent(
        name="Oracle",
        instructions=DISCOVERY_INSTRUCTIONS,
        tools=[
            WebSearchTool(
                search_context_size="low",
                external_web_access=True,
            )
        ],
        output_type=CustomerDiscovery,
    )
