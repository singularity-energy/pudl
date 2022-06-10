"""Process EQR contracts and identities."""
import argparse
import io
import logging
import sys
import zipfile
from pathlib import Path
from typing import NamedTuple

import pandas as pd
import sqlalchemy as sa
from tqdm import tqdm

logging.basicConfig()
logger = logging.getLogger()

db_path = Path(__file__).parent / "eqr.db"

eqr_data_dir = Path(__file__).parent / "eqr_data"

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

WORKING_PARTITIONS = {"years": [2020], "quarters": ["Q1", "Q2" "Q3", "Q4"]}


class FercEqrPartition(NamedTuple):
    """Represents FercEqr partition identifying unique resource file."""

    year: int
    quarter: str


def parse_command_line(argv):
    """Parse script command line arguments. See the -h option.

    Args:
        argv (list): command line arguments including caller file name.

    Returns:
        dict: A dictionary mapping command line arguments to their values.

    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-y",
        "--years",
        nargs="+",
        type=int,
        help="""Which years of FERC EQR data to process. Defaults to all years.""",
        default=WORKING_PARTITIONS["years"],
    )
    parser.add_argument(
        "-q",
        "--quarters",
        nargs="+",
        type=str.upper,
        help="""Which quarters to parocess. Defaults to all quarters.""",
        default=WORKING_PARTITIONS["quarters"],
    )
    parser.add_argument(
        "-c",
        "--clobber",
        action="store_true",
        default=False,
        help="Clobber existing PUDL SQLite and Parquet outputs if they exist.",
    )

    arguments = parser.parse_args(argv[1:])
    return arguments


def convert_to_stringdtype(df: pd.DataFrame) -> pd.DataFrame:
    """Convert all columns with nans to StringDtypes."""
    for column in df.columns:
        if df[column].isnull().any():
            df[column] = df[column].astype("string")
    return df


def extract_seller(seller_zip: zipfile.ZipFile, partition):
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
                    parse_dates=True,
                )
                df = convert_to_stringdtype(df)

                df["year"] = partition.year
                df["quarter"] = partition.quarter

                with engine.connect() as conn:
                    df.to_sql(table_name, conn, index=False, if_exists="append")


def extract_partition(partition: FercEqrPartition) -> None:
    """Extract a quarter of EQR data."""
    quarter_zip_path = eqr_data_dir / f"CSV_{partition.year}_{partition.quarter}.zip"
    with zipfile.ZipFile(quarter_zip_path, mode="r") as quarter_zip:
        for seller_path in tqdm(quarter_zip.namelist()):
            seller_zip_bytes = io.BytesIO(quarter_zip.read(seller_path))
            seller_zip = zipfile.ZipFile(seller_zip_bytes)
            extract_seller(seller_zip, partition)


def process_eqr():
    """Load EQR contracts and identities to a sqlite database."""
    args = parse_command_line(sys.argv)
    if args.clobber:
        db_path.unlink(missing_ok=True)
    else:
        if db_path.exists():
            raise SystemExit(
                "The FERC EQR DB already exists, and we don't want to clobber it.\n"
                f"Move {db_path} aside or set clobber=True and try again."
            )

    partitions = [
        FercEqrPartition(year, quarter)
        for year in args.years
        for quarter in args.quarters
    ]

    for partition in tqdm(partitions):
        logger.info(f"Processing {partition}")
        extract_partition(partition)


if __name__ == "__main__":
    process_eqr()
