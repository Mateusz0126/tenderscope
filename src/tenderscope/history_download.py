"""Download only catalog-selected history inputs; never modify cloud state."""

import argparse
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

from tenderscope.history import read_json, select_runs, source_files, source_path
from tenderscope.storage.adls import validate_account_name


def download_inputs(service, catalog: dict, destination: Path) -> None:
    selected = select_runs(catalog)
    destination.mkdir(parents=True, exist_ok=False)

    def download(container: str, relative: str) -> None:
        target = source_path(destination, f"{container}/{relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        client = service.get_file_system_client(container).get_file_client(relative)
        target.write_bytes(client.download_file().readall())

    for entry in selected:
        key = entry["key"]
        download("bronze", f"{key}/manifest.json")
        download("silver", f"{key}/_SUCCESS.json")
        manifest = read_json(source_path(destination, f"bronze/{key}/manifest.json"))
        pages = manifest.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ValueError("Missing Bronze pages")
        for index, page in enumerate(pages, 1):
            name = f"page_{index:03d}.json"
            if page.get("file") != name:
                raise ValueError("Invalid Bronze page sequence")
            download("bronze", f"{key}/{name}")
        for name in ("notice", "notice_buyer", "notice_cpv"):
            download("silver", f"{key}/{name}.parquet")
        source_files(destination, entry)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--storage-account", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    validate_account_name(args.storage_account)
    with (
        DefaultAzureCredential() as credential,
        DataLakeServiceClient(
            f"https://{args.storage_account}.dfs.core.windows.net",
            credential=credential,
        ) as service,
    ):
        download_inputs(service, read_json(args.catalog), args.destination)
    print(f"Downloaded selected inputs to {args.destination}")


if __name__ == "__main__":
    main()
