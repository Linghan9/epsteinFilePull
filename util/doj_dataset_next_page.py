
import time
import playwright
import requests

from common_util.headed_interaction_util import click_verification_controls, save_snapshot, _log_debug


def navigate_to_next_page(
        page: playwright.sync_api.Page,
        page_number: int,
        file_basename: str,
        run_dir: str,
        verbose: bool,
        timeout_ms: int = 30000,
        retries: int = 3):
    """Navigate to the next page URL with retries.
    """
    save_snapshot(page, run_dir, file_basename, f'start_find_next_page_from_page_{page_number}', ts=time.strftime("%Y%m%d_%H%M%S"))
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
    except Exception as e:
        _log_debug("Error locating next page link. Exception " + str(e), run_dir, verbose)
        pass

    # Advance to next page if available
    if next_link:
        try:
            href = None
            try:
                href = next_link.get_attribute('href') or None
            except Exception:
                _log_debug("Error getting href from next page link: " + str(e), run_dir, verbose)
                href = None

            _log_debug('Clicking next page', run_dir, verbose)
            # Prefer direct navigation when an href is available so we can capture response/status
            resp = None
            full_next = None
            if href:
                full_next = requests.compat.urljoin(page.url, href)
                _log_debug(f"Attempting navigation to next page URL: full_next={full_next} - page.url={page.url} - href={href}", run_dir, verbose)
                try:
                    resp = page.goto(full_next, timeout=30000)
                    try:
                        _log_debug(f"Next page navigation status: {getattr(resp, 'status', 'unknown')}", run_dir, verbose)
                        return True
                    except Exception:
                        _log_debug("Error getting status from next page response: " + str(e), run_dir, verbose)
                        pass
                    page.wait_for_load_state('networkidle', timeout=timeout_ms)
                except Exception as e:
                        _log_debug(f"Direct goto to next page failed. falling back to click", run_dir, exception=e, verbose=verbose)
                try:
                    next_link.click()
                    page.wait_for_load_state('networkidle', timeout=timeout_ms)
                except Exception as e2:
                    _log_debug(f"Click fallback failed.", run_dir, exception=e2, verbose=verbose)
                    pass
            else:
                next_link.click()
                page.wait_for_load_state('networkidle', timeout=timeout_ms)

                ts = time.strftime("%Y%m%d_%H%M%S")
                save_snapshot(page, run_dir, file_basename, f'page_{page_number+1}', ts=ts)

                # Detect Access Denied / WAF blocks
                page_content = (page.content() or '').lower()
                blocked = False
                # if 'access denied' in page_content or 'errors.edgesuite.net' in page_content:
                #     blocked = True
                if resp and getattr(resp, 'status', None) in (401, 403, 451, 503):
                    blocked = True

                if blocked:
                    _log_debug(f"Detected WAF/Access Denied on page {page_number+1} (url={full_next})", run_dir, verbose)
                try:
                    click_verification_controls(page, run_dir, file_basename)
                except Exception as e:
                    _log_debug(f"Failed to verify page after WAF detection", run_dir, exception=e, verbose=verbose)
                    pass

                # Retry once via direct goto if we have href
                try:
                    if full_next:
                        _log_debug(f"Retrying direct goto to next page URL: {full_next}", run_dir, verbose)
                        resp2 = page.goto(full_next, timeout=30000)
                        try:
                            _log_debug(f"Retry status: {getattr(resp2, 'status', 'unknown')}", run_dir, verbose)
                        except Exception as e:
                            _log_debug(f"Failed to get status from retry response: {resp2}", run_dir, exception=e, verbose=verbose)
                            pass
                        page.wait_for_load_state('networkidle', timeout=timeout_ms)
                        ts2 = time.strftime("%Y%m%d_%H%M%S")
                        save_snapshot(page, run_dir, file_basename, f'page_{page_number+1}_retry', ts=ts2)
                        page_content2 = (page.content() or '').lower()
                        if 'access denied' in page_content2 or \
                            'errors.edgesuite.net' in page_content2 or \
                            (resp2 and getattr(resp2, 'status', None) in (401,403,451,503)):
                            _log_debug('Still blocked after retry; stopping pagination for this dataset', run_dir, verbose)
                            return False
                        else:
                            page.reload()
                            page.wait_for_load_state('networkidle', timeout=timeout_ms)
                            ts2 = time.strftime("%Y%m%d_%H%M%S")
                            save_snapshot(page, run_dir, file_basename, f'page_{page_number+1}_retry', ts=ts2)
                            page_content2 = (page.content() or '').lower()
                            if 'access denied' in page_content2 or 'errors.edgesuite.net' in page_content2:
                                _log_debug('Still blocked after retry; stopping pagination for this dataset', run_dir, verbose)
                                return False
                except Exception as e:
                    _log_debug(f"Retry attempt after WAF detection failed.", run_dir, exception=e, verbose=verbose)
                    return False

                # otherwise return True to continue to next page loop
                return True
        except Exception as e:
            _log_debug(f"Failed to advance to next page.", exception=e, run_dir=run_dir, verbose=verbose)
            return False

