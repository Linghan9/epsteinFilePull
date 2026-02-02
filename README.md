## Epstein File Pull
This repository is designed to automate the process of pulling and downloading Epstein-related files from the U.S. Department of Justice (DOJ) website.
### Usage
---
---
## Running Locally
To set up and run scripts in this repository locally, follow these steps:
### Prerequisites
- Ensure you have [pipenv](https://pipenv.pypa.io/en/latest/) installed on your system.
### Install Dependencies
Run the following command in the project directory to install all required dependencies:
	pipenv install

### Optional: Enable headless verification (Playwright)
To enable automated headless verification for sites that require manual interaction (age-gates / bot checks), install Playwright's browsers after installing dependencies:

	pipenv run playwright install

If you encounter issues, you can also run:

	pipenv run python -m playwright install

This step is optional but recommended for automated bypass attempts.
### Running Scripts
To run any of the Python scripts in this repository, use:
	pipenv run python [script name]
For example, to run the January 2026 release pull script:
	pipenv run python jan2026ReleasePull.py

Run with verbose debug logging:

	pipenv run python jan2026ReleasePull.py --verbose
## Epstein File Pull

This repository is designed to automate the process of pulling and downloading Epstein-related files from the U.S. Department of Justice (DOJ) website.

### Purpose
The intent of this project is to:
- Retrieve and archive public documents related to the Epstein case from the DOJ website.
- Provide tools and scripts for efficient, repeatable downloads.
- Support further analysis and research by making these files easily accessible.

### Usage
Scripts and tools in this repository are intended for research and archival purposes only. Please ensure you comply with all relevant terms of use and legal requirements when accessing government data.

---
For more details, see the main project documentation or contact the repository maintainer.

---

## Script: jan2026ReleasePull.py

This script automates the process of pulling and archiving the millions of documents released in January 2026 under the DOJ Disclosures section, specifically Datasets 9–12. It efficiently retrieves all relevant files, organizes them for research and analysis, and ensures that the latest disclosures are available for further processing.

Use this script to:
- Download all documents from the January 2026 DOJ Disclosures Datasets 9–12
- Organize and store the files in a structured format
- Enable streamlined access for downstream analysis and review

Notes on verification & headless mode:
- The script uses headless Playwright to interact with DOJ pages (age gates / PDF viewers) and will attempt to automate interactions when possible.
- HTML snapshots and logs are written to each run's output directory (e.g. `jan2026ReleasePull_YYYYmmdd_HHMMSS`) to aid debugging.
- In some cases manual interaction is required; the script will pause and prompt you before continuing.
