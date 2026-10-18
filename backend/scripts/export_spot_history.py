"""Write the daily spot prices in the database to app/spot_history.csv.gz (bundled with the app, so new databases
start with the full history without calling any API).

    python -m scripts.export_spot_history
"""

from app.db import SessionLocal
from app.services import bullion

if __name__ == "__main__":
    with SessionLocal() as db:
        print(f"Wrote {bullion.export_bundle(db)} prices to {bullion.BUNDLED}")
