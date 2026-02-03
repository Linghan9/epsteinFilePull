import time
import os
import requests


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


def save_snapshot(page, outputDir: str, file_basename: str, event: str, ts: str = None):
    ts = ts or time.strftime("%Y%m%d_%H%M%S")
    snap_path = os.path.join(outputDir, f"{ts}_playwright_snapshot_{file_basename}_{event}.html")
    try:
        with open(snap_path, 'w', encoding='utf-8') as sf:
            sf.write(page.content())
    except Exception:
        pass
    return snap_path


def find_pdf_url(page):
    # Look for common PDF-containing elements
    try:
        sel = page.query_selector("embed[type='application/pdf'], object[type='application/pdf'], iframe[src$='.pdf'], a[href$='.pdf']")
        if sel:
            for attr in ('src', 'data', 'href'):
                try:
                    val = sel.get_attribute(attr)
                    if val and '.pdf' in val:
                        return page.url if val.strip().startswith('data:') else requests.compat.urljoin(page.url, val)
                except Exception:
                    continue
    except Exception:
        pass

    try:
        links = page.query_selector_all('a')
        for a in links:
            try:
                href = a.get_attribute('href') or ''
                if href and href.lower().endswith('.pdf'):
                    return requests.compat.urljoin(page.url, href)
            except Exception:
                pass
    except Exception:
        pass

    return None


def click_verification_controls(page_obj, outputDir: str, file_basename: str, verbose: bool = False, timeout_ms: int = 10000):
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
                frame.wait_for_load_state('networkidle', timeout=timeout_ms)
                tsc = time.strftime("%Y%m%d_%H%M%S")
                snap_path = save_snapshot(frame, outputDir, file_basename, 'bot_click', ts=tsc)
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
    except Exception as e:
        _log_debug(f"Error getting frames: {e}", outputDir, verbose)

    return False


def click_age_buttons(page_obj, outputDir: str, file_basename: str, verbose: bool = False, timeout_ms: int = 10000):
    try:
        btn = page_obj.query_selector('#age-button-yes')
        if btn:
            _log_debug('Found #age-button-yes, attempting click', outputDir, verbose)
            try:
                btn.click()
            except Exception:
                page_obj.evaluate('el => el.click()', btn)
            page_obj.wait_for_load_state('networkidle', timeout=timeout_ms)
            return True
    except Exception as e:
        _log_debug(f'Exception clicking #age-button-yes: {e}', outputDir, verbose)

    try:
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
                        page_obj.evaluate('el => el.click()', b)
                    page_obj.wait_for_load_state('networkidle', timeout=timeout_ms)
                    return True
    except Exception as e:
        _log_debug(f'Exception scanning .age-gate-buttons: {e}', outputDir, verbose)

    try:
        for f in page_obj.frames:
            try:
                btn = f.query_selector('#age-button-yes')
                if btn:
                    _log_debug('Found #age-button-yes in frame, attempting click', outputDir, verbose)
                    try:
                        btn.click()
                    except Exception:
                        f.evaluate('el => el.click()', btn)
                    f.wait_for_load_state('networkidle', timeout=timeout_ms)
                    return True
            except Exception:
                pass
    except Exception as e:
        _log_debug(f'Error checking frames for age button: {e}', outputDir, verbose)

    return False


def ensure_page_verified(page, outputDir: str, file_basename: str, verbose: bool = False, timeout_ms: int = 10000, max_attempts: int = 3):
    """Ensure DOJ site age/bot verification steps are completed for the given page.

    - Checks for known verification cookie or absence of the age-verify block.
    - Attempts clicking verification controls and age buttons across frames with retries.
    - Saves snapshots for each attempt.

    Returns True if verification is detected or successful, False otherwise.
    """
    def _is_verified():
        try:
            # Check cookie
            cookies = page.evaluate("() => document.cookie") or ''
            if 'justiceGovAgeVerified' in cookies:
                return True
        except Exception:
            pass
        try:
            # Check for age success element
            el = page.query_selector('#ageSuccess')
            if el:
                display = page.evaluate("el => window.getComputedStyle(el).display", el)
                if display and display != 'none':
                    return True
        except Exception:
            pass
        try:
            # Detect explicit bot verification challenge elements (do not treat as verified)
            robot_btn = page.query_selector("input[type=button][value*='robot'], button[value*='robot'], input[onclick*='reauth'], [onclick*='reauth']")
            if robot_btn:
                return False
        except Exception:
            pass
        try:
            # If the age block isn't present, we can't assume verified — check for dataset markers instead
            age_block = page.query_selector('#age-verify-block')
            if not age_block:
                # If the page contains the expected dataset list, consider it verified
                list_el = page.query_selector('.item-list, .views-field, .item-list ul')
                if list_el:
                    return True
                # Otherwise, unknown; conservatively treat as not verified so ensure_page_verified will attempt fixes
                return False
            # If present but hidden
            display = page.evaluate("el => window.getComputedStyle(el).display", age_block)
            if display and display == 'none':
                return True
        except Exception:
            pass
        return False

    if _is_verified():
        _log_debug('Page already verified', outputDir, verbose)
        return True

    for attempt in range(1, max_attempts + 1):
        _log_debug(f'Verification attempt {attempt} on page', outputDir, verbose)
        clicked = click_verification_controls(page, outputDir, file_basename, verbose, timeout_ms)
        if clicked:
            save_snapshot(page, outputDir, file_basename, f'verify_clicked_{attempt}')
        # Explicitly try clicking an "I am not a robot" input/button and call reauth() if present
        try:
            robot_btn = page.query_selector("input[type=button][value*='robot'], button[value*='robot'], input[onclick*='reauth'], [onclick*='reauth']")
            if robot_btn:
                _log_debug('Found robot verification button; attempting click', outputDir, verbose)
                try:
                    robot_btn.click()
                except Exception:
                    page.evaluate('el => el.click()', robot_btn)
                save_snapshot(page, outputDir, file_basename, f'robot_clicked_{attempt}')
                try:
                    page.wait_for_load_state('networkidle', timeout=timeout_ms)
                except Exception:
                    pass
            # If a reauth function exists on the page, call it directly as a fallback
            try:
                called = page.evaluate("() => { if (typeof reauth === 'function') { try { reauth(); return true; } catch(e){ return 'error'; } } return false }")
                if called:
                    _log_debug('Called reauth() on page', outputDir, verbose)
                    save_snapshot(page, outputDir, file_basename, f'reauth_called_{attempt}')
                    try:
                        page.wait_for_load_state('networkidle', timeout=timeout_ms)
                    except Exception:
                        pass
            except Exception as e:
                _log_debug(f'Exception invoking reauth(): {e}', outputDir, verbose)
        except Exception as e:
            _log_debug(f'Exception handling robot button/reauth: {e}', outputDir, verbose)

        age_clicked = click_age_buttons(page, outputDir, file_basename, verbose, timeout_ms)
        if age_clicked:
            save_snapshot(page, outputDir, file_basename, f'age_clicked_{attempt}')
        try:
            page.wait_for_load_state('networkidle', timeout=timeout_ms)
        except Exception:
            pass
        if _is_verified():
            _log_debug('Page verification succeeded', outputDir, verbose)
            return True
        time.sleep(1 * attempt)
    _log_debug('Page verification failed after attempts', outputDir, verbose)
    return False
