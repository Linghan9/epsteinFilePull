import time
import os
import argparse
from util import doj_dataset_helper

def main():
	parser = argparse.ArgumentParser(description='Download DOJ release files')
	parser.add_argument('--verbose', action='store_true', help='Enable verbose debug output', default=True)
	parser.add_argument('--non-interactive', action='store_true', dest='non_interactive', help='Run without prompting to continue (useful for CI)', default = True)
	args = parser.parse_args()
	verbose = args.verbose
	non_interactive = args.non_interactive
	# Create run directory and an 'output' subdirectory for files and snapshots
	timestamp = time.strftime("%Y%m%d_%H%M%S")
	# Put all runs under a top-level ./output directory
	base_output = os.path.join(os.getcwd(), 'output')
	os.makedirs(base_output, exist_ok=True)
	run_dir = os.path.join(base_output, f"jan2026ReleasePull_{timestamp}")
	os.makedirs(run_dir, exist_ok=True)
	output_dir = run_dir

	# Datasets to process (datasets 8-12)
	datasets = [
		"data-set-8-files",
		"data-set-9-files",
		"data-set-10-files",
		"data-set-11-files",
		"data-set-12-files",
	]

	base_url = "https://www.justice.gov/epstein/doj-disclosures"

	print(f"Run directory: {run_dir}; outputs in: {output_dir}")

	# Use dataset-level helper to crawl pages and download files (5 per page, up to 5 pages for testing)
	doj_dataset_helper.pull_doj_dataset_headless(datasets, base_url, output_dir, per_page_limit=1, timeout=30, verbose=verbose, non_interactive=non_interactive, max_pages=5)

main()