"""
scorer.py — versión GRATUITA, sin API de Anthropic.
Filtra vacantes por keywords y detecta si son hacibles desde Buenos Aires.

v2: usa campos _modality y _locations del IADB API directamente,
    mejor detección de ubicaciones (ciudades específicas, "based in X", etc.)
"""

KEYWORDS_POSITIVOS = [
    # Técnica
    "econom", "data", "statistic", "estadistic", "encuesta", "survey",
    "muestr", "sampling", "econometr", "quantitative", "cuantitativ",
    "python", "sql", "stata", "machine learning", "gis", "geospatial",
    "analysis", "analisis", "analyst", "analista",
    # Temática
    "policy", "politica publica", "public policy", "desarrollo", "development",
    "logistic", "trade", "comercio", "transport", "infraestructura",
    "subsidio", "energia", "fiscal", "poverty", "pobreza",
    "evaluation", "evaluacion", "impact", "impacto", "research", "investigacion",
    "consultant", "consultor", "short term", "STC",
    # Ubicación favorable
    "remote", "remoto", "home-based", "telework", "teletrabajo",
    "argentina", "buenos aires", "latin america", "america latina",
    "virtual", "anywhere",
]

KEYWORDS_NEGATIVOS = [
    "driver", "chofer", "security guard", "cleaning", "maintenance",
    "nurse", "enfermera", "doctor", "medical", "surgeon",
    "lawyer", "legal counsel", "abogado",
]

# Frases que confirman presencia física fuera de Argentina
PRESENCIAL_FIJO = [
    "must be based in washington",
    "must be based in new york",
    "must be based in geneva",
    "must be based in brussels",
    "must be based in nairobi",
    "must relocate",
    "relocation required",
    "on-site only",
    "presencial obligatorio",
]

# Keywords que confirman remoto
REMOTO_KW = [
    "remote", "remoto", "home-based", "homebased", "teletrabajo",
    "telework", "virtual", "anywhere", "from your country",
    "desde argentina", "100% remote", "100% remoto",
    "work from wherever", "work from home",
]

# Buenos Aires / Argentina → ok desde BA
BUENOS_AIRES_KW = ["buenos aires", "argentina", "arg "]

# Ciudades que implican presencia física fuera de Argentina
CIUDADES_OTRAS = [
    "washington, d.c", "washington dc", "new york", "geneva", "brussels",
    "nairobi", "addis ababa", "bangkok", "dakar", "accra", "abuja",
    "port-au-prince", "tegucigalpa", "managua", "kathmandu",
    "haiti", "port au prince",
]


def _detect_remote(texto: str, locations: str = "", modality: str = "") -> "bool | None":
    """
    True  → hacible desde Buenos Aires
    False → requiere presencia en otra ciudad
    None  → no queda claro (no descartar)
    """
    t   = texto.lower()
    loc = locations.lower()
    mod = modality.lower()

    # — Campo de modalidad directo (viene del IADB API) —
    if mod:
        if "remote" in mod:
            return True
        if "on site" in mod or "onsite" in mod:
            # On site: ok solo si Buenos Aires está listada como ubicación
            if loc and any(k in loc for k in BUENOS_AIRES_KW):
                return True
            if loc:
                return False   # on site en otra ciudad
            # Sin info de ubicación → no sabemos, no descartamos
            return None

    # — Campo de ubicaciones directo —
    if loc:
        if "remote" in loc:
            return True
        if any(k in loc for k in BUENOS_AIRES_KW):
            return True

    # — Búsqueda en texto libre —
    if any(k in t for k in REMOTO_KW):
        return True
    if any(k in t for k in BUENOS_AIRES_KW):
        return True
    if any(k in t for k in PRESENCIAL_FIJO):
        return False

    # "based in X" / "located in X" con ciudad que no es Argentina
    for ciudad in CIUDADES_OTRAS:
        if f"based in {ciudad}" in t or f"located in {ciudad}" in t:
            return False

    # Si hay campo de ubicaciones y NO incluye BA → presencial en otra ciudad
    if loc and "remote" not in loc and not any(k in loc for k in BUENOS_AIRES_KW):
        if "on site" in mod:
            return False

    return None   # sin info suficiente → no descartar


def score_job(title: str, body: str, org: str, **kwargs) -> dict:
    """
    Retorna: {"relevant": bool, "score": int 1-10, "reason": str, "remote_ok": bool|None}

    kwargs opcionales:
      _modality  → campo cust_workModality del IADB (ej. "Remote", "On site")
      _locations → campo jobLocationShort del IADB (ej. "Argentina Buenos Aires , Peru Lima")
    """
    texto = (title + " " + body).lower()

    hits_pos = sum(1 for kw in KEYWORDS_POSITIVOS if kw.lower() in texto)
    hits_neg = sum(1 for kw in KEYWORDS_NEGATIVOS if kw.lower() in texto)
    score = min(10, max(1, hits_pos * 2 - hits_neg * 3))

    # Bonus si el título menciona algo directamente relevante
    if any(kw in title.lower() for kw in [
        "consultant", "consultor", "economist", "economista",
        "data", "analyst", "analista", "research", "survey",
        "encuesta", "statistician", "specialist",
    ]):
        score = min(10, score + 2)

    modality_field  = kwargs.get("_modality", "")
    locations_field = kwargs.get("_locations", "")

    remote_ok = _detect_remote(texto, locations_field, modality_field)
    relevant  = score >= 5 and remote_ok is not False

    # Razón legible para el mensaje de Telegram
    if not relevant:
        if remote_ok is False:
            hint = (
                f"{modality_field} — {locations_field[:60]}" if locations_field
                else modality_field if modality_field
                else "presencia requerida en otra ciudad"
            )
            reason = f"No hacible desde BA: {hint}"
        else:
            reason = f"Score bajo ({hits_pos} keywords)"
    else:
        matched = [kw for kw in KEYWORDS_POSITIVOS if kw.lower() in texto][:3]
        reason = "Match: " + ", ".join(matched) if matched else "Keywords generales"

    return {
        "relevant":  relevant,
        "score":     score,
        "reason":    reason,
        "remote_ok": remote_ok,
    }
