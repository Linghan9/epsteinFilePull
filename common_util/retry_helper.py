

import time

from .headed_interaction_util import _log_debug


def retry_with_backoff(func, recovery_fun, run_dir: str, verbose: bool, max_retries=3, backoff_factor=1):
    """
    Retry a function with exponential backoff.

    :param func: The function to retry. Should raise an exception on failure.
    :param recovery_fun: A function to call on failure before retrying.
    :param run_dir: The run directory for logging.
    :param verbose: Whether to log verbose messages.
    :param max_retries: Maximum number of retries before giving up.
    :param backoff_factor: Base factor for calculating backoff time (in seconds).
    :return: The result of the function if successful.
    :raises Exception: The last exception raised by the function after exhausting retries.
    """
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_exception = e
            sleep_time = backoff_factor * (2 ** (attempt - 1))
            _log_debug(f"Attempt {attempt} failed with error: {e}. Retrying in {sleep_time} seconds...", run_dir=run_dir, exception=e, verbose=verbose)
            time.sleep(sleep_time)
            recovery_fun(e)
    raise last_exception