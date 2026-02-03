import time
import os
import requests
from typing import List

from .doj_file_helper import pull_doj_file_headless
from .headless_interaction_util import save_snapshot


def _log(msg: str, outputDir: str, verbose: bool = False):
    if verbose:
        try:
            print(f"[DEBUG] {msg}")
        except Exception:
            pass
    try:
        with open(os.path.join(outputDir, 'verbose_log.txt'), 'a', encoding='utf-8') as vf:
            vf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
    except Exception:
        pass


def pull_doj_dataset_headless(dataset_paths: List[str], base_url: str, outputDir: str, per_page_limit: int = 5, timeout: int = 30, verbose: bool = False, non_interactive: bool = False):
    """Navigate DOJ dataset pages and download files.

    For each dataset path, navigate to {base_url}/{path}, and on each page download up to
    `per_page_limit` files from the item-list. If a "Next page" link exists, click it and repeat.

    This helper currently delegates single-file downloads to `pull_doj_file_headless`.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright not available. Install with 'pipenv install' and run 'pipenv run playwright install' to enable headless mode") from e

    timeout_ms = int(timeout * 1000)

    for path in dataset_paths:
        ds_url = requests.compat.urljoin(base_url + '/', path)
        _log(f"Starting dataset: {ds_url}", outputDir, verbose)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            page.goto(ds_url, timeout=30000)
            page.wait_for_load_state('networkidle', timeout=30000)
            file_basename = (path.rstrip('/').split('/')[-1]) or 'dataset'
            ts = time.strftime("%Y%m%d_%H%M%S")
            save_snapshot(page, outputDir, file_basename, 'init', ts=ts)

            # Ensure page verification (bot/age) before scraping items
            try:
                from .headless_interaction_util import ensure_page_verified
                verified = ensure_page_verified(page, outputDir, file_basename, verbose, timeout_ms)
                _log(f"Page verification status: {verified}", outputDir, verbose)
                if not verified:
                    if non_interactive:
                        _log(f"Non-interactive: verification failed, skipping dataset page {ds_url}", outputDir, verbose)
                        browser.close()
                        break
                    else:
                        try:
                            import webbrowser
                            webbrowser.open(page.url)
                            resp = input(f"Opened browser for manual verification of {ds_url}. Press Enter to continue after verifying, or type 'skip' to skip this dataset/page: ").strip().lower()
                            if resp == 'skip':
                                browser.close()
                                break
                            try:
                                page.reload()
                                page.wait_for_load_state('networkidle', timeout=timeout_ms)
                            except Exception:
                                pass
                            verified = ensure_page_verified(page, outputDir, file_basename, verbose, timeout_ms)
                            _log(f"Post-manual verify status: {verified}", outputDir, verbose)
                            if not verified:
                                _log(f"Still not verified after manual intervention, skipping", outputDir, verbose)
                                break
                        except Exception:
                            pass
            except Exception:
                pass

            # page loop
            page_number = 0
            while True:
                page_number += 1
                _log(f"Processing page {page_number} for {path}", outputDir, verbose)

                # collect item links
                anchors = page.query_selector_all('.item-list a')
                _log(f"Found {len(anchors)} items on page", outputDir, verbose)
                count = 0
                for a in anchors:
                    if count >= per_page_limit:
                        break
                    try:
                        href = a.get_attribute('href') or ''
                        if not href:
                            continue
                        file_url = requests.compat.urljoin(page.url, href)
                        _log(f"Attempting file {file_url}", outputDir, verbose)
                        # Reuse the dataset-level context so session cookies and verification persist across file downloads
                        res = pull_doj_file_headless(file_url, outputDir, timeout=timeout, verbose=verbose, non_interactive=non_interactive, context=context)
                        if res:
                            content = res.get('content')
                            fname = res.get('filename')
                            if content:
                                outpath = os.path.join(outputDir, fname)
                                with open(outpath, 'wb') as wf:
                                    wf.write(content)
                                _log(f"Saved: {outpath} ({len(content)} bytes)", outputDir, verbose)
                        else:
                            _log(f"Skipped or failed: {file_url}", outputDir, verbose)
                        count += 1
                    except Exception as e:
                        _log(f"Error downloading file {a}: {e}", outputDir, verbose)

                # try to find the next page link
                next_link = None
                try:
                    cand = page.query_selector("a.usa-pagination__next-page")
                    if cand:
                        next_link = cand
                    else:
                        # look for 'Next' text anchors
                        links = page.query_selector_all('a')
                        for l in links:
                            try:
                                txt = (l.inner_text() or '').strip().lower()
                            except Exception:
                                txt = ''
                            if txt.startswith('next') or 'next' == txt:
                                next_link = l
                                break
                except Exception:
                    pass

                if next_link:
                    try:
                        _log('Clicking next page', outputDir, verbose)
                        next_link.click()
                        page.wait_for_load_state('networkidle', timeout=timeout_ms)
                        ts = time.strftime("%Y%m%d_%H%M%S")
                        save_snapshot(page, outputDir, file_basename, f'page_{page_number+1}', ts=ts)
                        continue
                    except Exception as e:
                        _log(f"Failed to advance to next page: {e}", outputDir, verbose)
                        break
                else:
                    _log('No next page found, moving to next dataset', outputDir, verbose)
                    break

            browser.close()
