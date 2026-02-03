import time
import os
import requests
from .headless_interaction_util import find_pdf_url, click_verification_controls, click_age_buttons, save_snapshot


def _log_debug(msg: str, outputDir: str, verbose: bool = False):
    if not verbose:
        return
    try:
        print(f"[DEBUG] {msg}")
    except Exception:
        pass
    try:
        with open(os.path.join(outputDir, 'verbose_log.txt'), 'a', encoding='utf-8') as vf:
            vf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
    except Exception:
        pass


def pull_doj_file_headless(file_url: str, outputDir: str, timeout: int = 30, verbose: bool = False, non_interactive: bool = False, retries: int = 3):
    """Download a single DOJ file using Playwright headless.

    This function focuses on single-file download logic; page interactions are delegated
    to the helpers in headless_interaction_util.
    """
    timeout_ms = int(timeout * 1000)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright not available. Install with 'pipenv install' and run 'pipenv run playwright install' to enable headless mode") from e

    def _try_get_request(page, url, desc='resource'):
        last_exc = None
        for attempt in range(1, max(1, retries) + 1):
            try:
                _log_debug(f"Attempt {attempt} to fetch {desc}: {url}", outputDir, verbose)
                resp = page.request.get(url, timeout=timeout_ms)
                _log_debug(f"Got response (attempt {attempt}) status: {getattr(resp, 'status', 'unknown')}", outputDir, verbose)
                return resp
            except Exception as e:
                last_exc = e
                _log_debug(f"Attempt {attempt} failed to fetch {desc}: {e}", outputDir, verbose)
                if attempt < retries:
                    sleep_time = 1 * (2 ** (attempt - 1))
                    _log_debug(f"Retrying in {sleep_time}s...", outputDir, verbose)
                    time.sleep(sleep_time)
        raise last_exc

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            _log_debug("Launched headless Chromium", outputDir, verbose)
            context = browser.new_context()
            page = context.new_page()
            _log_debug(f"Navigating to {file_url}", outputDir, verbose)
            page.goto(file_url, timeout=30000)
            page.wait_for_load_state('networkidle', timeout=30000)

            file_basename = os.path.basename(file_url.split('?')[0])

            # initial snapshot
            init_snap = save_snapshot(page, outputDir, file_basename, 'init')
            _log_debug(f"Saved initial snapshot {init_snap}", outputDir, verbose)

            # Ensure the DOJ site verification (bot/age gate) is handled for this page
            try:
                from .headless_interaction_util import ensure_page_verified
                verified = ensure_page_verified(page, outputDir, file_basename, verbose, timeout_ms)
                _log_debug(f"Page verification status: {verified}", outputDir, verbose)
                if not verified:
                    msg = f"[WARN] Page not auto-verified for {file_url}"
                    _log_debug(msg, outputDir, verbose)
                    if non_interactive:
                        _log_debug("Non-interactive mode: skipping file due to verification failure", outputDir, verbose)
                        browser.close()
                        return None
                    else:
                        try:
                            import webbrowser
                            webbrowser.open(page.url)
                            resp = input(f"Opened browser for manual verification of {file_url}. Press Enter to continue after verifying, or type 'skip' to skip: ").strip().lower()
                            if resp == 'skip':
                                browser.close()
                                return None
                            # reload and re-check
                            try:
                                page.reload()
                                page.wait_for_load_state('networkidle', timeout=timeout_ms)
                            except Exception:
                                pass
                            verified = ensure_page_verified(page, outputDir, file_basename, verbose, timeout_ms)
                            _log_debug(f"Post-manual verify status: {verified}", outputDir, verbose)
                            if not verified:
                                _log_debug('Still not verified after manual intervention', outputDir, verbose)
                        except Exception:
                            pass
            except Exception:
                pass

            pdf_url = find_pdf_url(page)
            _log_debug(f"Initial pdf_url detection: {pdf_url}", outputDir, verbose)

            try:
                clicked_bot = click_verification_controls(page, outputDir, file_basename, verbose, timeout_ms)
                _log_debug(f"click_verification_controls returned: {clicked_bot}", outputDir, verbose)
                if clicked_bot:
                    page.wait_for_load_state('networkidle', timeout=timeout_ms)
                    bot_snap = save_snapshot(page, outputDir, file_basename, 'bot_after_click')
                    _log_debug(f"Saved bot-after-click snapshot {bot_snap}", outputDir, verbose)
                    pdf_url = find_pdf_url(page)
                    _log_debug(f"pdf_url after bot click: {pdf_url}", outputDir, verbose)
            except Exception as e:
                msg = f"[ERROR] Bot click attempt failed for {file_url}: {e}"
                _log_debug(msg, outputDir, verbose)
                try:
                    with open(os.path.join(outputDir, 'error_log_playwright.txt'), 'a', encoding='utf-8') as ef:
                        ef.write(msg + '\n')
                except Exception:
                    pass

            try:
                age_clicked = click_age_buttons(page, outputDir, file_basename, verbose, timeout_ms)
                _log_debug(f'click_age_buttons returned: {age_clicked}', outputDir, verbose)
                if age_clicked:
                    page.wait_for_load_state('networkidle', timeout=timeout_ms)
                    age_snap = save_snapshot(page, outputDir, file_basename, 'age_after_click')
                    _log_debug(f"Saved age-after-click snapshot {age_snap}", outputDir, verbose)
                    pdf_url = find_pdf_url(page)
                    _log_debug(f'pdf_url after age click: {pdf_url}', outputDir, verbose)
            except Exception as e:
                msg = f"[ERROR] Age click attempt failed for {file_url}: {e}"
                _log_debug(msg, outputDir, verbose)
                try:
                    with open(os.path.join(outputDir, 'error_log_playwright.txt'), 'a', encoding='utf-8') as ef:
                        ef.write(msg + '\n')
                except Exception:
                    pass

                # fallback click attempts
                candidates = page.query_selector_all("button, a, input[type=button], input[type=submit], input[type=checkbox]")
                import re
                pattern = re.compile(r"(?i)\b(i am|i'm|confirm|continue|agree|accept|enter|proceed|verify|not a robot|over 18|18\+|age|cookie|submit)\b")
                clicked = False
                for el in candidates:
                    try:
                        txt = (el.inner_text() or '').strip()
                    except Exception:
                        txt = ''
                    if pattern.search(txt):
                        try:
                            el.click()
                            clicked = True
                            page.wait_for_load_state('networkidle', timeout=timeout_ms)
                            ts2 = time.strftime("%Y%m%d_%H%M%S")
                            with open(os.path.join(outputDir, f'{ts2}_playwright_snapshot_{file_basename}_after_click.html'), 'w', encoding='utf-8') as af:
                                af.write(page.content())
                        except Exception:
                            pass

                if not clicked:
                    more = page.query_selector_all("[id*='age'], [id*='confirm'], [class*='age'], [class*='confirm'], [class*='consent'], [name*='age']")
                    for el in more:
                        try:
                            el.click()
                            clicked = True
                            page.wait_for_load_state('networkidle', timeout=timeout_ms)
                            ts2 = time.strftime("%Y%m%d_%H%M%S")
                            with open(os.path.join(outputDir, f'{ts2}_playwright_snapshot_{file_basename}_after_click.html'), 'w', encoding='utf-8') as af:
                                af.write(page.content())
                            break
                        except Exception:
                            pass

                pdf_url = find_pdf_url(page)

            final_snap = save_snapshot(page, outputDir, file_basename, 'final')
            _log_debug(f"Saved final snapshot {final_snap}", outputDir, verbose)

            if not non_interactive:
                try:
                    user = input(f"Saved snapshots for '{file_url}' in '{outputDir}'. Press Enter to continue, or type 'skip' to skip this file: ").strip().lower()
                    if user == 'skip':
                        browser.close()
                        return None
                except Exception:
                    pass

            tsf = time.strftime("%Y%m%d_%H%M%S")

            if pdf_url:
                try:
                    _log_debug(f"Attempting Playwright fetch for PDF URL: {pdf_url}", outputDir, verbose)
                    api_resp = _try_get_request(page, pdf_url, desc='pdf url')
                    _log_debug(f"Playwright fetch status for {pdf_url}: {getattr(api_resp, 'status', 'unknown')}", outputDir, verbose)
                    if getattr(api_resp, 'status', None) == 200:
                        content = api_resp.body()
                        headers = api_resp.headers
                        filename = os.path.basename(pdf_url.split('?')[0]) or f"download_{tsf}.pdf"
                        browser.close()
                        _log_debug(f"Successfully fetched PDF {filename} ({len(content)} bytes)", outputDir, verbose)
                        return {'content': content, 'filename': filename, 'headers': headers}
                except Exception as e:
                    msg = f"[ERROR] Playwright fetch failed for {pdf_url}: {e}"
                    _log_debug(msg, outputDir, verbose)
                    try:
                        with open(os.path.join(outputDir, 'error_log_playwright.txt'), 'a', encoding='utf-8') as ef:
                            ef.write(msg + '\n')
                    except Exception:
                        pass

            try:
                _log_debug(f"Attempting Playwright nav fetch for {file_url}", outputDir, verbose)
                nav_resp = _try_get_request(page, file_url, desc='nav file')
                _log_debug(f"Playwright nav status: {getattr(nav_resp, 'status', 'unknown')}", outputDir, verbose)
                if getattr(nav_resp, 'status', None) == 200 and 'application/pdf' in (nav_resp.headers.get('content-type') or ''):
                    content = nav_resp.body()
                    headers = nav_resp.headers
                    filename = os.path.basename(file_url.split('?')[0]) or f"download_{tsf}.pdf"
                    browser.close()
                    _log_debug(f"Successfully fetched via nav: {filename} ({len(content)} bytes)", outputDir, verbose)
                    return {'content': content, 'filename': filename, 'headers': headers}
            except Exception as e:
                msg = f"[ERROR] Playwright nav fetch failed for {file_url}: {e}"
                _log_debug(msg, outputDir, verbose)
                try:
                    with open(os.path.join(outputDir, 'error_log_playwright.txt'), 'a', encoding='utf-8') as ef:
                        ef.write(msg + '\n')
                except Exception:
                    pass

            browser.close()
            return None

    except Exception as e:
        try:
            with open(os.path.join(outputDir, 'error_log_playwright.txt'), 'a', encoding='utf-8') as ef:
                ef.write(f"[ERROR] Playwright run failed for {file_url}: {e}\n")
        except Exception:
            pass
        return None
