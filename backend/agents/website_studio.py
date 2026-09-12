from pydantic import BaseModel, Field
from agents import Agent, WebSearchTool


class ProductCard(BaseModel):
    name: str
    eyebrow: str = ""
    description: str
    price_label: str = "Pricing on request"
    details: list[str] = Field(default_factory=list)


class CollectionSpec(BaseModel):
    name: str
    eyebrow: str
    intro: str
    items: list[ProductCard] = Field(default_factory=list)


class FAQItem(BaseModel):
    question: str
    answer: str


class WebsiteBuildSpec(BaseModel):
    brand_name: str
    website_url: str
    positioning: str
    hero_eyebrow: str
    hero_heading: str
    hero_subheading: str
    about_heading: str
    about_body: str
    trust_points: list[str]
    collections: list[CollectionSpec] = Field(min_length=2, max_length=2)
    faqs: list[FAQItem]
    address_lines: list[str] = Field(default_factory=list)
    contact_email: str | None = None
    contact_phone: str | None = None
    customer_assets_needed: list[str] = Field(default_factory=list)
    evidence_urls: list[str]
    unverified_claims: list[str] = Field(default_factory=list)


class UXReview(BaseModel):
    approved: bool
    score: int = Field(ge=0, le=100)
    strengths: list[str]
    required_changes: list[str]
    conversion_notes: list[str]


FORGE_INSTRUCTIONS = """
You are Forge, senior web strategist and fulfillment lead at Darwin Industries.

Create the content and information architecture for a premium, conversion-oriented small-business
website rebuild. Use the supplied public business website as the primary factual source.

Rules:
- Use live public web search and prefer the supplied first-party website.
- Preserve factual product/service names, dimensions, prices, lead times, materials, addresses and
  policies only when you can support them from the public site.
- Never invent testimonials, certifications, customer counts, medical claims, performance claims,
  awards, guarantees, phone numbers, email addresses, or business facts.
- Health/wellness claims must be phrased conservatively and must not be strengthened beyond the source.
- If something cannot be verified, put it in unverified_claims or customer_assets_needed instead of
  presenting it as fact.
- Return exactly two primary product/service collections. Each collection should represent a useful
  customer navigation path and may contain representative product/service cards.
- The website is lead-generation first: clear navigation, concise premium copy, strong enquiry CTAs,
  mobile readability, useful FAQs and transparent buying information.
- Return 2-4 representative cards per collection when supported.
- Return 4-8 useful FAQs based on public facts.
- Keep copy polished and restrained. Avoid AI clichés, fake luxury language, excessive adjectives,
  exclamation marks, countdowns, scarcity or fake urgency.
- Do not contact anyone, create accounts, spend money, or publish anything.
"""


NOVA_INSTRUCTIONS = """
You are Nova, conversion and UX reviewer at Darwin Industries.

Review a proposed premium website build specification for a real client-quality staging site.
Score it for clarity, hierarchy, credibility, mobile scannability, lead-generation flow and trust.

Flag:
- vague generic copy,
- unsupported claims,
- poor CTA hierarchy,
- missing pricing/process transparency,
- weak information scent,
- excessive text,
- anything that could make the business look scammy.

Do not invent business facts. required_changes must be concrete and limited to the most important
fixes. approved=true only when the specification is strong enough for a professional staging build.
"""


def build_website_forge() -> Agent:
    return Agent(
        name="Forge",
        instructions=FORGE_INSTRUCTIONS,
        tools=[WebSearchTool(search_context_size="medium", external_web_access=True)],
        output_type=WebsiteBuildSpec,
    )


def build_website_nova() -> Agent:
    return Agent(
        name="Nova",
        instructions=NOVA_INSTRUCTIONS,
        output_type=UXReview,
    )
