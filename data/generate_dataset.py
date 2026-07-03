"""
generate_dataset.py — generates synthetic GCP billing/usage data as Apache Iceberg tables.

Run: uv run python data/generate_dataset.py
Produces: data/warehouse/ directory with Iceberg tables readable by DuckDB.

Falls back to Parquet if pyiceberg write fails (documented fallback).
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import duckdb

WAREHOUSE_PATH = Path(__file__).parent / "warehouse"
PROJECTS = ["analytics-prod", "ml-platform", "data-ingestion", "backend-api"]
SERVICES = ["BigQuery", "Cloud Storage", "Compute Engine", "Cloud Run", "Vertex AI"]
SKUS = {
    "BigQuery": ["Analysis", "Storage Active", "Storage Long-Term"],
    "Cloud Storage": ["Standard Storage", "Nearline Storage", "Operations"],
    "Compute Engine": ["N2 Instance Core", "N2 Instance Ram", "GPU"],
    "Cloud Run": ["CPU Allocation Time", "Memory Allocation Time", "Requests"],
    "Vertex AI": ["Prediction", "Training", "Embeddings"],
}


def generate_billing_rows(n_days: int = 90) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    start = date.today() - timedelta(days=n_days)
    for i in range(n_days):
        d = start + timedelta(days=i)
        for project in PROJECTS:
            for service in SERVICES:
                for sku in SKUS[service]:
                    usage = round(random.uniform(0.1, 1000.0), 4)
                    cost = round(usage * random.uniform(0.001, 0.05), 4)
                    rows.append(
                        {
                            "date": d.isoformat(),
                            "project_id": project,
                            "service": service,
                            "sku": sku,
                            "usage_amount": usage,
                            "cost_usd": cost,
                            "currency": "USD",
                        }
                    )
    return rows


def generate_resource_rows(n_days: int = 90) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    start = date.today() - timedelta(days=n_days)
    resource_types = ["vm", "bucket", "cloudsql", "gke-node"]
    regions = ["us-central1", "europe-west1", "asia-east1"]
    for i in range(n_days):
        d = start + timedelta(days=i)
        for project in PROJECTS:
            for rt in resource_types:
                rows.append(
                    {
                        "date": d.isoformat(),
                        "project_id": project,
                        "resource_type": rt,
                        "resource_name": f"{rt}-{project[:4]}",
                        "region": random.choice(regions),
                        "utilization_pct": round(random.uniform(5.0, 95.0), 2),
                    }
                )
    return rows


def generate_credits_rows(n_days: int = 90) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    start = date.today() - timedelta(days=n_days)
    credit_types = ["SUSTAINED_USE_DISCOUNT", "COMMITTED_USE_DISCOUNT", "PROMOTIONAL"]
    for i in range(n_days):
        d = start + timedelta(days=i)
        for project in PROJECTS:
            if random.random() > 0.6:
                rows.append(
                    {
                        "date": d.isoformat(),
                        "project_id": project,
                        "credit_type": random.choice(credit_types),
                        "credit_amount_usd": round(random.uniform(1.0, 50.0), 4),
                    }
                )
    return rows


def write_parquet_fallback(con: duckdb.DuckDBPyConnection) -> None:
    """Write Parquet files as documented fallback if Iceberg write fails."""
    WAREHOUSE_PATH.mkdir(parents=True, exist_ok=True)
    for table in ["gcp_billing_export", "gcp_resource_usage", "gcp_credits"]:
        out = WAREHOUSE_PATH / f"{table}.parquet"
        con.execute(f"COPY {table} TO '{out}' (FORMAT PARQUET)")
        print(f"  Wrote fallback Parquet: {out}")


def main() -> None:
    print("Generating synthetic GCP billing dataset...")
    con = duckdb.connect(":memory:")

    billing = generate_billing_rows()
    resources = generate_resource_rows()
    credits = generate_credits_rows()

    con.execute(
        """
        CREATE TABLE gcp_billing_export AS
        SELECT * FROM read_json_auto(?)
    """,
        [billing],
    )
    con.execute(
        """
        CREATE TABLE gcp_resource_usage AS
        SELECT * FROM read_json_auto(?)
    """,
        [resources],
    )
    con.execute(
        """
        CREATE TABLE gcp_credits AS
        SELECT * FROM read_json_auto(?)
    """,
        [credits],
    )

    print(f"  gcp_billing_export: {len(billing)} rows")
    print(f"  gcp_resource_usage: {len(resources)} rows")
    print(f"  gcp_credits: {len(credits)} rows")

    # Try Iceberg write; fall back to Parquet
    try:
        con.execute("INSTALL iceberg; LOAD iceberg;")
        WAREHOUSE_PATH.mkdir(parents=True, exist_ok=True)
        for table in ["gcp_billing_export", "gcp_resource_usage", "gcp_credits"]:
            out = WAREHOUSE_PATH / table
            con.execute(f"COPY {table} TO '{out}' (FORMAT ICEBERG, ALLOW_OVERWRITE TRUE)")
            print(f"  Wrote Iceberg table: {out}")
    except Exception as e:
        print(f"  Iceberg write failed ({e}), falling back to Parquet...")
        write_parquet_fallback(con)

    print("Done.")


if __name__ == "__main__":
    main()
