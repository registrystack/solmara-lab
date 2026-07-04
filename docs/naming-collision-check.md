# Naming Collision Check

Status: normative record for Solmara Lab wave 1 naming.

Date checked: 2026-07-04.

## Final Names

| Code | Type | Name |
|---|---|---|
| `XS-01` | Province | Anvela |
| `XS-0101` | District | Ketterin |
| `XS-0102` | District | Ovasse |
| `XS-0103` | District | Brenholm |
| `XS-02` | Province | Tolara |
| `XS-0201` | District | Salvet |
| `XS-0202` | District | Marindi |
| `XS-0203` | District | Velcor |
| `XS-03` | Province | Mendira |
| `XS-0301` | District | Lydessa |
| `XS-0302` | District | Orivale |
| `XS-0303` | District | Carrowen |
| `XS-04` | Province | Corvala |
| `XS-0401` | District | Eastmere |
| `XS-0402` | District | Navaro |
| `XS-0403` | District | Vestrel |

## Check Method

The collision check used three public discovery routes:

1. Web search for exact quoted names alone and exact quoted names with
   `province`, `district`, `city`, and `government`.
2. OpenStreetMap Nominatim, because it searches OpenStreetMap place and address
   data.
3. GeoNames and NGA GEOnet Names Server documentation as target gazetteer
   sources for future scripted checks.

Sources used to define the check surface:

- GeoNames describes its database as covering all countries and containing more
  than eleven million placenames: https://www.geonames.org/
- Nominatim describes itself as OpenStreetMap-based geocoding for name and
  address lookup: https://nominatim.org/
- NGA GEOnet Names Server describes itself as a geographic names database for
  public and U.S. Government use: https://geonames.nga.mil/

## Results

No exact match was found that appears to be a real first-order or second-order
administrative division for the full final list. Some names have non-blocking
generic, personal, address, or product-like search hits:

| Name | Observed non-blocking hits |
|---|---|
| Tolara | Appears in Italian street or address contexts and unrelated web content. Not found as a government province or district. |
| Navaro | Similar to surnames, brands, and variants of Navarro. Not found as a government district with exact spelling. |
| Eastmere | English-like compound and possible fictional or local usage. Not found as a government district in this exact Solmara context. |

The search performed here is not a legal trademark clearance. It is a practical
geography and narrative collision check for a fictional demo country. If the lab
later exposes these names in marketing material, repeat the check with a formal
trademark search in the target jurisdictions.
