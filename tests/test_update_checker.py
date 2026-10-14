"""Tests for the GitHub release checks used by the update bar and the Changelog tab."""
from unittest.mock import Mock, patch

import update_checker


def _response(payload):
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status = Mock()
    return response


def test_get_releases_skips_drafts_and_prereleases():
    payload = [
        {'tag_name': '3.8.1', 'name': 'GLaSSIST 3.8.1', 'published_at': '2026-10-15T10:00:00Z',
         'body': '### Fixes', 'html_url': 'https://github.com/x/releases/tag/3.8.1'},
        {'tag_name': '3.9.0', 'name': 'draft', 'draft': True},
        {'tag_name': '3.9.0-beta', 'name': 'beta', 'prerelease': True},
        {'tag_name': '3.8.0', 'name': None, 'published_at': None, 'body': None, 'html_url': None},
    ]
    with patch('update_checker.requests.get', return_value=_response(payload)) as get:
        releases = update_checker.get_releases(limit=5)
    assert get.call_args.kwargs['params'] == {'per_page': 5}
    assert releases == [
        {'tag': '3.8.1', 'name': 'GLaSSIST 3.8.1', 'date': '2026-10-15', 'notes': '### Fixes',
         'url': 'https://github.com/x/releases/tag/3.8.1'},
        {'tag': '3.8.0', 'name': '3.8.0', 'date': '', 'notes': '', 'url': update_checker.RELEASES_URL},
    ]


def test_get_releases_returns_none_when_offline():
    with patch('update_checker.requests.get', side_effect=OSError('offline')):
        assert update_checker.get_releases() is None


def test_check_for_update_compares_versions():
    with patch('update_checker.get_latest_release', return_value='v99.0.0'):
        assert update_checker.check_for_update() == 'v99.0.0'
    with patch('update_checker.get_latest_release', return_value='0.0.1'):
        assert update_checker.check_for_update() is None
