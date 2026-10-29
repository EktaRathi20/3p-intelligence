# Multi-hazard intelligence contract

Region `hazardIds` describe hazards configured for a region. They do not mean
that an intelligence engine exists for those hazards. Implemented handlers are
registered independently in `services/hazard_intelligence.py`; cyclone is the
only registered engine.

`GET /api/disaster-intelligence/{region}?hazard=cyclone` resolves the region
and hazard before running an engine. A configured hazard without a handler
returns HTTP 200 with `status: "not_implemented"`; a known hazard not configured
for the region returns `status: "not_configured"`. Both responses include
`supported: false` and a user-facing `message`. Unknown regions return 404 and
unknown hazard values return 422, and missing regional inputs return 503.
Implemented cyclone responses retain their
existing assessment fields and add `hazard` and `supported: true`. Data-source
source failures return 502 and insufficient current evidence returns 503 rather
than a low-risk assessment.

`GET /api/disaster-intelligence/{region}/capabilities` lists the region's
configured hazard IDs, the globally implemented handler IDs, status for each
known hazard type, and historical-source coverage.

`GET /api/history?region={region}` returns all records from the integrated
historical sources. `hazard` is an optional filter using a known hazard ID,
code, or name. Each record includes `hazard_type`. At present the only
historical source is NOAA IBTrACS North Indian Ocean cyclone tracks; the
response reports `available_hazards: ["cyclone"]` and
`history_coverage.complete: false`. `available_hazards` lists hazard types
with an integrated history source; `hazards_with_records` lists types actually
present in that region's returned source records. Other hazards are not
inferred from cyclone data, and an empty result is not evidence that no
disaster occurred.

Population, forecast, current-conditions, and shelter routes remain independent
of region hazard configuration.
