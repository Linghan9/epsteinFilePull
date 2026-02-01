import time
import os
import webbrowser
import requests

"""Helper to handle HTML responses requiring manual verification.

Usage:
    response = ensure_media_response(file_url, initial_response, outputDir, timeout=30)

The method checks the response to confirm supported media is present or if not
opens the provided URL in the user's default browser and prompts them to
complete any verification (age gate / bot check). It will retry the GET until
a media response is returned or the user types 'skip'. Snapshots of the HTML
response are written to disk in `outputDir` for debugging. If specified, the
provided `timeout` is used for requests, otherwise a default timeout is leveraged.
"""

def try_headless_bypass(file_url: str, outputDir: str, timeout: int = 30):
    """Attempt to navigate the page headlessly and click likely verification controls.

    Returns a requests.Response if it was able to reach a non-HTML resource after
    interacting with the page, otherwise returns None.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright not available. Install with 'pip install playwright' and run 'playwright install' to enable headless bypass") from e

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(file_url, timeout=30000)
            page.wait_for_load_state('networkidle', timeout=30000)

            ts = time.strftime("%Y%m%d_%H%M%S")
            snap = os.path.join(outputDir, f'playwright_snapshot_{file_url.split('/')[-1]}_{ts}.html')
            with open(snap, 'w', encoding='utf-8') as sf:
                sf.write(page.content())

            # Look for likely controls to click
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
                        with open(os.path.join(outputDir, f'playwright_after_click_{ts2}.html'), 'w', encoding='utf-8') as af:
                            af.write(page.content())
                    except Exception:
                        pass

            # Try additional selectors if nothing clicked
            if not clicked:
                more = page.query_selector_all("[id*='age'], [id*='confirm'], [class*='age'], [class*='confirm'], [class*='consent'], [name*='age']")
                for el in more:
                    try:
                        el.click()
                        clicked = True
                        page.wait_for_load_state('networkidle', timeout=10000)
                        ts2 = time.strftime("%Y%m%d_%H%M%S")
                        with open(os.path.join(outputDir, f'playwright_after_click_{ts2}.html'), 'w', encoding='utf-8') as af:
                            af.write(page.content())
                        break
                    except Exception:
                        pass

            final_url = page.url
            browser.close()

            # Try fetching the final URL to get a requests.Response
            try:
                final_response = requests.get(final_url, allow_redirects=True, timeout=timeout)
                return final_response
            except Exception as e:
                try:
                    with open(os.path.join(outputDir, 'error_log_playwright.txt'), 'a', encoding='utf-8') as ef:
                        ef.write(f"[ERROR] Playwright bypass fetch failed for {final_url}: {e}\n")
                except Exception:
                    pass
                return None

    except Exception as e:
        try:
            with open(os.path.join(outputDir, 'error_log_playwright.txt'), 'a', encoding='utf-8') as ef:
                ef.write(f"[ERROR] Playwright run failed for {file_url}: {e}\n")
        except Exception:
            pass
        return None

def ensure_media_response(file_url: str, response: requests.Response, outputDir: str,timeout: int = 30):
    attemptCount = 1
    while True:
        is_html = 'text/html' in response.headers.get('content-type', '').lower() or '<html' in response.text.lower()
        if not is_html:
            return response

        snapshot_path = f'{outputDir}/error_html_snapshot_{file_url.split("/")[-1]}_attempt{attemptCount}.html'
        attemptCount += 1
        try:
            with open(snapshot_path, 'w', encoding='utf-8') as sf:
                sf.write(response.text)
        except Exception:
            # If snapshot fails, continue; don't block the user
            pass

        # Attempt headless bypass using Playwright (if available)
        try:
            bypass_resp = try_headless_bypass(file_url, outputDir, timeout)
            if bypass_resp is not None:
                # If bypass returned a non-HTML response, continue processing with it
                is_html = 'text/html' in bypass_resp.headers.get('content-type', '').lower() or '<html' in bypass_resp.text.lower()
                if not is_html:
                    return bypass_resp
        except Exception as e:
            msg = f"[NOTICE] Headless bypass attempt failed or not available: {e}"
            print(msg)
            try:
                with open(os.path.join(outputDir, 'error_log_playwright.txt'), 'a', encoding='utf-8') as ef:
                    ef.write(msg + '\n')
            except Exception:
                pass

        # Fallback to manual browser interaction
        print(f"[NOTICE] Received HTML response for {file_url}. Opening browser for manual verification: {file_url}")
        webbrowser.open(file_url)

        user = input("Please complete verification in the browser, then press Enter to retry (or type 'skip' to skip this file). If browser does not automatically open then please manually open in a desired browser and complete the required interaction: ").strip().lower()
        if user == 'skip':
            return None

        # Retry the request once per loop iteration
        try:
            response = requests.get(file_url, allow_redirects=True, timeout=timeout)
        except Exception as e:
            err = f"[ERROR] Exception while retrying {file_url}: {e}"
            print(err)
            try:
                with open(os.path.join(outputDir, 'error_log_retry.txt'), 'a', encoding='utf-8') as ef:
                    ef.write(err + '\n')
            except Exception:
                pass

            cont = input("Retry? Press Enter to retry, type 'skip' to skip: ").strip().lower()
            if cont == 'skip':
                return None
            # otherwise loop and retry
