import tempfile
import unittest
from pathlib import Path

from backend.agents.website_studio import CollectionSpec, FAQItem, ProductCard, WebsiteBuildSpec
from backend.site_builder import render_site, validate_site
from backend.site_export import export_deployment_package


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
            collections=[
                CollectionSpec(
                    name="Infrared Saunas",
                    eyebrow="Warmth",
                    intro="Explore infrared sauna formats.",
                    items=[
                        ProductCard(
                            name="Example Sauna",
                            eyebrow="Infrared",
                            description="A representative sauna product.",
                            details=["Example size", "Example finish"],
                        )
                    ],
                ),
                CollectionSpec(
                    name="Ice Baths",
                    eyebrow="Cold immersion",
                    intro="Explore handcrafted cold immersion formats.",
                    items=[
                        ProductCard(
                            name="Example Ice Bath",
                            eyebrow="Cold immersion",
                            description="A representative cold immersion product.",
                            price_label="From £8,000",
                            details=["Example finish", "Quotation available"],
                        )
                    ],
                ),
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
            for page in ["index.html", "infrared-saunas.html", "ice-baths.html", "about.html", "faq.html", "contact.html", "privacy.html"]:
                self.assertTrue((output / page).exists())

            contact = (output / "contact.html").read_text(encoding="utf-8")
            app_js = (output / "assets" / "app.js").read_text(encoding="utf-8")
            robots = (output / "robots.txt").read_text(encoding="utf-8")

            self.assertIn('id="quote-form"', contact)
            self.assertIn('name="company_website"', contact)
            self.assertIn("privacy.html", contact)
            self.assertIn("/api/quote", app_js)
            self.assertIn("Disallow: /", robots)

    def test_export_creates_standalone_application(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            site = project / "site"
            render_site(self.sample_spec(), site)
            deploy = export_deployment_package(project, site)

            self.assertTrue((deploy / "app.py").exists())
            self.assertTrue((deploy / "Dockerfile").exists())
            self.assertTrue((deploy / "site" / "index.html").exists())
            self.assertIn("/api/quote", (deploy / "app.py").read_text(encoding="utf-8"))

    def test_staging_pages_are_noindex(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "site"
            render_site(self.sample_spec(), output)
            for page in ["index.html", "infrared-saunas.html", "ice-baths.html", "about.html", "faq.html", "contact.html", "privacy.html"]:
                text = (output / page).read_text(encoding="utf-8")
                self.assertIn('name="robots" content="noindex,nofollow"', text)


if __name__ == "__main__":
    unittest.main()
