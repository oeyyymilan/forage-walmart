"""
populate_db.py

Reads the three shipping spreadsheets provided by the shipping department
and inserts their data into shipment_database.db, following the schema:

    product(id, name)
    shipment(id, product_id, quantity, origin, destination)

Spreadsheet 0 (shipping_data_0.csv):
    Already contains one row per shipment/product combination, along with
    quantity, origin and destination -> can be inserted directly.

Spreadsheet 1 (shipping_data_1.csv):
    One row per individual product unit within a shipment (no quantity or
    origin/destination columns). Multiple rows share the same
    shipment_identifier + product, and the quantity for that
    product must be derived by counting how many times it appears
    within that shipment.

Spreadsheet 2 (shipping_data_2.csv):
    Contains the origin/destination (and driver) for each shipment_identifier
    referenced in spreadsheet 1. Spreadsheet 1 and 2 must be joined on
    shipment_identifier before they can be inserted into the `shipment` table.
"""

import csv
import sqlite3
from collections import Counter
from pathlib import Path

DB_PATH = Path("shipment_database.db")
DATA_DIR = Path("data")

SHIPPING_DATA_0 = DATA_DIR / "shipping_data_0.csv"
SHIPPING_DATA_1 = DATA_DIR / "shipping_data_1.csv"
SHIPPING_DATA_2 = DATA_DIR / "shipping_data_2.csv"


def get_or_create_product_id(cursor: sqlite3.Cursor, product_name: str) -> int:
    """
    Returns the id of `product_name` in the product table, inserting a new
    row for it first if it doesn't already exist.
    """
    cursor.execute("SELECT id FROM product WHERE name = ?", (product_name,))
    row = cursor.fetchone()
    if row is not None:
        return row[0]

    cursor.execute("INSERT INTO product (name) VALUES (?)", (product_name,))
    return cursor.lastrowid


def insert_shipment_row(
    cursor: sqlite3.Cursor,
    product_name: str,
    quantity: int,
    origin: str,
    destination: str,
) -> None:
    """Inserts a single row into the shipment table."""
    product_id = get_or_create_product_id(cursor, product_name)
    cursor.execute(
        """
        INSERT INTO shipment (product_id, quantity, origin, destination)
        VALUES (?, ?, ?, ?)
        """,
        (product_id, quantity, origin, destination),
    )


def process_shipping_data_0(cursor: sqlite3.Cursor) -> None:
    """
    Spreadsheet 0 is self-contained: every row already has a product,
    quantity, origin and destination, so each row maps directly onto one
    row in the `shipment` table.
    """
    with open(SHIPPING_DATA_0, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            insert_shipment_row(
                cursor,
                product_name=row["product"],
                quantity=int(row["product_quantity"]),
                origin=row["origin_warehouse"],
                destination=row["destination_store"],
            )


def process_shipping_data_1_and_2(cursor: sqlite3.Cursor) -> None:
    """
    Spreadsheet 1 has one row per product *unit* (no quantity column), so
    rows with the same shipment_identifier + product need to be grouped
    together and counted to work out the quantity shipped.

    Spreadsheet 2 provides the origin/destination for each
    shipment_identifier, so it's loaded into a lookup dict first and then
    joined against the grouped data from spreadsheet 1.
    """
    # Step 1: build a shipment_identifier -> (origin, destination) lookup
    # from spreadsheet 2.
    shipment_locations = {}
    with open(SHIPPING_DATA_2, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            shipment_locations[row["shipment_identifier"]] = (
                row["origin_warehouse"],
                row["destination_store"],
            )

    # Step 2: count occurrences of each (shipment_identifier, product) pair
    # in spreadsheet 1 -- this gives us the quantity of each product
    # within each shipment.
    product_counts = Counter()
    with open(SHIPPING_DATA_1, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["shipment_identifier"], row["product"])
            product_counts[key] += 1

    # Step 3: insert one row per (shipment_identifier, product) pair,
    # using the counted quantity and the origin/destination looked up
    # from spreadsheet 2.
    for (shipment_id, product_name), quantity in product_counts.items():
        origin, destination = shipment_locations[shipment_id]
        insert_shipment_row(
            cursor,
            product_name=product_name,
            quantity=quantity,
            origin=origin,
            destination=destination,
        )


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        process_shipping_data_0(cursor)
        process_shipping_data_1_and_2(cursor)
        conn.commit()
        print("Database populated successfully.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()