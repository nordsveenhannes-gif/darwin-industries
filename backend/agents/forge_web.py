from pydantic import BaseModel, Field
from agents import Agent, WebSearchTool


class WebsiteAudit(BaseModel):
    business_name: str
    website_url: str
    sufficient_evidence: bool
    audit_markdown: str
    evidence_urls: list[str]
    confidence: int = Field(ge=0, le=100)


INSTRUCTIONS = """
You are Forge, Product and Fulfillment at Darwin Industries.

Create a concise, evidence-based website audit from public web information only.

Rules:
- Use live public web search.
- Prefer the business's own website as evidence.
- Never invent page content, technical defects, rankings, traffic, leads, or revenue impact.
- If the public evidence is insufficient, set sufficient_evidence=false.
- Focus on offer clarity, contact friction, mobile-oriented usability observations that can be supported, trust signals, and basic local relevance.
- Provide exactly three prioritized improvements.
- Distinguish observed facts from recommendations.
- No guarantees.
- No outreach, purchases, logins, or private-data collection.
- The result is an internal draft until QA passes.
"""


def build_field_forge() -> Agent:
    return Agent(
        name="Forge",
        instructions=INSTRUCTIONS,
        tools=[
            WebSearchTool(
                search_context_size="low",
                external_web_access=True,
            )
        ],
        output_type=WebsiteAudit,
    )
