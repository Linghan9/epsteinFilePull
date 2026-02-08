## Epstein File Pull
This repository is designed to automate the process of pulling and downloading Epstein-related files from the U.S. Department of Justice (DOJ) website.

Scripts and tools in this repository are intended for research and archival purposes only. Please ensure you comply with all relevant terms of use and legal requirements when accessing government data.

## Usage
Ensure all prerequisites below are installed and then to download the default doj disclosures datasets 8-12 run the following:

```sh
    pipenv run python epsteinFilePull.py 
```

The output will be written to `./out/[YYYYmmdd_HHMMSS]` and includes the files downloaded as well as various files for troubleshooting including (1) verbose_log.txt with detailed logs, (2) dead_letter.txt with a list of any failed files, and (3) html snapshots for debugging.

To see more options run the following
```sh
    pipenv run python epsteinFilePull.py --help
```

---
## Prerequisites
To set up and run scripts in this repository locally, follow these steps:
### Pipenv Dependency
Ensure you have [pipenv](https://pipenv.pypa.io/en/latest/) installed on your system. 

### Install Pipenv Dependencies
Run the following command in the project directory to install all required dependencies:
```sh
    pipenv install
```

To enable the required automated headed verification install Playwright's browsers:

```sh
    pipenv run playwright install
```

If you encounter issues, you can also run:

```sh
    pipenv run python -m playwright install
```

## Purpose
The intent of this project is to:
- Retrieve and archive public documents related to the Epstein case from the DOJ website.
- Provide tools and scripts for efficient, repeatable downloads.
- Support further analysis and research by making these files easily accessible.

## Script: epsteinFilePull.py

This script automates the process of pulling and archiving the millions of documents released by DOJ and by default will download Datasets 8-12 under the DOJ Disclosures section. It efficiently retrieves all relevant files, organizes them for research and analysis, and ensures that the latest disclosures are available for further processing.

Use this script to:
- Download all documents from the January 2026 DOJ Disclosures Datasets or other datasets from DOJ website (see usage section above)
- Organize and store the files in a structured format
- Enable streamlined access for downstream analysis and review

Notes on verification & headed mode:
- The script uses headed Playwright to interact with DOJ pages (age gates / etc).
- HTML snapshots and logs are written to each run's output directory (e.g. `output/YYYYmmdd_HHMMSS`) to aid debugging.
- If a non-recoverable failure occurs or file not found then the name of the file is written to a dead letter queue file named "dead_letter.txt" in that same subfolder.