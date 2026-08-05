"""CLI: python -m app.db.seed_cli"""
from app.db.seed import register_handlers, seed_database
from app.db.session import Base, SessionLocal, engine


def main() -> None:
    Base.metadata.create_all(bind=engine)
    register_handlers()
    db = SessionLocal()
    try:
        seed_database(db)
        print("Seed complete")
    finally:
        db.close()


if __name__ == "__main__":
    main()
