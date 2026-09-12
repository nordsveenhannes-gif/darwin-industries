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


class ClientClarificationQuestion(BaseModel):
    key: str
    question: str
    why_needed: str
    required_for: str = Field(pattern="^(STAGING|LAUNCH)$")


class ClarificationPlan(BaseModel):
    staging_can_continue: bool
    safe_omissions: list[str] = Field(default_factory=list)
    questions: list[ClientClarificationQuestion] = Field(default_factory=list, max_length=5)


CLARIFIER_INSTRUCTIONS = """
You are Mercury and Sentinel working together as a client clarification planner for Darwin Industries.

A website project has been researched and reviewed. Decide whether unresolved issues actually require
the client before a PRIVATE STAGING build can continue.

Rules:
- Separate STAGING blockers from LAUNCH blockers.
- Staging blockers are only decisions/facts that materially change information architecture, visual direction,
  core functionality, or customer-facing claims that cannot safely be omitted.
- Final legal wording, cookie configuration, analytics, domain/hosting credentials, production form routing,
  final warranty/returns text, final payment verification, and production asset licensing are normally LAUNCH
  dependencies, not reasons to stop a private noindex staging build.
- If a disputed or unsupported fact can simply be omitted from staging, put it in safe_omissions rather than
  asking the client.
- Ask no more than 5 concise questions.
- Never ask for passwords, private keys, API keys, payment card data, or secrets.
- Use unique machine-friendly question keys.
- staging_can_continue=true if remaining issues can safely be omitted or deferred to launch.
"""


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
- missing pricing/process transparency when that information is necessary for the staging user journey,
- weak information scent,
- excessive text,
- anything that could make the business look scammy.

Important staging distinction:
- Review the private staging experience, not final launch compliance.
- Do NOT reject staging merely because final legal copy, warranty wording, cookie settings, analytics,
  production hosting, domain access, final CRM routing, or other launch-only dependencies are pending.
- If a commercial fact is uncertain, it is acceptable for staging to omit it or mark it for client confirmation
  rather than inventing it.
- required_changes should contain only changes needed to make the private staging build professionally reviewable.
- Put launch-only dependencies in conversion_notes instead of using them to force approved=false.

Do not invent business facts. required_changes must be concrete and limited to the most important
staging fixes. approved=true when the specification is strong enough for a professional private staging review.
"""


def build_website_clarifier() -> Agent:
    return Agent(
        name="Mercury",
        instructions=CLARIFIER_INSTRUCTIONS,
        output_type=ClarificationPlan,
    )


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
