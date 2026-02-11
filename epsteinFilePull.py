import time
import os
import argparse
import util.doj_dataset_helper as doj_dataset_helper

def main():

    # Obtain Playwright up front as this is a hard requirement
    try:
        # Import locally so the function can be used in environments without Playwright installed for parts that don't need it
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright not available. Install with 'pipenv install' and run 'pipenv run playwright install' to enable headless mode") from e

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Download DOJ release files')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose debug output', default=True)
    parser.add_argument('--datasets', nargs='*', help='Names of datasets to process (default: datasets 8-12)', default=[])
    parser.add_argument('--max-pages', type=int, help='Maximum number of pages to process per dataset (default: all)', default=None)
    parser.add_argument('--per-page-limit', type=int, help='Maximum number of files to download per page (default: all)', default=None)
    parser.add_argument('--doj-section', type=str, help='Section of the DOJ site to target (default: doj-disclosures)', default='doj-disclosures')
    args = parser.parse_args()
    verbose = args.verbose
    max_pages = args.max_pages
    per_page_limit = args.per_page_limit
    doj_section = args.doj_section
    if args.datasets and len(args.datasets) > 0:
        datasets = args.datasets
    else:
        datasets = [
            "data-set-8-files"
        ]
    print(f"Datasets to process: {datasets}")

    # Create 'output' subdirectory and run specific subfolder for files and snapshots
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(os.getcwd(), 'output')
    os.makedirs(output_dir, exist_ok=True)
    run_dir = os.path.join(output_dir, f"{timestamp}")
    os.makedirs(run_dir, exist_ok=True)
    print(f"Run directory: {run_dir}; outputs in: {output_dir}")

    # Use dataset-level helper to crawl pages and download files
    base_url = f"https://www.justice.gov/epstein/{doj_section}"
    with sync_playwright() as playwright:
        doj_dataset_helper.pull_doj_dataset_headed(
            playwright=playwright,
            datasets=datasets, 
            base_url=base_url,
            run_dir=run_dir, 
            per_page_limit=per_page_limit, 
            timeout_ms=30000, 
            verbose=verbose, 
            max_pages=max_pages)

main()