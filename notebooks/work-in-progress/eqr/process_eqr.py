"""Process EQR contracts and identities."""
import io
import logging
import zipfile
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
from tqdm import tqdm

eqr_data_dir = Path(__file__).parent / "eqr_data"

logger = logging.getLogger()

db_path = Path(__file__).parent / "eqr.db"
db_path.unlink(missing_ok=True)

engine = sa.create_engine(f"sqlite:///{db_path}")

FILE_END_STRS_TO_TABLE_NAMES = {
    "indexPub.CSV": "index_publishing",
    "ident.CSV": "identities",
    "contracts.CSV": "contracts",
}

TABLE_DTYPES = {
    "identities": {"contact_zip": "string", "contact_phone": "string"},
    "contracts": {
        "seller_history_name": "string",
    },
}


def convert_to_stringdtype(df: pd.DataFrame):
    """Convert all columns with nans to StringDtypes."""
    for column in df.columns:
        if df[column].isnull().any():
            df[column] = df[column].astype("string")
    return df


def extract_seller(seller_zip: zipfile.ZipFile, year, quarter):
    """Extract the tables and load them to a sqlite db for a seller."""
    with seller_zip as seller:
        for table_type, table_name in FILE_END_STRS_TO_TABLE_NAMES.items():
            # find a file in seller_zip that matches the substring
            table_csv_path = list(
                filter(lambda x: x.endswith(table_type), seller.namelist())
            )
            assert len(table_csv_path) <= 1
            if table_csv_path:
                df = pd.read_csv(
                    io.BytesIO(seller_zip.read(table_csv_path[0])),
                    encoding="ISO-8859-1",
                    dtype=TABLE_DTYPES.get(table_name),
                )
                df = convert_to_stringdtype(df)

                df["year"] = year
                df["quarter"] = quarter

                with engine.connect() as conn:
                    df.to_sql(table_name, conn, index=False, if_exists="append")


def extract_quarter(quarter_zip_path: Path):
    """Extract a quarter of EQR data."""
    _, year, quarter = quarter_zip_path.stem.split("_")
    year = int(year)
    with zipfile.ZipFile(quarter_zip_path, mode="r") as quarter_zip:
        for seller_path in tqdm(quarter_zip.namelist()):
            seller_zip_bytes = io.BytesIO(quarter_zip.read(seller_path))
            seller_zip = zipfile.ZipFile(seller_zip_bytes)
            extract_seller(seller_zip, year, quarter)


def process_eqr():
    """Load EQR contracts and identities to a sqlite database."""
    for quarter_zip in tqdm(eqr_data_dir.glob("*.zip")):
        print(f"Processing {quarter_zip}")
        extract_quarter(quarter_zip)


if __name__ == "__main__":
    process_eqr()
