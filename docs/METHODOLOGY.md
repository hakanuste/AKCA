# AKÇA independent fixed-basket price index — methodology

## 1. Purpose and naming

AKÇA uses the TÜİK April 2022 item list as a fixed reference and researches monthly price changes using prices collected directly from vendors and service providers. The result is named the **AKÇA Independent Fixed-Basket Price Index**. It is not the official TÜFE and does not claim to reproduce TÜİK's methodology.

## 2. Reference data

- The data/reference/tuik_2022_items.csv file was created from the 2022 Madde Listesi sheet in the supplied AKÇA tracking workbook.
- All 409 distinct item codes are preserved as seven-character text strings.
- Historical prices are not used as an AKÇA base-price series. AKÇA's comparison history begins when its own observations begin.
- The workbook does not contain the official 2022 item weights. No weights have been fabricated. The index remains blocked until the official 2022 weight source, scope and item-code mapping are verified.
- A TÜİK item code is not necessarily identical to one unique brand, grade, package size or service definition.

## 3. Product matching and variants

A comparable product variant must be registered for each reference item. A variant key identifies the same brand/SKU, quality, package size and conditions across vendors. Different sizes or qualities must not be merged under one variant.

If a reference item has multiple variants, each variant requires a within-item weight and its supporting source. These weights remain unverified until the representative product mix and source have been checked. Active variant weights must sum to 100% for each item. An item without a defined representative mix is not included in the index.

## 4. Price observations

Each observation records period, item code, variant key, vendor, product description, region, sales channel, quantity, unit, product price, delivery fee, stock state, URL, timezone-aware timestamp, membership requirement and campaign terms.

- Only in-stock and purchasable products are eligible.
- Membership-only prices are excluded from the primary index.
- Campaign prices may be used only after their public conditions are recorded and the observation is reviewed.
- New observations start as pending and are excluded until approved.
- Observation date must fall within the declared YYYY-MM period.
- Source URLs must use HTTP or HTTPS.
- For each vendor and variant, only the latest approved observation in the month is used; repeat observations do not inflate seller count.
- Product price and delivery fee are stored separately. Product unit price is normalized; delivery is available for separate assessment.

## 5. Unit normalization

Supported conversions:
- Mass: g/gr/gram to kg; kg to kg
- Volume: ml to L; L/lt/litre to L
- Count: adet/ad/piece/pcs/unit to adet
- Length: m/metre to m
- Area: m² to m2
- Volume: m³ to m3
- Services: hour/saat to saat; service/servis to servis

Normalized product unit price equals product price divided by package quantity multiplied by the unit conversion factor. Delivery is not automatically added to product unit price. Unsupported units are rejected rather than guessed.

## 6. Vendor statistics

For each variant and month, the latest approved observations per distinct vendor determine:
- Minimum normalized product unit price
- Maximum normalized product unit price
- Arithmetic mean across vendors
- Median across vendors
- Distinct vendor count

Each variant requires at least three distinct vendors in both the current and immediately preceding calendar month. Missing months are not skipped. For example, October is never compared to August merely because September data is missing.

## 7. Monthly change and index

Variant monthly change:
(current month's mean normalized vendor price / immediately previous month's mean normalized vendor price - 1) × 100

Item monthly change uses verified within-item variant weights:
sum(variant monthly change × variant weight / 100)

AKÇA monthly price change:
sum(item monthly change × official 2022 item weight / 100)

For every calculation, all 409 item weights, each item's 100% variant weight total, both months' data coverage and minimum vendor count are checked. Missing items or weights are never silently removed. The index calculation is blocked and the coverage gap is reported.

For the first successfully calculated month, the immediately preceding month is explicitly rebased to 100. Later months chain only from the immediately preceding calculated month. The series does not jump over an uncalculated month.

## 8. Comparison with published indicators

TÜİK TÜFE, ENAG, İTO and other official or independent indicators may be shown separately as context. The AKÇA direct-vendor index must not be conflated with those series. Differences in scope, period, weighting and method must be stated.

## 9. Licensing, access and data quality

Every external provider must be assessed for source URL, access type, licence/terms, freshness and attribution requirements. Authenticated, paid or restricted sources must not be scraped without permission. No observation may be fabricated where data or access rights are unavailable.

## 10. Publication gate

A monthly index is marked calculated only when all weight, variant matching, vendor count, timestamp, stock/access and previous-month coverage checks pass. Otherwise the run is marked blocked and the missing evidence is listed. A partial figure must not be presented as a complete index.
