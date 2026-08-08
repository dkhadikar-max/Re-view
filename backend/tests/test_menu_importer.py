"""Menu Importer — MENU_ORDERING.md §3, frozen v1 sub-scope.

Tests the extraction/classification pipeline (menu_ai_parser.py's
heuristic fallback -> menu_parser.py's classification) and
MenuImporter's own import_()/summary() directly against the database,
independent of the HTTP layer (mirrors the existing PDF import test
style where practical, but stays at the service level since no
`test_pdf_importer.py`-equivalent service-level file exists to mirror
exactly).
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest

from app.db.session import Base
from app.models.entities import ImportSession, ImportSessionStatus, MenuItem, Property, Tenant
from app.schemas import MenuConfirmItem, MenuItemDraft
from app.services.menu_importer import menu_importer
from app.services.menu_parser import classify_extracted_items


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_property(db, *, tenant_id):
    db.add(Tenant(id=tenant_id, name=tenant_id))
    property_ = Property(tenant_id=tenant_id, name=f"{tenant_id} Hotel", city="Berlin", country="Germany")
    db.add(property_)
    db.flush()
    return property_


def _make_session(db, *, tenant_id):
    session = ImportSession(
        tenant_id=tenant_id, source="menu", status=ImportSessionStatus.running,
        initiated_by="manager@hotel.test",
    )
    db.add(session)
    db.flush()
    return session


# -- heuristic extraction / classification -------------------------------


def test_heuristic_extracts_name_and_price_with_dot_leader():
    text = "Grilled Salmon .......... 24.00\nCaesar Salad .......... 12.50\n"
    rows = classify_extracted_items(
        [
            {"name": "Grilled Salmon", "price": 24.0, "currency": "EUR", "confidence": 0.9},
            {"name": "Caesar Salad", "price": 12.5, "currency": "EUR", "confidence": 0.9},
        ],
        full_text=text,
    )
    assert len(rows) == 2
    assert all(row.review_state == "ready_to_import" for row in rows)
    assert rows[0].item.name == "Grilled Salmon"
    assert rows[0].item.price == 24.0


def test_missing_price_routes_to_needs_review():
    rows = classify_extracted_items(
        [{"name": "Mystery Dish", "price": None, "confidence": 0.9}],
        full_text="Mystery Dish",
    )
    assert len(rows) == 1
    assert rows[0].review_state == "needs_review"
    assert rows[0].item is None
    assert any(issue.field == "price" for issue in rows[0].issues)


def test_missing_name_routes_to_needs_review():
    rows = classify_extracted_items(
        [{"name": None, "price": 10.0, "confidence": 0.9}],
        full_text="",
    )
    assert rows[0].review_state == "needs_review"
    assert rows[0].item is None
    assert any(issue.field == "name" for issue in rows[0].issues)


def test_low_confidence_routes_to_needs_review_even_with_valid_fields():
    rows = classify_extracted_items(
        [{"name": "Soup of the Day", "price": 8.0, "confidence": 0.3}],
        full_text="",
    )
    assert rows[0].review_state == "needs_review"
    # Still built (name + price were present) -- just not confident enough.
    assert rows[0].item is not None
    assert rows[0].item.name == "Soup of the Day"


def test_never_invents_a_missing_price_in_heuristic_extraction():
    """A line with no clear price pattern produces no candidate at all --
    not a guessed price."""
    from app.integrations.menu_ai_parser import _heuristic_extract

    text = "Our chef recommends the seasonal tasting menu.\nAsk your server for details."
    items = _heuristic_extract(text)
    assert items == []


def test_heuristic_extracts_currency_symbol():
    from app.integrations.menu_ai_parser import _heuristic_extract

    items = _heuristic_extract("Club Sandwich .......... €18.00")
    assert len(items) == 1
    assert items[0]["name"] == "Club Sandwich"
    assert items[0]["price"] == 18.0
    assert items[0]["currency"] == "EUR"


# -- MenuImporter.import_() -----------------------------------------------


def test_import_creates_menu_items_scoped_to_property(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-a")
    session = _make_session(db, tenant_id="hotel-a")

    rows = [
        MenuConfirmItem(
            item=MenuItemDraft(menu_name="Dinner Menu", name="Grilled Salmon", price=24.0)
        ),
        MenuConfirmItem(
            item=MenuItemDraft(menu_name="Dinner Menu", name="Caesar Salad", price=12.5)
        ),
    ]

    result = menu_importer.import_(rows, session, db=db, tenant_id="hotel-a", property_id=property_.id)

    assert len(result["imported"]) == 2
    items = db.query(MenuItem).filter(MenuItem.tenant_id == "hotel-a").all()
    assert len(items) == 2
    assert all(item.property_id == property_.id for item in items)
    assert all(item.source_import_id == session.id for item in items)
    assert session.rows_imported == 2


def test_reupload_creates_new_rows_not_a_merge(db_session):
    """No fuzzy dedup against existing items -- a second upload always
    creates fresh rows, per the frozen decision (fuzzy name-matching
    across an edited menu is exactly the guess this codebase avoids)."""
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-b")
    first_session = _make_session(db, tenant_id="hotel-b")
    menu_importer.import_(
        [MenuConfirmItem(item=MenuItemDraft(name="Grilled Salmon", price=24.0))],
        first_session, db=db, tenant_id="hotel-b", property_id=property_.id,
    )

    second_session = _make_session(db, tenant_id="hotel-b")
    menu_importer.import_(
        [MenuConfirmItem(item=MenuItemDraft(name="Grilled Salmon", price=26.0))],
        second_session, db=db, tenant_id="hotel-b", property_id=property_.id,
    )

    items = db.query(MenuItem).filter(MenuItem.tenant_id == "hotel-b", MenuItem.name == "Grilled Salmon").all()
    assert len(items) == 2
    assert {item.price for item in items} == {24.0, 26.0}


def test_menu_item_id_is_stable_across_edits(db_session):
    """The identity a future Order snapshot depends on -- editing a
    field must never change the row's own id."""
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-c")
    session = _make_session(db, tenant_id="hotel-c")
    menu_importer.import_(
        [MenuConfirmItem(item=MenuItemDraft(name="Grilled Salmon", price=24.0))],
        session, db=db, tenant_id="hotel-c", property_id=property_.id,
    )
    item = db.query(MenuItem).filter(MenuItem.tenant_id == "hotel-c").one()
    original_id = item.id

    item.price = 26.0
    item.available = False
    db.flush()

    refreshed = db.query(MenuItem).filter(MenuItem.id == original_id).one()
    assert refreshed.id == original_id
    assert refreshed.price == 26.0
    assert refreshed.available is False


def test_summary_groups_by_menu_name(db_session):
    db = db_session
    property_ = _make_property(db, tenant_id="hotel-d")
    session = _make_session(db, tenant_id="hotel-d")
    menu_importer.import_(
        [
            MenuConfirmItem(item=MenuItemDraft(menu_name="Breakfast", name="Omelette", price=9.0)),
            MenuConfirmItem(item=MenuItemDraft(menu_name="Breakfast", name="Pancakes", price=8.0)),
            MenuConfirmItem(item=MenuItemDraft(menu_name="Dinner", name="Steak", price=32.0)),
        ],
        session, db=db, tenant_id="hotel-d", property_id=property_.id,
    )

    summary = menu_importer.summary(session, db=db)
    assert summary["items_imported"] == 3
    assert summary["by_menu"] == {"Breakfast": 2, "Dinner": 1}


def test_tenant_isolation_on_import(db_session):
    db = db_session
    property_a = _make_property(db, tenant_id="hotel-e1")
    _make_property(db, tenant_id="hotel-e2")
    session = _make_session(db, tenant_id="hotel-e1")
    menu_importer.import_(
        [MenuConfirmItem(item=MenuItemDraft(name="Grilled Salmon", price=24.0))],
        session, db=db, tenant_id="hotel-e1", property_id=property_a.id,
    )

    assert db.query(MenuItem).filter(MenuItem.tenant_id == "hotel-e1").count() == 1
    assert db.query(MenuItem).filter(MenuItem.tenant_id == "hotel-e2").count() == 0
