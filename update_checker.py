"""Lightweight GitHub release update check.

Best-effort and non-blocking by design: any failure (no network, rate limit,
unexpected payload) is swallowed and treated as "no update", so it can never
break startup or the settings window.
"""
import re
import requests

import utils
from version import __version__, GITHUB_REPO

logger = utils.setup_logger()

# Direct link that always redirects to the newest published release.
LATEST_RELEASE_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"

_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def _parse_version(text):
    """Turn a tag like 'v3.6.0' or '3.6.0-beta' into a comparable tuple."""
    if not text:
        return None
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def get_latest_release(timeout=5):
    """Return the latest release tag string from GitHub, or None on any failure."""
    try:
        response = requests.get(
            _API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"GLaSSIST/{__version__}",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        tag = (response.json() or {}).get("tag_name")
        if tag:
            logger.info(f"Update check: latest release on GitHub is {tag}")
        return tag
    except Exception as e:
        logger.info(f"Update check skipped (could not reach GitHub): {e}")
        return None


def check_for_update(timeout=5):
    """Return the latest tag string if it is newer than the running version, else None."""
    latest_tag = get_latest_release(timeout=timeout)
    latest = _parse_version(latest_tag)
    current = _parse_version(__version__)
    if not latest or not current:
        return None
    if latest > current:
        logger.info(f"Update available: {__version__} -> {latest_tag}")
        return latest_tag
    logger.info(f"No update: running {__version__}, latest {latest_tag}")
    return None
