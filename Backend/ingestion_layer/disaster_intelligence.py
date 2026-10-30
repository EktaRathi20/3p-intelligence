import json
from datetime import datetime, timezone
from fastapi import HTTPException
from ingestion_layer import hazard_model
from ingestion_layer.constant import REGION_DATA
from ingestion_layer.index import run_ingestion
from ingestion_layer.signals import (
    build_model_features,
    classify_local_cyclone_impact,
    combine_levels,
    score_to_level,
    screen_risk,
    summarize_active_systems,
    summarize_warning_lines,
    warning_floor_level,
)
from services.meta_client import MetaClientError

async def build_disaster_intelligence(region: str, client):
    """
    Unified disaster-intelligence endpoint.

    Architecture:
        Real ingestion
            ↓
        Data normalization
            ↓
        Deterministic risk screening
            ↓
        H2O AutoML severity probability (when a trained model exists)
            ↓
        Meta Llama contextual interpretation
            ↓
        Final response

    IMPORTANT:
    Meta does not create measurements, coordinates, historical events,
    insurance payouts, or hazard observations.
    """

    region_key = region.strip().lower()

    # ---------------------------------------------------------
    # 1. RUN REAL DATA INGESTION
    # ---------------------------------------------------------
    ingestion_error = None

    try:
        unified_data = run_ingestion(region_key)

        if not isinstance(unified_data, dict):
            raise RuntimeError(
                "run_ingestion() returned an invalid response."
            )

    except Exception as error:
        ingestion_error = str(error)

        print(
            f"[DISASTER INTELLIGENCE] "
            f"Ingestion failed for '{region_key}': {error}"
        )

        # IMPORTANT:
        # Do NOT manufacture weather values here.
        #
        # We only return metadata and clearly mark the telemetry
        # as unavailable.
        fallback_region = REGION_DATA.get(region_key)

        if not fallback_region:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown region: {region_key}"
            )

        unified_data = {
            "region_metadata": fallback_region,

            "meteorological_telemetry": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "region_target": region_key,
                "system_name": "Live telemetry unavailable",
                "alert_status": "DATA_UNAVAILABLE",
                "metrics": {
                    "wind_speed_kmh": None,
                    "peak_wind_kmh": None,
                    "pressure_hpa": None,
                    "central_pressure_hpa": None,
                    "storm_surge_meters": None,
                },
                "trajectory": None,
            },

            "demography": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "region_target": region_key,
                "total_population": None,
            },

            "places": {
                "hospitals": [],
                "shelters": [],
                "source_errors": {
                    "ingestion": ingestion_error
                },
            },

            "history": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "region_target": region_key,
                "historical_analogs": [],
            },

            "forecast": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "region_target": region_key,
                "forecast": [],
            },
        }

    # ---------------------------------------------------------
    # 2. NORMALIZE TELEMETRY
    # ---------------------------------------------------------

    telemetry = (
        unified_data.get("meteorological_telemetry")
        or unified_data.get("current_condition")
        or {}
    )

    if not isinstance(telemetry, dict):
        telemetry = {}

    metrics = telemetry.get("metrics")

    if not isinstance(metrics, dict):
        metrics = {}

    def first_value(*values):
        """
        Return the first value that is actually present.

        Unlike `or`, this does not accidentally replace valid
        values such as 0.
        """
        for value in values:
            if value is not None:
                return value
        return None

    def safe_float(value):
        try:
            if value is None:
                return None

            return float(value)

        except (TypeError, ValueError):
            return None

    wind = first_value(
        telemetry.get("wind_speed_kmh"),
        metrics.get("wind_speed_kmh"),
        metrics.get("peak_wind_kmh"),
    )

    pressure = first_value(
        telemetry.get("pressure_hpa"),
        metrics.get("pressure_hpa"),
        metrics.get("central_pressure_hpa"),
    )

    storm_surge = first_value(
        telemetry.get("storm_surge_meters"),
        metrics.get("storm_surge_meters"),
    )

    wind = safe_float(wind)
    pressure = safe_float(pressure)
    storm_surge = safe_float(storm_surge)

    marine = unified_data.get("marine")

    if not isinstance(marine, dict):
        marine = {}

    wave_height = safe_float(marine.get("wave_height_m"))

    active_block = unified_data.get("active_systems")

    if not isinstance(active_block, dict):
        active_block = {}

    active_systems = active_block.get("systems", [])

    if not isinstance(active_systems, list):
        active_systems = []

    warnings_block = unified_data.get("warnings")

    if not isinstance(warnings_block, dict):
        warnings_block = {}

    official_warnings = warnings_block.get("warnings", [])

    if not isinstance(official_warnings, list):
        official_warnings = []

    local_impact = warnings_block.get("local_impact", {})

    if not isinstance(local_impact, dict):
        local_impact = {}

    inactive_warnings = warnings_block.get("inactive_warnings", [])

    if not isinstance(inactive_warnings, list):
        inactive_warnings = []

    warnings_source = warnings_block.get("source")
    warnings_timestamp = warnings_block.get("timestamp")
    warnings_error = warnings_block.get("source_error")

    # ---------------------------------------------------------
    # 3. DETERMINE DATA PROVENANCE
    # ---------------------------------------------------------

    telemetry_timestamp = (
        telemetry.get("timestamp")
        or telemetry.get("observed_at")
        or telemetry.get("updated_at")
    )

    telemetry_status = (
        telemetry.get("alert_status")
        or telemetry.get("status")
        or "UNKNOWN"
    )

    system_name = telemetry.get(
        "system_name",
        "Meteorological telemetry"
    )

    source_errors = {}
    for source_name, source_block in (
        ("marine", marine),
        ("active_systems", active_block),
        ("warnings", warnings_block),
        ("forecast", unified_data.get("forecast") or unified_data.get("forcast")),
    ):
        if not isinstance(source_block, dict):
            continue
        source_error = source_block.get("source_error")
        nested_errors = source_block.get("source_errors")
        if isinstance(nested_errors, dict):
            source_error = source_error or nested_errors.get("ingestion")
        if source_error:
            source_errors[source_name] = str(source_error)

    if ingestion_error:
        telemetry_data_status = "UNAVAILABLE"

    elif (
        wind is not None
        or pressure is not None
        or storm_surge is not None
        or wave_height is not None
    ):
        telemetry_data_status = "AVAILABLE"

    else:
        telemetry_data_status = "NO_CURRENT_MEASUREMENTS"

    # ---------------------------------------------------------
    # 4. HISTORICAL ANALOGS
    # ---------------------------------------------------------

    history = unified_data.get("history")

    if not isinstance(history, dict):
        history = unified_data.get("disaster_history", {})

    if not isinstance(history, dict):
        history = {}

    historical_analogs = history.get(
        "historical_analogs",
        []
    )

    if not isinstance(historical_analogs, list):
        historical_analogs = []

    # Never invent a historical event.
    #
    # Only accept an analog that actually came from the ingestion
    # layer.
    valid_analogs = []

    for analog in historical_analogs:
        if not isinstance(analog, dict):
            continue

        name = (
            analog.get("matched_cyclone")
            or analog.get("event_name")
            or analog.get("name")
            or analog.get("title")
        )

        if name:
            valid_analogs.append(analog)

    primary_analog = None

    if valid_analogs:
        primary_analog = (
            valid_analogs[0].get("matched_cyclone")
            or valid_analogs[0].get("event_name")
            or valid_analogs[0].get("name")
            or valid_analogs[0].get("title")
        )

    # ---------------------------------------------------------
    # 5. FORECAST
    # ---------------------------------------------------------

    forecast = unified_data.get("forecast")

    if not isinstance(forecast, dict):
        # Backward compatibility with your previous typo.
        forecast = unified_data.get("forcast", {})

    if not isinstance(forecast, dict):
        forecast = {}

    forecast_items = forecast.get("forecast", [])

    if not isinstance(forecast_items, list):
        forecast_items = []

    # ---------------------------------------------------------
    # 6. REGION METADATA
    # ---------------------------------------------------------

    region_meta = unified_data.get(
        "region_metadata"
    ) or REGION_DATA.get(region_key, {})

    if not isinstance(region_meta, dict):
        region_meta = {}

    min_lat = safe_float(region_meta.get("min_lat"))
    max_lat = safe_float(region_meta.get("max_lat"))
    min_lon = safe_float(region_meta.get("min_lon"))
    max_lon = safe_float(region_meta.get("max_lon"))

    center_lat = None
    center_lon = None

    if (
        min_lat is not None
        and max_lat is not None
    ):
        center_lat = (min_lat + max_lat) / 2

    if (
        min_lon is not None
        and max_lon is not None
    ):
        center_lon = (min_lon + max_lon) / 2

    # ---------------------------------------------------------
    # 7. DETERMINISTIC RISK SCREENING
    # ---------------------------------------------------------
    #
    # This is deliberately NOT an official evacuation model.
    #
    # Screening bands are documented in ingestion_layer.constant:
    # IMD cyclone-scale winds, screening pressure bands, and WMO
    # sea-state wave bands.
    #
    # IMPORTANT:
    # Missing data does NOT become zero. Active-system evidence is
    # reported as factors but adds no score points, because IBTrACS
    # fixes are provisional with weeks-scale latency.
    # ---------------------------------------------------------

    risk_score, risk_factors = screen_risk(
        wind=wind,
        pressure=pressure,
        wave_height_m=wave_height,
    )

    risk_factors.extend(summarize_active_systems(active_systems))
    risk_factors.extend(summarize_warning_lines(official_warnings))
    if official_warnings:
        verdict = local_impact.get("verdict", "uncertain")
        for line in local_impact.get("basis", []):
            risk_factors.append(f"Local impact ({verdict}): {line}")

    # ---------------------------------------------------------
    # 7.5 H2O AUTOML SEVERITY PROBABILITY
    # ---------------------------------------------------------
    #
    # Scores P(same-storm winds >= 118 km/h within 24h) from a model
    # trained on real IBTrACS fixes. Features come ONLY from measured
    # values; anything missing (or no trained model file) reports
    # UNAVAILABLE instead of a fabricated number.
    # ---------------------------------------------------------

    ml_probability = {
        "status": "UNAVAILABLE",
        "probability": None,
        "model_id": None,
        "features_used": None,
        "label": hazard_model.LABEL_DESCRIPTION,
        "reason": None,
        "note": (
            "Screening probability only; not an official warning or "
            "evacuation order."
        ),
    }

    if telemetry_data_status == "AVAILABLE":
        features = build_model_features(
            latitude=center_lat,
            longitude=center_lon,
            wind_speed_kmh=wind,
            pressure_hpa=pressure,
        )
        if features is None:
            ml_probability["reason"] = (
                "Insufficient features: wind and pressure observations "
                "are both required."
            )
        else:
            scored = hazard_model.score(features)
            if scored is None:
                ml_probability["reason"] = (
                    "Model unavailable: set H2O_MODEL_PATH to a trained "
                    "model file (see Backend/scripts/train_risk_model.py)."
                )
            else:
                ml_probability.update({
                    "status": "SCORED",
                    "probability": scored["probability"],
                    "model_id": scored["model_id"],
                    "features_used": scored["features_used"],
                    "reason": None,
                })
                risk_factors.append(
                    "H2O severity probability: "
                    f"{scored['probability']:.2f} "
                    f"({hazard_model.LABEL_DESCRIPTION})"
                )
    else:
        ml_probability["reason"] = (
            f"No current measurements (telemetry status: "
            f"{telemetry_data_status})."
        )

    # ---------------------------------------------------------
    # 8. RISK LEVEL
    # ---------------------------------------------------------

    if telemetry_data_status != "AVAILABLE":
        screening_level = "UNKNOWN"

    else:
        screening_level = score_to_level(risk_score)

    # Official warnings set a severity floor: a verified warning can only
    # raise the reported level, never lower it. A missing active-system
    # result therefore cannot override a verified official warning.
    floor = warning_floor_level(official_warnings)
    risk_level, level_basis = combine_levels(screening_level, floor)

    # ---------------------------------------------------------
    # 8.5 LOCAL CYCLONE IMPACT (separate from regional warning)
    # ---------------------------------------------------------
    #
    # The combined level above stays regional: a RED official warning
    # keeps the REGION at RED however far the anchor lies from the
    # verified footprint. The local assessment below answers the
    # distinct question "is THIS location directly impacted", using
    # only the evidence rules documented in
    # classify_local_cyclone_impact.
    # ---------------------------------------------------------

    local_assessment = classify_local_cyclone_impact(
        warnings=official_warnings,
        inactive_warnings=inactive_warnings,
        warnings_source=warnings_source if isinstance(warnings_source, str) else None,
        warnings_timestamp=warnings_timestamp if isinstance(warnings_timestamp, str) else None,
        warnings_error=str(warnings_error) if warnings_error else None,
        verdict=local_impact.get("verdict"),
        distance_km=local_impact.get("distance_to_footprint_km"),
        geometry_source=local_impact.get("geometry_source"),
        screening_level=screening_level,
        screening_score=risk_score,
        telemetry_status=telemetry_data_status,
    )
    risk_factors.append(
        f"Local cyclone impact: {local_assessment['local_impact_zone']} "
        f"({local_assessment['local_impact_status']}) - "
        f"{local_assessment['reason']}"
    )

    # ---------------------------------------------------------
    # 9. RISK ZONES
    # ---------------------------------------------------------
    #
    # Precise circles are drawn ONLY from verified local evidence
    # (screening extremes observed at the anchor). A regional warning
    # floor alone never generates city circles: the warning's own
    # footprint polygons carry the geography instead (see
    # official_warnings[].footprint and local_impact).
    #
    # These are screening zones around the region center.
    #
    # They are NOT claimed to be official evacuation boundaries.
    #
    # The frontend should display this distinction.
    # ---------------------------------------------------------

    risk_zones = []

    zone_level = None
    if screening_level in ("RED", "ORANGE", "YELLOW"):
        zone_level = screening_level
    elif screening_level == "GREEN" and floor is None:
        zone_level = "GREEN"

    if center_lat is not None and center_lon is not None:

        if zone_level == "RED":

            risk_zones = [
                {
                    "id": "red-zone",
                    "label": "Red Zone",
                    "color": "red",
                    "lat": center_lat,
                    "lon": center_lon,
                    "radius_km": 7.5,
                    "description": (
                        "High-risk screening zone based on "
                        "current hazard indicators."
                    ),
                    "basis": risk_factors,
                },
                {
                    "id": "orange-zone",
                    "label": "Orange Zone",
                    "color": "orange",
                    "lat": center_lat,
                    "lon": center_lon,
                    "radius_km": 15,
                    "description": (
                        "Potential impact screening zone."
                    ),
                    "basis": risk_factors,
                },
            ]

        elif zone_level == "ORANGE":

            risk_zones = [
                {
                    "id": "orange-zone",
                    "label": "Orange Zone",
                    "color": "orange",
                    "lat": center_lat,
                    "lon": center_lon,
                    "radius_km": 10,
                    "description": (
                        "Elevated-risk screening zone."
                    ),
                    "basis": risk_factors,
                },
                {
                    "id": "yellow-zone",
                    "label": "Yellow Zone",
                    "color": "yellow",
                    "lat": center_lat,
                    "lon": center_lon,
                    "radius_km": 20,
                    "description": (
                        "Potential impact / preparedness zone."
                    ),
                    "basis": risk_factors,
                },
            ]

        elif zone_level == "YELLOW":

            risk_zones = [
                {
                    "id": "yellow-zone",
                    "label": "Yellow Zone",
                    "color": "yellow",
                    "lat": center_lat,
                    "lon": center_lon,
                    "radius_km": 15,
                    "description": (
                        "Preparedness screening zone."
                    ),
                    "basis": risk_factors,
                },
                {
                    "id": "green-zone",
                    "label": "Green Zone",
                    "color": "green",
                    "lat": center_lat,
                    "lon": center_lon,
                    "radius_km": 30,
                    "description": (
                        "Currently lower modeled exposure."
                    ),
                    "basis": risk_factors,
                },
            ]

        elif zone_level == "GREEN":

            risk_zones = [
                {
                    "id": "green-zone",
                    "label": "Green Zone",
                    "color": "green",
                    "lat": center_lat,
                    "lon": center_lon,
                    "radius_km": 20,
                    "description": (
                        "No elevated hazard signal detected "
                        "from currently available telemetry."
                    ),
                    "basis": risk_factors,
                }
            ]

    # ---------------------------------------------------------
    # 10. INSURANCE / PARAMETRIC TRIGGER
    # ---------------------------------------------------------
    #
    # Do NOT invent payout values.
    #
    # If actual storm surge data is unavailable, the trigger
    # cannot be evaluated. Wave height is NOT storm surge and is
    # never substituted here.
    # ---------------------------------------------------------

    trigger_threshold_m = 1.2

    if storm_surge is None:

        insurance_summary = {
            "status": "UNAVAILABLE",
            "trigger_met": None,
            "trigger_threshold_m": trigger_threshold_m,
            "observed_water_depth_m": None,
            "estimated_payout_cr": None,
            "headline": (
                "Parametric trigger cannot be evaluated "
                "because current water-depth data is unavailable."
            ),
            "coverage_focus": [
                "Coastal wards",
                "Critical infrastructure",
                "Low-lying settlements",
            ],
        }

    else:

        trigger_met = (
            storm_surge >= trigger_threshold_m
        )

        insurance_summary = {
            "status": "EVALUATED",
            "trigger_met": trigger_met,
            "trigger_threshold_m": trigger_threshold_m,
            "observed_water_depth_m": round(
                storm_surge,
                2
            ),
            "estimated_payout_cr": None,
            "headline": (
                "Configured trigger threshold reached."
                if trigger_met
                else "Configured trigger threshold not reached."
            ),
            "coverage_focus": [
                "Coastal wards",
                "Critical infrastructure",
                "Low-lying settlements",
            ],
            "note": (
                "Payout amount is not calculated because "
                "no actual insurance policy configuration "
                "is connected to this endpoint."
            ),
        }

    # ---------------------------------------------------------
    # 11. META CONTEXT
    # ---------------------------------------------------------
    #
    # Meta gets verified/derived backend information.
    #
    # It does NOT get permission to create:
    # - weather observations
    # - coordinates
    # - insurance payouts
    # - historical events
    # ---------------------------------------------------------

    ai_context = {
        "region": region_key,

        "current_telemetry": {
            "wind_speed_kmh": wind,
            "pressure_hpa": pressure,
            "storm_surge_meters": storm_surge,
            "wave_height_m": wave_height,
            "timestamp": telemetry_timestamp,
            "status": telemetry_data_status,
            "source_system": system_name,
        },

        "ml_probability": ml_probability,

        "active_systems": active_systems,

        "official_warnings": official_warnings,

        "risk_assessment": {
            "level": risk_level,
            "screening_level": screening_level,
            "warning_floor": floor,
            "level_basis": level_basis,
            "score": risk_score,
            "factors": risk_factors,
        },

        "historical_analogs": valid_analogs[:5],

        "forecast": forecast_items[:10],

        "demography": unified_data.get(
            "demography",
            {}
        ),

        "places": unified_data.get(
            "places",
            {}
        ),
    }

    tactical_insights = {
        "summary": None,
        "recommended_tasks": [],
        "reasoning_context": [],
    }

    # ---------------------------------------------------------
    # 12. META = EXPLANATION / PREPARATION ASSISTANT
    # ---------------------------------------------------------

    if client is not None:

        prompt = f"""
You are an AI disaster-preparedness assistant.

You must ONLY reason from the supplied backend data.

IMPORTANT RULES:

1. Never invent weather observations.
2. Never invent storm-surge measurements.
3. Never invent historical disasters.
4. Never invent population numbers.
5. Never invent shelters or hospitals.
6. Never invent insurance payout amounts.
7. Never create new coordinates.
8. Never change the backend risk level.
9. If data is missing, explicitly say that it is unavailable.
10. Do not claim that an area is under an official evacuation order.
11. Provide practical preparedness actions based only on available evidence.

The backend has already calculated the risk screening.

BACKEND DATA:

{json.dumps(ai_context, indent=2, default=str)}

Return ONLY JSON in this exact structure:

{{
    "summary": "Short explanation of the current situation based only on the supplied data.",

    "recommended_tasks": [
        {{
            "department": "Relevant response department",
            "location": "Only use a location explicitly present in the supplied data",
            "description": "Practical preparation action justified by the available data",
            "priority": "critical|high|moderate|low"
        }}
    ],

    "reasoning_context": [
        "Specific supplied fact supporting the recommendation"
    ]
}}

If the telemetry status is UNAVAILABLE or NO_CURRENT_MEASUREMENTS,
do not pretend current hazard conditions are known.
"""

        try:

            parsed_ai = client.generate_json(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
            )

            if isinstance(parsed_ai, dict):

                tactical_insights = {
                    "summary": parsed_ai.get(
                        "summary"
                    ),

                    "recommended_tasks": (
                        parsed_ai.get(
                            "recommended_tasks",
                            []
                        )
                        if isinstance(
                            parsed_ai.get(
                                "recommended_tasks",
                                []
                            ),
                            list
                        )
                        else []
                    ),

                    "reasoning_context": (
                        parsed_ai.get(
                            "reasoning_context",
                            []
                        )
                        if isinstance(
                            parsed_ai.get(
                                "reasoning_context",
                                []
                            ),
                            list
                        )
                        else []
                    ),
                }

        except (MetaClientError, RuntimeError, ValueError) as error:

            print(
                f"[META] Disaster intelligence "
                f"analysis failed: {error}"
            )

            tactical_insights = {
                "summary": (
                    "AI analysis is currently unavailable. "
                    "The response contains backend-derived "
                    "risk information."
                ),

                "recommended_tasks": [],

                "reasoning_context": risk_factors,
            }

    # ---------------------------------------------------------
    # 13. FINAL RESPONSE
    # ---------------------------------------------------------

    return {
        "status": "success",

        "region": region_key,
        "ml_probability": ml_probability,
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "data_quality": {
            "ingestion_status": (
                "FAILED"
                if ingestion_error
                else "SUCCESS"
            ),

            "telemetry_status": telemetry_data_status,

            "ingestion_error": ingestion_error,

            "telemetry_timestamp": telemetry_timestamp,

            "source_errors": source_errors,

            "sources": {
                "meteorological": system_name,
                "marine": (
                    marine.get("source")
                    if isinstance(marine, dict)
                    else None
                ),
                "active_systems": (
                    active_block.get("source")
                    if isinstance(active_block, dict)
                    else None
                ),
                "warnings": (
                    warnings_block.get("source")
                    if isinstance(warnings_block, dict)
                    else None
                ),
                "history": (
                    history.get("source")
                    if isinstance(history, dict)
                    else None
                ),
                "forecast": (
                    forecast.get("source")
                    if isinstance(forecast, dict)
                    else None
                ),
            },
        },

        "current_conditions": {
            "wind_speed_kmh": wind,
            "pressure_hpa": pressure,
            "storm_surge_meters": storm_surge,
            "wave_height_m": wave_height,
            "alert_status": telemetry_status,
        },

        "forecast": {
            "items": forecast_items,
            "source": forecast.get("source"),
            "timestamp": forecast.get("timestamp"),
        },

        "marine": marine if marine else None,

        "active_systems": active_systems,

        "official_warnings": official_warnings,

        "local_impact": local_impact,

        "local_impact_assessment": local_assessment,

        "risk_assessment": {
            "level": risk_level,
            "screening_level": screening_level,
            "warning_floor": floor,
            "level_basis": level_basis,
            "score": risk_score,
            "factors": risk_factors,
            "method": (
                "Deterministic screening from available telemetry "
                "(IMD/WMO bands), raised to at least the verified "
                "official-warning severity; H2O severity probability "
                "reported separately when a trained model is configured"
            ),
            "official_warning": level_basis in ("official_warning", "both"),
            "note": (
                "This screening result is not an official "
                "evacuation order or government warning."
            ),
        },

        "risk_zones": risk_zones,

        "historical_context": {
            "primary_analog": primary_analog,
            "historical_analogs": valid_analogs[:5],
        },

        "demography": unified_data.get(
            "demography",
            {}
        ),

        "critical_places": unified_data.get(
            "places",
            {}
        ),

        "insurance_summary": insurance_summary,

        "ai_analysis": tactical_insights,

        # VERY IMPORTANT:
        # Keep the actual ingestion context available.
        # This lets your frontend explain why the AI produced
        # its recommendations.
        "supporting_context": {
            "telemetry": telemetry,
            "risk_factors": risk_factors,
            "historical_analogs": valid_analogs[:5],
        },
    }
