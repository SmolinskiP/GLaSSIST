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
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"

_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": f"GLaSSIST/{__version__}",
}


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
        response = requests.get(_API_URL, headers=_HEADERS, timeout=timeout)
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


def get_releases(limit=10, timeout=5):
    """Return the newest published releases (tag, name, date, notes, url), or None on any failure."""
    try:
        response = requests.get(_RELEASES_API_URL, headers=_HEADERS,
                                params={"per_page": limit}, timeout=timeout)
        response.raise_for_status()
        return [
            {
                "tag": release.get("tag_name", ""),
                "name": release.get("name") or release.get("tag_name", ""),
                "date": (release.get("published_at") or "")[:10],
                "notes": release.get("body") or "",
                "url": release.get("html_url") or RELEASES_URL,
            }
            for release in response.json()
            if not release.get("draft") and not release.get("prerelease")
        ]
    except Exception as e:
        logger.info(f"Changelog skipped (could not reach GitHub): {e}")
        return None
