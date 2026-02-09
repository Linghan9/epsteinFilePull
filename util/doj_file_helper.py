import os
from playwright.sync_api import Page

from common_util.retry_helper import retry_with_backoff
from common_util.headed_interaction_util import TryGetRequestException, _log_debug, _try_get_request, click_verification_controls, click_age_buttons

def handle_file_fetch_failure(page: Page, file_url: str, exception: TryGetRequestException, run_dir: str, verbose: bool):
    _log_debug(f"Handling file fetch failure for {file_url}. Exception: {exception}", exception=exception, run_dir=run_dir, verbose=verbose) 
    if not isinstance(exception, TryGetRequestException):
        _log_debug(f"Unexpected exception type: {type(exception)}", exception=exception, run_dir=run_dir, verbose=verbose)
    else:
        resp = exception.response
        if resp is not None:
            _log_debug(f"Handling file fetch failure due to response status: {getattr(resp, 'status', 'unknown')}, headers: {getattr(resp, 'headers', {})}", run_dir=run_dir, verbose=verbose)
            if (resp.status == 404):
                _log_debug(f"File not found (404) for URL: {file_url}. No further retries will be attempted. File was removed or inaccessible.", run_dir=run_dir, verbose=verbose)
                raise exception  # re-raise to stop retries
            else:
                _log_debug(f"Non-404 failure, will attempt verification controls before next retry.", run_dir=run_dir, verbose=verbose)
                file_basename = os.path.basename(file_url.split('?')[0])
                click_verification_controls(page, run_dir=run_dir, file_basename=file_basename, verbose=verbose)
                click_age_buttons(page, run_dir=run_dir, file_basename=file_basename, verbose=verbose)

def file_already_saved(file_url: str, run_dir: str) -> bool:
    file_name = file_url.rsplit('/', 1)[-1]
    out_dir = os.path.dirname(run_dir) # files are saved in the parent directory of run_dir
    outpath = os.path.join(out_dir, file_name)
    return os.path.exists(outpath)                

"""Download a single DOJ file using Playwright page provided."""
def pull_doj_file(page: Page, 
        file_url: str, 
        run_dir: str, 
        timeout_ms: int = 30000, 
        verbose: bool = False, 
        retries: int = 3):

    # Retry loop with verification controls if needed
    verification_controls_attempted = False # Track if we've tried verification controls yet
    while (True):
        resp = retry_with_backoff(
            func=lambda: 
                _try_get_request(page, file_url, run_dir, verbose, timeout_ms=timeout_ms), 
            recovery_fun=lambda e: 
                handle_file_fetch_failure(page, file_url, e, run_dir, verbose),
        run_dir=run_dir, 
        verbose=verbose,
        max_retries=retries)
        
        file_basename = os.path.basename(file_url.split('?')[0])

        if getattr(resp, 'status', None) != 200 and verification_controls_attempted:
            _log_debug(f"Retry attempts exhausted for {file_url} with status {getattr(resp, 'status', 'unknown')} after attempting verification controls.", run_dir=run_dir, verbose=verbose) 
            raise RuntimeError(f"Failed to fetch {file_url} after retries and verification control attempt.")
        else:
            expected_content_types = ['application/pdf', 'video/mp4', 'video/webm', 'video/mpeg', 'm4a', 'wav']
            if any(contentType in resp.headers.get('content-type') for contentType in expected_content_types):
                content = resp.body()
                headers = resp.headers
                filename = os.path.basename(file_url.split('?')[0])
                _log_debug(f"Fetch succeeded for {file_url}: {filename} ({len(content)} bytes)", run_dir=run_dir, verbose=verbose)
                return {'content': content, 'filename': filename, 'headers': headers}
            elif not verification_controls_attempted:
                _log_debug(f"Attempting verification controls for {file_url}", run_dir=run_dir, verbose=verbose)
                click_verification_controls(page, run_dir=run_dir, file_basename=file_basename, verbose=verbose)
                click_age_buttons(page, run_dir=run_dir, file_basename=file_basename, verbose=verbose)
                verification_controls_attempted = True
            else:
                _log_debug(f"Unexpected content-type for {file_url}: {resp.headers.get('content-type')}.", run_dir=run_dir, verbose=verbose)
                raise RuntimeError(f"Unexpected content-type for {file_url}: {resp.headers.get('content-type')}.")