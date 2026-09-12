from pydantic import BaseModel, Field
from agents import Agent, WebSearchTool


class PublicBusinessContact(BaseModel):
    prospect_id: int
    eligible: bool
    email: str | None = None
    source_url: str | None = None
    rationale: str
    confidence: int = Field(ge=0, le=100)


CONTACT_FINDER_INSTRUCTIONS = """
You are Oracle's contact-verification specialist at Darwin Industries.

Your job is READ-ONLY public web research for one already-qualified business prospect.

Rules:
- Use the business's official public website as the source whenever possible.
- Return only a generic business/role email that is explicitly published, such as info@, contact@, hello@, office@, sales@, reception@, booking@, service@, or local-language equivalents.
- Never return a named person's address, personal mailbox, private contact detail, scraped data-broker address, or an email guessed from a naming pattern.
- Never infer an email that is not visibly supported by a public source.
- The email domain must belong to the business/official website.
- If the site exposes only a contact form, phone number, social profile, or a named person's email, set eligible=false.
- Do not contact anyone, submit forms, log in, or buy anything.
- source_url should be the public page that supports the email.
- confidence reflects confidence that the email is a real, generic business contact for this exact prospect.
"""


def build_contact_finder() -> Agent:
    return Agent(
        name="Oracle Contact Verifier",
        instructions=CONTACT_FINDER_INSTRUCTIONS,
        tools=[
            WebSearchTool(
                search_context_size="low",
                external_web_access=True,
            )
        ],
        output_type=PublicBusinessContact,
    )
