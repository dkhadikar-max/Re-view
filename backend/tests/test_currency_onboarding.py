"""Currency mapping and hotel signup currency tests."""

from app.services.currency import convert_from_eur, currency_for_country


def test_currency_for_country_common():
    assert currency_for_country("India") == "INR"
    assert currency_for_country("IN") == "INR"
    assert currency_for_country("Germany") == "EUR"
    assert currency_for_country("United Kingdom") == "GBP"
    assert currency_for_country("USA") == "USD"
    assert currency_for_country("United Arab Emirates") == "AED"
    assert currency_for_country("Japan") == "JPY"
    assert currency_for_country("") == "EUR"


def test_convert_from_eur_scales():
    assert convert_from_eur(100, "EUR") == 100
    assert convert_from_eur(100, "INR") == 9000
    assert convert_from_eur(100, "USD") == 110


def test_hotel_signup_sets_currency_from_country(client):
    res = client.post(
        "/api/demo/hotel-signup",
        json={
            "hotel_name": "Jaipur Palace",
            "your_name": "Priya Shah",
            "email": "priya.currency@example.com",
            "password": "TryRevisit1!",
            "city": "Jaipur",
            "country": "India",
            "rooms": 72,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["currency"] == "INR"

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    props = client.get("/api/properties", headers=headers)
    assert props.status_code == 200
    assert props.json()[0]["currency"] == "INR"
    assert props.json()[0]["country"] == "India"

    reservations = client.get("/api/reservations", headers=headers)
    assert reservations.status_code == 200
    assert all(r["currency"] == "INR" for r in reservations.json())
    assert any(r["total_amount"] > 1000 for r in reservations.json())

    celebrate = client.get("/api/celebrate/config", headers=headers)
    assert celebrate.status_code == 200
    assert celebrate.json()["currency"] == "INR"

    stats = client.get("/api/dashboard/stats", headers=headers)
    assert stats.status_code == 200
    assert stats.json()["currency"] == "INR"

    roi = client.get("/api/analytics/roi?period_days=30", headers=headers)
    assert roi.status_code == 200
    assert roi.json()["currency"] == "INR"
    assert "₹" in roi.json()["narrative"] or "INR" in roi.json()["narrative"]


def test_hotel_signup_uk_uses_gbp(client):
    res = client.post(
        "/api/demo/hotel-signup",
        json={
            "hotel_name": "Bath Abbey Inn",
            "your_name": "James Reed",
            "email": "james.currency@example.com",
            "password": "TryRevisit1!",
            "city": "Bath",
            "country": "United Kingdom",
            "rooms": 36,
        },
    )
    assert res.status_code == 200
    assert res.json()["currency"] == "GBP"
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    props = client.get("/api/properties", headers=headers).json()
    assert props[0]["currency"] == "GBP"
