"""Map hotel country → ISO 4217 currency for onboarding and demo data."""

from __future__ import annotations

# Approximate EUR→local multipliers for demo amounts (not live FX).
_EUR_TO_LOCAL: dict[str, float] = {
    "EUR": 1.0,
    "USD": 1.1,
    "GBP": 0.85,
    "CHF": 0.95,
    "SEK": 11.5,
    "NOK": 11.8,
    "DKK": 7.45,
    "PLN": 4.3,
    "CZK": 25.0,
    "HUF": 390.0,
    "RON": 5.0,
    "TRY": 38.0,
    "INR": 90.0,
    "AED": 4.0,
    "SAR": 4.1,
    "QAR": 4.0,
    "JPY": 165.0,
    "CNY": 8.0,
    "KRW": 1500.0,
    "SGD": 1.45,
    "HKD": 8.5,
    "AUD": 1.65,
    "NZD": 1.8,
    "CAD": 1.5,
    "MXN": 20.0,
    "BRL": 6.0,
    "ARS": 1000.0,
    "CLP": 1050.0,
    "COP": 4500.0,
    "ZAR": 20.0,
    "EGP": 55.0,
    "MAD": 10.5,
    "THB": 38.0,
    "MYR": 5.0,
    "IDR": 17500.0,
    "PHP": 62.0,
    "VND": 28000.0,
    "PKR": 300.0,
    "BDT": 130.0,
    "LKR": 330.0,
    "NPR": 145.0,
    "ILS": 4.0,
}

# Country name / common aliases → currency
_COUNTRY_CURRENCY: dict[str, str] = {
    # Eurozone & EUR pegs used in hospitality demos
    "germany": "EUR",
    "deutschland": "EUR",
    "france": "EUR",
    "italy": "EUR",
    "italia": "EUR",
    "spain": "EUR",
    "españa": "EUR",
    "espana": "EUR",
    "portugal": "EUR",
    "netherlands": "EUR",
    "holland": "EUR",
    "belgium": "EUR",
    "austria": "EUR",
    "ireland": "EUR",
    "greece": "EUR",
    "finland": "EUR",
    "luxembourg": "EUR",
    "slovakia": "EUR",
    "slovenia": "EUR",
    "estonia": "EUR",
    "latvia": "EUR",
    "lithuania": "EUR",
    "croatia": "EUR",
    "cyprus": "EUR",
    "malta": "EUR",
    "monaco": "EUR",
    "andorra": "EUR",
    "montenegro": "EUR",
    # Other Europe
    "united kingdom": "GBP",
    "uk": "GBP",
    "england": "GBP",
    "scotland": "GBP",
    "wales": "GBP",
    "switzerland": "CHF",
    "sweden": "SEK",
    "norway": "NOK",
    "denmark": "DKK",
    "poland": "PLN",
    "czech republic": "CZK",
    "czechia": "CZK",
    "hungary": "HUF",
    "romania": "RON",
    "turkey": "TRY",
    "türkiye": "TRY",
    "turkiye": "TRY",
    # Americas
    "united states": "USD",
    "usa": "USD",
    "us": "USD",
    "united states of america": "USD",
    "canada": "CAD",
    "mexico": "MXN",
    "brazil": "BRL",
    "argentina": "ARS",
    "chile": "CLP",
    "colombia": "COP",
    # Middle East & Africa
    "united arab emirates": "AED",
    "uae": "AED",
    "dubai": "AED",
    "saudi arabia": "SAR",
    "qatar": "QAR",
    "israel": "ILS",
    "egypt": "EGP",
    "morocco": "MAD",
    "south africa": "ZAR",
    # Asia Pacific
    "india": "INR",
    "japan": "JPY",
    "china": "CNY",
    "south korea": "KRW",
    "korea": "KRW",
    "singapore": "SGD",
    "hong kong": "HKD",
    "australia": "AUD",
    "new zealand": "NZD",
    "thailand": "THB",
    "malaysia": "MYR",
    "indonesia": "IDR",
    "philippines": "PHP",
    "vietnam": "VND",
    "pakistan": "PKR",
    "bangladesh": "BDT",
    "sri lanka": "LKR",
    "nepal": "NPR",
}

# ISO country codes
_ISO_CURRENCY: dict[str, str] = {
    "DE": "EUR",
    "FR": "EUR",
    "IT": "EUR",
    "ES": "EUR",
    "PT": "EUR",
    "NL": "EUR",
    "BE": "EUR",
    "AT": "EUR",
    "IE": "EUR",
    "GR": "EUR",
    "FI": "EUR",
    "LU": "EUR",
    "SK": "EUR",
    "SI": "EUR",
    "EE": "EUR",
    "LV": "EUR",
    "LT": "EUR",
    "HR": "EUR",
    "CY": "EUR",
    "MT": "EUR",
    "GB": "GBP",
    "UK": "GBP",
    "CH": "CHF",
    "SE": "SEK",
    "NO": "NOK",
    "DK": "DKK",
    "PL": "PLN",
    "CZ": "CZK",
    "HU": "HUF",
    "RO": "RON",
    "TR": "TRY",
    "US": "USD",
    "CA": "CAD",
    "MX": "MXN",
    "BR": "BRL",
    "AR": "ARS",
    "CL": "CLP",
    "CO": "COP",
    "AE": "AED",
    "SA": "SAR",
    "QA": "QAR",
    "IL": "ILS",
    "EG": "EGP",
    "MA": "MAD",
    "ZA": "ZAR",
    "IN": "INR",
    "JP": "JPY",
    "CN": "CNY",
    "KR": "KRW",
    "SG": "SGD",
    "HK": "HKD",
    "AU": "AUD",
    "NZ": "NZD",
    "TH": "THB",
    "MY": "MYR",
    "ID": "IDR",
    "PH": "PHP",
    "VN": "VND",
    "PK": "PKR",
    "BD": "BDT",
    "LK": "LKR",
    "NP": "NPR",
}


def normalize_country(country: str | None) -> str:
    return (country or "").strip().lower()


def currency_for_country(country: str | None, default: str = "EUR") -> str:
    """Return ISO 4217 currency code for a hotel country name or ISO code."""
    raw = (country or "").strip()
    if not raw:
        return default
    if len(raw) == 3 and raw.isalpha() and raw.upper() in _EUR_TO_LOCAL:
        return raw.upper()
    if len(raw) == 2 and raw.isalpha():
        return _ISO_CURRENCY.get(raw.upper(), default)
    key = normalize_country(raw)
    if key in _COUNTRY_CURRENCY:
        return _COUNTRY_CURRENCY[key]
    # Prefix match: "United States of America" already exact; try first token sets
    for name, code in _COUNTRY_CURRENCY.items():
        if key.startswith(name) or name.startswith(key):
            return code
    return default


def convert_from_eur(amount_eur: float, currency: str) -> float:
    """Convert a EUR demo amount into the hotel currency (approximate)."""
    code = (currency or "EUR").upper()
    rate = _EUR_TO_LOCAL.get(code, 1.0)
    value = float(amount_eur) * rate
    if code in {"JPY", "KRW", "IDR", "VND", "CLP", "COP", "HUF", "ARS"}:
        return float(round(value))
    if value >= 100:
        return float(round(value))
    return float(round(value, 2))
