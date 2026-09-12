import tempfile
import unittest
from pathlib import Path

from backend.agents.website_studio import FAQItem, ProductCard, WebsiteBuildSpec
from backend.site_builder import REQUIRED_PAGES, render_site, validate_site


class WebsiteBuilderTests(unittest.TestCase):
    def sample_spec(self):
        return WebsiteBuildSpec(
            brand_name="Fire & Ice Test",
            website_url="https://example.com",
            positioning="Premium hot and cold equipment with transparent quotations.",
            hero_eyebrow="Private wellbeing",
            hero_heading="Heat. Cold. Built beautifully.",
            hero_subheading="A premium home wellbeing collection.",
            about_heading="Built around quality and clarity.",
            about_body="A concise, factual description of the business.",
            trust_points=[
                "Quotation-led buying process",
                "Clear product information",
                "Responsive customer support",
            ],
            sauna_intro="Explore infrared sauna formats.",
            ice_bath_intro="Explore handcrafted cold immersion formats.",
            saunas=[
                ProductCard(
                    name="Example Sauna",
                    eyebrow="Infrared",
                    description="A representative sauna product.",
                    details=["Example size", "Example finish"],
                )
            ],
            ice_baths=[
                ProductCard(
                    name="Example Ice Bath",
                    eyebrow="Cold immersion",
                    description="A representative cold immersion product.",
                    price_label="From £8,000",
                    details=["Example finish", "Quotation available"],
                )
            ],
            faqs=[
                FAQItem(question="How do I get pricing?", answer="Submit a project enquiry.")
            ],
            address_lines=["1 Example Street", "London"],
            customer_assets_needed=["Approved photography"],
            evidence_urls=["https://example.com"],
        )

    def test_renders_complete_functional_staging_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "site"
            render_site(self.sample_spec(), output)

            self.assertEqual(validate_site(output), [])
            for page in REQUIRED_PAGES:
                self.assertTrue((output / page).exists())

            contact = (output / "contact.html").read_text(encoding="utf-8")
            app_js = (output / "assets" / "app.js").read_text(encoding="utf-8")
            robots = (output / "robots.txt").read_text(encoding="utf-8")

            self.assertIn('id="quote-form"', contact)
            self.assertIn("/api/quote", app_js)
            self.assertIn("Disallow: /", robots)

    def test_staging_pages_are_noindex(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "site"
            render_site(self.sample_spec(), output)
            for page in REQUIRED_PAGES:
                text = (output / page).read_text(encoding="utf-8")
                self.assertIn('name="robots" content="noindex,nofollow"', text)


if __name__ == "__main__":
    unittest.main()
