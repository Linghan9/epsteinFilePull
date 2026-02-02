import time
import os
import webbrowser
import requests


def _log_debug(msg: str, outputDir: str, verbose: bool = False):
    """Write verbose debug messages to stdout and a file when enabled."""
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
    """Headless entry point to get a DOJ file.

    - Uses Playwright headless Chromium to navigate and interact with the page.
    - Saves snapshots (initial and final) into outputDir for debugging.
    - Attempts to auto-click age-gate / consent controls, then looks for a PDF
      embed/iframe/object/link and fetches it using Playwright's request api so
      authentication/cookies are preserved.
    - Respects non_interactive to skip the manual prompt when set.

    Returns a dict on success: { 'content': bytes, 'filename': str, 'headers': dict }
    Returns None on skip or failure.
    """
    # Playwright timeouts are in milliseconds; convert from seconds
    timeout_ms = int(timeout * 1000)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright not available. Install with 'pipenv install' and run 'pipenv run playwright install' to enable headless mode") from e

    # Helper to do request.get with retries and exponential backoff
    def _try_get_request(url, desc='resource'):
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

            # basename to use in consistent snapshot filenames
            file_basename = os.path.basename(file_url.split('?')[0])
            ts = time.strftime("%Y%m%d_%H%M%S")
            init_snap = os.path.join(outputDir, f'{ts}_playwright_snapshot_{file_basename}_init.html')
            with open(init_snap, 'w', encoding='utf-8') as sf:
                sf.write(page.content())
            _log_debug(f"Saved initial snapshot {init_snap}", outputDir, verbose)

            def find_pdf_url(p):
                sel = p.query_selector("embed[type='application/pdf'], object[type='application/pdf'], iframe[src$='.pdf'], a[href$='.pdf']")
                if sel:
                    for attr in ('src', 'data', 'href'):
                        try:
                            val = sel.get_attribute(attr)
                            if val and '.pdf' in val:
                                return p.url if val.strip().startswith('data:') else requests.compat.urljoin(p.url, val)
                        except Exception:
                            continue
                links = p.query_selector_all('a')
                for a in links:
                    try:
                        href = a.get_attribute('href') or ''
                        if href and href.lower().endswith('.pdf'):
                            return requests.compat.urljoin(p.url, href)
                    except Exception:
                        pass
                return None

            pdf_url = find_pdf_url(page)
            _log_debug(f"Initial pdf_url detection: {pdf_url}", outputDir, verbose)

            def click_verification_controls(page_obj):
                """Attempt to find and click verification controls (incl. bot checkbox) across frames."""
                import re
                pattern = re.compile(r"(?i)\b(i am not a robot|i'm not a robot|not a robot|i am not a bot|i'm not a bot|verify|confirm|continue|agree|accept|proceed|over 18|18\+|age|cookie|submit)\b")

                def _check_and_click(el, frame):
                    try:
                        text = (el.inner_text() or '').strip()
                    except Exception:
                        text = ''
                    attrs = []
                    for a in ('aria-label', 'title', 'alt', 'value', 'id', 'name'):
                        try:
                            v = el.get_attribute(a) or ''
                            attrs.append(v)
                        except Exception:
                            pass
                    full = ' '.join([text] + attrs)
                    if pattern.search(full):
                        try:
                            t = el.get_attribute('type') or ''
                            if t.lower() == 'checkbox':
                                try:
                                    el.check()
                                except Exception:
                                    el.click()
                            else:
                                el.click()
                            frame.wait_for_load_state('networkidle', timeout=10000)
                            tsc = time.strftime("%Y%m%d_%H%M%S")
                            snap_path = os.path.join(outputDir, f'{tsc}_playwright_snapshot_{file_basename}_bot_click.html')
                            with open(snap_path, 'w', encoding='utf-8') as bf:
                                bf.write(frame.content())
                            _log_debug(f"Clicked verification control; saved snapshot {snap_path}", outputDir, verbose)
                            return True
                        except Exception as e:
                            _log_debug(f"Exception while clicking verification control: {e}", outputDir, verbose)
                            return False
                    return False

                # Check main frame
                try:
                    candidates = page_obj.query_selector_all("button, a, input[type=button], input[type=submit], input[type=checkbox], label")
                    _log_debug(f"Found {len(candidates)} candidate controls in main frame", outputDir, verbose)
                    for el in candidates:
                        if _check_and_click(el, page_obj):
                            _log_debug("Clicked a control in main frame", outputDir, verbose)
                            return True
                except Exception as e:
                    _log_debug(f"Error scanning main frame for controls: {e}", outputDir, verbose)
                    pass

                # Check nested frames
                try:
                    frames = page_obj.frames
                    _log_debug(f"Found {len(frames)} frames to scan", outputDir, verbose)
                    for f in frames:
                        try:
                            cands = f.query_selector_all("button, a, input[type=button], input[type=submit], input[type=checkbox], label")
                            _log_debug(f"Found {len(cands)} candidate controls in a frame", outputDir, verbose)
                            for el in cands:
                                if _check_and_click(el, f):
                                    _log_debug("Clicked a control in a nested frame", outputDir, verbose)
                                    return True
                        except Exception as e:
                            _log_debug(f"Error scanning a nested frame: {e}", outputDir, verbose)
                            pass
                except Exception as e:
                    _log_debug(f"Error getting frames: {e}", outputDir, verbose)
                    pass

                return False

            # Attempt to click bot/age verification controls first
            try:
                clicked_bot = click_verification_controls(page)
                _log_debug(f"click_verification_controls returned: {clicked_bot}", outputDir, verbose)
                if clicked_bot:
                    # re-check for pdf after clicking
                    page.wait_for_load_state('networkidle', timeout=10000)
                    ts_bot = time.strftime("%Y%m%d_%H%M%S")
                    bot_snap = os.path.join(outputDir, f'{ts_bot}_playwright_snapshot_{file_basename}_bot_after_click.html')
                    with open(bot_snap, 'w', encoding='utf-8') as bf:
                        bf.write(page.content())
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

            # If the age gate is present, try clicking explicit age buttons (Yes)
            def click_age_buttons(page_obj):
                """Click 'Yes' age verification buttons or buttons inside .age-gate-buttons."""
                try:
                    # Try known id
                    btn = page_obj.query_selector('#age-button-yes')
                    if btn:
                        _log_debug('Found #age-button-yes, attempting click', outputDir, verbose)
                        try:
                            btn.click()
                        except Exception:
                            # fallback to JS click
                            page_obj.evaluate("el => el.click()", btn)
                        page_obj.wait_for_load_state('networkidle', timeout=10000)
                        return True
                except Exception as e:
                    _log_debug(f'Exception clicking #age-button-yes: {e}', outputDir, verbose)

                try:
                    # buttons inside .age-gate-buttons
                    group = page_obj.query_selector('.age-gate-buttons')
                    if group:
                        btns = group.query_selector_all('button')
                        for b in btns:
                            try:
                                txt = (b.inner_text() or '').strip().lower()
                            except Exception:
                                txt = ''
                            if txt in ('yes', 'i am 18 or older', 'i am over 18') or 'yes' in txt:
                                _log_debug(f'Clicking age-gate button with text: {txt}', outputDir, verbose)
                                try:
                                    b.click()
                                except Exception:
                                    page_obj.evaluate("el => el.click()", b)
                                page_obj.wait_for_load_state('networkidle', timeout=10000)
                                return True
                except Exception as e:
                    _log_debug(f'Exception scanning .age-gate-buttons: {e}', outputDir, verbose)

                # Check frames for the age button
                try:
                    for f in page_obj.frames:
                        try:
                            btn = f.query_selector('#age-button-yes')
                            if btn:
                                _log_debug('Found #age-button-yes in frame, attempting click', outputDir, verbose)
                                try:
                                    btn.click()
                                except Exception:
                                    f.evaluate("el => el.click()", btn)
                                f.wait_for_load_state('networkidle', timeout=10000)
                                return True
                        except Exception:
                            pass
                except Exception as e:
                    _log_debug(f'Error checking frames for age button: {e}', outputDir, verbose)

                return False

            try:
                age_clicked = click_age_buttons(page)
                _log_debug(f'click_age_buttons returned: {age_clicked}', outputDir, verbose)
                if age_clicked:
                    page.wait_for_load_state('networkidle', timeout=10000)
                    ts_age = time.strftime("%Y%m%d_%H%M%S")
                    age_snap = os.path.join(outputDir, f'{ts_age}_playwright_snapshot_{file_basename}_age_after_click.html')
                    with open(age_snap, 'w', encoding='utf-8') as af:
                        af.write(page.content())
                    _log_debug(f'Saved age-after-click snapshot {age_snap}', outputDir, verbose)
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
                            page.wait_for_load_state('networkidle', timeout=10000)
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
                            page.wait_for_load_state('networkidle', timeout=10000)
                            ts2 = time.strftime("%Y%m%d_%H%M%S")
                            with open(os.path.join(outputDir, f'{ts2}_playwright_snapshot_{file_basename}_after_click.html'), 'w', encoding='utf-8') as af:
                                af.write(page.content())
                            break
                        except Exception:
                            pass

                pdf_url = find_pdf_url(page)

            tsf = time.strftime("%Y%m%d_%H%M%S")
            final_snap = os.path.join(outputDir, f'{tsf}_playwright_snapshot_{file_basename}_final.html')
            with open(final_snap, 'w', encoding='utf-8') as sf:
                sf.write(page.content())
            _log_debug(f"Saved final snapshot {final_snap}", outputDir, verbose)

            if non_interactive:
                _log_debug("Non-interactive mode: continuing without prompt", outputDir, verbose)
            else:
                user = input(f"Saved snapshots for '{file_url}' in '{outputDir}'. Press Enter to continue, or type 'skip' to skip this file: ").strip().lower()
                if user == 'skip':
                    browser.close()
                    return None

            if pdf_url:
                try:
                    _log_debug(f"Attempting Playwright fetch for PDF URL: {pdf_url}", outputDir, verbose)
                    api_resp = _try_get_request(pdf_url, desc='pdf url')
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
                nav_resp = _try_get_request(file_url, desc='nav file')
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
