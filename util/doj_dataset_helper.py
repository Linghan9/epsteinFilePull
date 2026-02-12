import time
import os
from playwright.sync_api import Page
import requests
from typing import List

from common_util.headed_interaction_util import _append_dead_letter, _log_debug, click_verification_controls, ensure_page_verified, print_request_details, save_snapshot
from common_util import headed_interaction_util
from .doj_dataset_next_page import navigate_to_next_page
from .doj_file_helper import file_already_saved, pull_doj_file


def pull_doj_dataset_headed(playwright: Page,
        datasets: List[str], 
        base_url: str, 
        run_dir: str, 
        per_page_limit: int | None = None, 
        timeout_ms: int = 30000, 
        verbose: bool = False, 
        max_pages: int | None = None):
    
    """Navigate DOJ dataset pages and download files via headed browser.

    For each dataset path, navigate to {base_url}/{path}, and on each page download up to
    `per_page_limit` files from the item-list (or all items if no `per_page_limit` ). If a "Next page" link exists, click it and repeat.

    - `max_pages` (optional): stop after processing this many pages for the dataset. Use for short test runs.

    This helper currently delegates single-file downloads to `pull_doj_file_headless`.
    """
    headed_interaction_util.schedule.run_pending()  # Run any pending scheduled tasks, including Playwright cleanup if scheduled, before starting dataset processing
    _log_debug(f"Starting DOJ dataset pull for base URL: {base_url}", run_dir, verbose)
    for path in datasets:
        ds_url = requests.compat.urljoin(base_url + '/', path)
        _log_debug(f"Starting dataset: {ds_url}", run_dir, verbose)
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.on("request", print_request_details)

        page.goto(ds_url, timeout=30000)
        page.wait_for_load_state('networkidle', timeout=30000)
        file_basename = (path.rstrip('/').split('/')[-1]) or 'dataset'
        ts = time.strftime("%Y%m%d_%H%M%S")
        save_snapshot(page, run_dir, file_basename, 'init', ts=ts)
        _log_debug("Hello!!! This is a debug message to confirm that the logging system is working correctly.", run_dir, verbose)

        try:
            # Ensure page verification (bot/age) before scraping items
            verified = ensure_page_verified(page, run_dir, file_basename, verbose, timeout_ms)
            _log_debug(f"Page verification status: {verified}", run_dir, verbose)
            if not verified:
                _log_debug(f"Verification failed for dataset {ds_url}. Exiting. See logs and snapshots for details.", run_dir, verbose)
                browser.close()
                break

            # page loop
            page_number = 0
            while True:
                headed_interaction_util.schedule.run_pending()  # Run any pending scheduled tasks, including resetting the cleanup flag if needed
                if headed_interaction_util.playwright_cleanup_scheduled:
                    _log_debug("Performing scheduled Playwright cleanup to manage memory usage.", run_dir, verbose)
                    context.storage_state(path=os.path.join(run_dir, f'context_storage_state_page_{page_number}.json'))
                    current_url = page.url
                    context.close()
                    context = browser.new_context(storage_state=os.path.join(run_dir, f'context_storage_state_page_{page_number}.json'))
                    page = context.new_page()
                    page.on("request", print_request_details)
                    page.goto(current_url, timeout=30000)
                    page.wait_for_load_state('networkidle', timeout=30000)
                    headed_interaction_util.playwright_cleanup_scheduled = False
                page_number += 1
                if max_pages is not None and page_number > max_pages:
                    _log_debug(f"Reached max_pages ({max_pages}), stopping pagination for {path}", run_dir, verbose)
                    break
                _log_debug(f"Processing page {page_number} for {path} (max {max_pages})", run_dir, verbose)
                # collect item links
                anchors = page.query_selector_all('.item-list a')
                _log_debug(f"Found {len(anchors)} items on page", run_dir, verbose)
                count = 0
                for a in anchors:
                    if per_page_limit is not None and count >= per_page_limit:
                        _log_debug(f"Reached per_page_limit ({per_page_limit}), stopping processing for page {page_number} of {path}", run_dir, verbose)
                        break
                    try:
                        href = a.get_attribute('href') or ''
                        if not href:
                            continue
                        file_url = requests.compat.urljoin(page.url, href)
                        _log_debug(f"Attempting file {file_url}", run_dir, verbose)
                        if file_already_saved(file_url, run_dir):
                            _log_debug(f"File already saved, skipping: {file_url}", run_dir, verbose)
                            continue
                        try:
                            res = pull_doj_file(page, file_url, run_dir, timeout_ms=timeout_ms, verbose=verbose, retries=3)
                        except Exception as e:
                            _log_debug(f"Failed to fetch {file_url} after exhausting retry attempts.", run_dir, exception=e, verbose=verbose)
                            _append_dead_letter(file_url, run_dir)
                            continue

                        if res is None:
                            _log_debug(f"No result for file {file_url}, after exhausting retries.", run_dir, verbose)
                            continue

                        # Save content to file if available
                        content = res.get('content')
                        fname = res.get('filename')
                        if content:
                            out_dir = os.path.dirname(run_dir)  # Save files one level up from snapshots
                            outpath = os.path.join(out_dir, fname)
                            with open(outpath, 'wb') as wf:
                                wf.write(content)
                                _log_debug(f"Saved: {outpath} ({len(content)} bytes)", run_dir, verbose)
                        else:
                            _log_debug(f"No content found for file after exhausting retry attempts: {file_url}", run_dir, verbose)
                        
                        count += 1
                    except Exception as e:
                        _log_debug(f"Error downloading file {a} after exhausting retries. Skipping this file.", run_dir, exception=e, verbose=verbose)
                        pass

                # After iterating all items, attempt to navigate to next page link
                attempted_next_page_verification_controls = False
                next_page_found = False
                while True:
                    next_page_found = navigate_to_next_page(
                        page=page,
                        page_number=page_number,
                        file_basename=file_basename,
                        run_dir=run_dir,
                        verbose=verbose,
                    timeout_ms=timeout_ms)

                    if next_page_found:
                        _log_debug(f"Next page found, navigating to page {page_number + 1} for {path}", run_dir=run_dir, verbose=verbose)
                        break

                    # if not next_page_found and not attempted_next_page_verification_controls:
                    #     _log_debug('No next page found, attempting verification controls before concluding pagination.', run_dir=run_dir, verbose=verbose)
                    #     click_verification_controls(page, run_dir=run_dir, file_basename=file_basename, verbose=verbose)
                    #     attempted_next_page_verification_controls = True
                    # else:
                    _log_debug('No next page found after attempting verification controls, attempting to increment the page in the url instead.', run_dir=run_dir, verbose=verbose)
                    direct_page_url = ds_url + '?page=' + str(page_number + 1)
                    _log_debug(f"Attempting direct URL navigation to next page: {direct_page_url}", run_dir=run_dir, verbose=verbose)
                    page.goto(direct_page_url, timeout=30000)
                    break

        except Exception as e:
            _log_debug(f"Error processing dataset {ds_url}. Moving to next dataset.", run_dir=run_dir, exception=e, verbose=verbose)

        browser.close()
