"""Publish the datasette to fly.io.

We use custom logic here because the datasette-publish-fly plugin bakes the
uncompressed databases into the image, which makes the image too large.

We compress the databases before baking them into the image. Then we decompress
them at runtime to a Fly volume mounted at /data. This avoids a long download
at startup, and allows us stay within the Fly.io 8GB image size limit.

The volume handling is done manually outside of this publish.py script - it
should be terraformed at some point.

Some static fly.io deployment-related files live in ./fly:
* fly.toml - service configuration
* run.sh - service entrypoint

Apart from that: the Dockerfile and dataset-specific
metadata.yml/inspect-data.json are generated by this script.
"""
import json
import logging
import secrets
import sys
from pathlib import Path
from subprocess import check_call, check_output

import click

from pudl.metadata.classes import DatasetteMetadata
from pudl.workspace.setup import PudlPaths

logging.basicConfig(format="%(asctime)s %(message)s", level=logging.INFO)

DOCKERFILE_TEMPLATE = """
FROM python:3.11.0-slim-bullseye
COPY . /app
WORKDIR /app

RUN apt-get update
RUN apt-get install -y zstd

ENV DATASETTE_SECRET '{datasette_secret}'
RUN pip install -U datasette datasette-cluster-map datasette-vega datasette-block-robots
ENV PORT 8080
EXPOSE 8080

CMD ["./run.sh"]
"""


def make_dockerfile() -> str:
    """Write a dockerfile from template, to use in fly deploy.

    We write this from template so we can generate a datasette secret. This way
    we don't have to manage secrets at all.
    """
    datasette_secret = secrets.token_hex(16)
    return DOCKERFILE_TEMPLATE.format(datasette_secret=datasette_secret)


def inspect_data(datasets: list[str], pudl_out: Path) -> str:
    """Pre-inspect databases to generate some metadata for Datasette.

    This is done in the image build process in datasette-publish-fly, but since
    we don't have access to the databases in the build process we have to
    inspect before building the Docker image.
    """
    inspect_output = json.loads(
        check_output(
            [  # noqa: S603
                "datasette",
                "inspect",
            ]
            + [str(pudl_out / ds) for ds in datasets]
        )
    )

    for dataset in inspect_output:
        name = Path(inspect_output[dataset]["file"]).name
        new_filepath = Path("/data") / name
        inspect_output[dataset]["file"] = str(new_filepath)
    return inspect_output


def metadata(pudl_out: Path) -> str:
    """Return human-readable metadata for Datasette."""
    return DatasetteMetadata.from_data_source_ids(pudl_out).to_yaml()


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--fly",
    "-f",
    "deploy",
    flag_value="fly",
    help="Deploy Datasette to fly.io.",
    default=True,
)
@click.option(
    "--local",
    "-l",
    "deploy",
    flag_value="local",
    help="Deploy Datasette locally for testing or debugging purposes.",
)
@click.option(
    "--metadata",
    "-m",
    "deploy",
    flag_value="metadata",
    help="Generate the Datasette metadata.yml in current directory, but do not deploy.",
)
def deploy_datasette(deploy: str) -> int:
    """Generate deployment files and run the deploy."""
    pudl_out = PudlPaths().pudl_output
    metadata_yml = metadata(pudl_out)
    # Order the databases to highlight PUDL
    datasets = (
        ["pudl.sqlite"]
        + sorted(str(p.name) for p in pudl_out.glob("ferc*.sqlite"))
        + ["censusdp1tract.sqlite"]
    )

    if deploy == "fly":
        logging.info("Deploying to fly.io...")
        fly_dir = Path(__file__).parent.absolute() / "fly"
        docker_path = fly_dir / "Dockerfile"
        inspect_path = fly_dir / "inspect-data.json"
        metadata_path = fly_dir / "metadata.yml"

        logging.info(f"Inspecting DBs for datasette: {datasets}...")
        inspect_output = inspect_data(datasets, pudl_out)
        with inspect_path.open("w") as f:
            f.write(json.dumps(inspect_output))

        logging.info(f"Writing Datasette metadata to: {metadata_path}")
        with metadata_path.open("w") as f:
            f.write(metadata_yml)

        logging.info("Writing Dockerfile...")
        with docker_path.open("w") as f:
            f.write(make_dockerfile())

        logging.info(f"Compressing {datasets} and putting into docker context...")
        check_call(
            ["tar", "-a", "-czvf", fly_dir / "all_dbs.tar.zst"] + datasets,  # noqa: S603
            cwd=pudl_out,
        )

        logging.info("Running fly deploy...")
        check_call(["/usr/bin/env", "flyctl", "deploy"], cwd=fly_dir)  # noqa: S603
        logging.info("Deploy finished!")

    elif deploy == "local":
        logging.info("Running Datasette locally...")
        metadata_path = pudl_out / "metadata.yml"
        logging.info(f"Writing Datasette metadata to: {metadata_path}")
        with metadata_path.open("w") as f:
            f.write(metadata_yml)

        check_call(
            ["/usr/bin/env", "datasette", "serve", "-m", "metadata.yml"] + datasets,  # noqa: S603
            cwd=pudl_out,
        )

    elif deploy == "metadata":
        metadata_path = Path.cwd() / "metadata.yml"
        logging.info(f"Writing Datasette metadata to: {metadata_path}")
        with metadata_path.open("w") as f:
            f.write(metadata_yml)

    else:
        logging.error(f"Unrecognized deployment destination: {deploy=}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(deploy_datasette())
