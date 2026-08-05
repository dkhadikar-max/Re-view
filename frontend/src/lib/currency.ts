/** Country → ISO 4217 currency for onboarding preview (mirrors backend). */

const COUNTRY_CURRENCY: Record<string, string> = {
  germany: "EUR",
  france: "EUR",
  italy: "EUR",
  spain: "EUR",
  portugal: "EUR",
  netherlands: "EUR",
  belgium: "EUR",
  austria: "EUR",
  ireland: "EUR",
  greece: "EUR",
  finland: "EUR",
  croatia: "EUR",
  "united kingdom": "GBP",
  uk: "GBP",
  england: "GBP",
  switzerland: "CHF",
  sweden: "SEK",
  norway: "NOK",
  denmark: "DKK",
  poland: "PLN",
  "united states": "USD",
  usa: "USD",
  us: "USD",
  canada: "CAD",
  mexico: "MXN",
  brazil: "BRL",
  india: "INR",
  "united arab emirates": "AED",
  uae: "AED",
  dubai: "AED",
  "saudi arabia": "SAR",
  qatar: "QAR",
  japan: "JPY",
  china: "CNY",
  singapore: "SGD",
  "hong kong": "HKD",
  australia: "AUD",
  "new zealand": "NZD",
  thailand: "THB",
  malaysia: "MYR",
  indonesia: "IDR",
  philippines: "PHP",
  vietnam: "VND",
  "south africa": "ZAR",
  turkey: "TRY",
  israel: "ILS",
  egypt: "EGP",
  morocco: "MAD",
};

const ISO_CURRENCY: Record<string, string> = {
  DE: "EUR",
  FR: "EUR",
  IT: "EUR",
  ES: "EUR",
  PT: "EUR",
  NL: "EUR",
  BE: "EUR",
  AT: "EUR",
  IE: "EUR",
  GB: "GBP",
  UK: "GBP",
  CH: "CHF",
  SE: "SEK",
  NO: "NOK",
  DK: "DKK",
  PL: "PLN",
  US: "USD",
  CA: "CAD",
  MX: "MXN",
  BR: "BRL",
  IN: "INR",
  AE: "AED",
  SA: "SAR",
  QA: "QAR",
  JP: "JPY",
  CN: "CNY",
  SG: "SGD",
  HK: "HKD",
  AU: "AUD",
  NZ: "NZD",
  TH: "THB",
  MY: "MYR",
  ID: "IDR",
  PH: "PHP",
  VN: "VND",
  ZA: "ZAR",
  TR: "TRY",
  IL: "ILS",
  EG: "EGP",
  MA: "MAD",
};

export function currencyForCountry(country: string, fallback = "EUR"): string {
  const raw = (country || "").trim();
  if (!raw) return fallback;
  if (raw.length === 2 && /^[a-zA-Z]+$/.test(raw)) {
    return ISO_CURRENCY[raw.toUpperCase()] || fallback;
  }
  const key = raw.toLowerCase();
  if (COUNTRY_CURRENCY[key]) return COUNTRY_CURRENCY[key];
  for (const [name, code] of Object.entries(COUNTRY_CURRENCY)) {
    if (key.startsWith(name) || name.startsWith(key)) return code;
  }
  return fallback;
}
