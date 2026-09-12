from backend.agents.website_studio import CollectionSpec, FAQItem, ProductCard, WebsiteBuildSpec


def fire_ice_reference_spec() -> WebsiteBuildSpec:
    """
    Conservative fallback for the consented Fire & Ice demo.

    Facts here are limited to information published on the customer's public source site.
    The live Forge agent remains the preferred path; this exists so the demo can still render
    a truthful staging build if live web/model research is temporarily unavailable.
    """
    return WebsiteBuildSpec(
        brand_name="Fire & Ice Wellbeing",
        website_url="https://www.fireandicewellbeing.com/",
        positioning=(
            "Premium hot and cold wellbeing equipment with a quotation-led buying process, "
            "clear product choices and worldwide delivery calculated by order size and destination."
        ),
        hero_eyebrow="Fire / Ice / Wellbeing",
        hero_heading="A considered space for heat, cold and recovery.",
        hero_subheading=(
            "Explore premium infrared saunas and handcrafted UK-built ice baths, then request "
            "pricing for the configuration that suits your space."
        ),
        about_heading="Craftsmanship across heat and cold.",
        about_body=(
            "Fire & Ice Wellbeing offers infrared saunas alongside handcrafted ice baths, "
            "with product choices, materials and quotation details published for customers "
            "planning home or bespoke wellbeing spaces."
        ),
        trust_points=[
            "Infrared sauna options in Basswood, Eucalyptus and Eucalyptus/Cedar finishes",
            "UK-built ice baths in cedar and oak options",
            "Standard published lead time of six weeks",
            "Worldwide shipping with fees calculated by order size and destination",
        ],
        collections=[
            CollectionSpec(
                name="Infrared Saunas",
                eyebrow="Fire / Infrared",
                intro=(
                    "Two infrared sauna collections with different formats, finishes and sizes. "
                    "Sauna pricing is supplied by quotation."
                ),
                items=[
                    ProductCard(
                        name="Standard Full Spectrum Sauna",
                        eyebrow="Full spectrum",
                        description=(
                            "A full-spectrum infrared sauna format offered in Basswood and "
                            "Eucalyptus finishes."
                        ),
                        price_label="Pricing on request",
                        details=[
                            "1,293mm W × 1,166mm D × 1,974mm H, plus 51mm feet",
                            "Basswood or Eucalyptus Wood",
                            "Published standard lead time: 6 weeks",
                            "Worldwide shipping available",
                        ],
                    ),
                    ProductCard(
                        name="Premium 3 in 1 Sauna",
                        eyebrow="Premium infrared",
                        description=(
                            "A multi-size infrared sauna collection offered in Basswood, "
                            "Eucalyptus and Eucalyptus/Cedar finishes."
                        ),
                        price_label="Pricing on request",
                        details=[
                            "Medium, Large and Extra Large formats published",
                            "Basswood, Eucalyptus or Eucalyptus/Cedar",
                            "Published standard lead time: 6 weeks",
                            "Worldwide shipping available",
                        ],
                    ),
                ],
            ),
            CollectionSpec(
                name="Ice Baths",
                eyebrow="Ice / Cold immersion",
                intro=(
                    "Handcrafted ice baths built in the UK with cedar and oak finish options, "
                    "digital temperature control and a published cooling range down to 3°C."
                ),
                items=[
                    ProductCard(
                        name="Yellow Western Cedar Ice Bath",
                        eyebrow="Handcrafted in the UK",
                        description=(
                            "A timber ice bath option with stainless-steel banding choices and "
                            "published personalisation options."
                        ),
                        price_label="£8,000 inc. VAT",
                        details=[
                            "Published dimensions: 1,200mm W × 1,000mm H",
                            "Logo engraving, personalisation and size changes available by request",
                            "Published standard lead time: 6 weeks",
                        ],
                    ),
                    ProductCard(
                        name="Red Western Cedar Ice Bath",
                        eyebrow="Handcrafted in the UK",
                        description=(
                            "A cedar ice bath with the same quotation-led customisation and "
                            "delivery process."
                        ),
                        price_label="£8,500 inc. VAT",
                        details=[
                            "Published dimensions: 1,200mm W × 1,000mm H",
                            "Stainless Steel or Bronzed banding listed",
                            "Published standard lead time: 6 weeks",
                        ],
                    ),
                    ProductCard(
                        name="European Oak Ice Bath",
                        eyebrow="Handcrafted in the UK",
                        description=(
                            "An oak-finished ice bath option for customers seeking a different "
                            "material expression within the same cold-immersion system."
                        ),
                        price_label="From £9,000 inc. VAT",
                        details=[
                            "Published standard model price: £9,000 inc. VAT",
                            "Published rectangular model price: £9,250 inc. VAT",
                            "Published standard lead time: 6 weeks",
                        ],
                    ),
                ],
            ),
        ],
        faqs=[
            FAQItem(
                question="How are the infrared saunas priced?",
                answer="The source website states that sauna pricing is supplied on a quotation basis.",
            ),
            FAQItem(
                question="What is the standard lead time?",
                answer=(
                    "The source website publishes a standard lead time of six weeks for its "
                    "saunas and ice baths, while noting that it aims to beat that time."
                ),
            ),
            FAQItem(
                question="Do you ship internationally?",
                answer=(
                    "Yes. The source website states that Fire & Ice ships worldwide, with "
                    "shipping fees calculated according to order size and destination."
                ),
            ),
            FAQItem(
                question="Can an ice bath be customised?",
                answer=(
                    "The source website lists logo engraving, personalisation and size changes "
                    "as customisation options to specify with the order request."
                ),
            ),
            FAQItem(
                question="What materials are available for the ice baths?",
                answer=(
                    "Published options include Red Western Cedar, Yellow Western Cedar and Oak, "
                    "with Stainless Steel and Bronzed banding listed."
                ),
            ),
            FAQItem(
                question="What sauna finishes are available?",
                answer=(
                    "Published sauna finishes include Basswood, Eucalyptus Wood and, on the "
                    "Premium 3 in 1 range, Eucalyptus/Cedar."
                ),
            ),
        ],
        address_lines=[
            "71–75 Shelton Street",
            "Covent Garden, London",
            "WC2H 9JQ",
        ],
        customer_assets_needed=[
            "Final confirmation that existing website photography may be reused in production",
            "Final approved legal/privacy/cookie wording before public launch",
        ],
        evidence_urls=["https://www.fireandicewellbeing.com/"],
        unverified_claims=[],
    )
