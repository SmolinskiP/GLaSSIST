"""Tests for platform_utils module."""
import os
from pathlib import Path
from unittest.mock import patch

import platform_utils


class TestFlatpakPaths:
    def test_is_flatpak_false_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert platform_utils.is_flatpak() is False

    def test_is_flatpak_true_when_id_set(self):
        with patch.dict(os.environ, {"FLATPAK_ID": "io.github.SmolinskiP.GLaSSIST"}):
            assert platform_utils.is_flatpak() is True

    def test_config_dir_outside_flatpak_is_app_dir(self):
        with patch.dict(os.environ, {}, clear=True):
            expected = Path(platform_utils.__file__).parent
            assert platform_utils.get_config_dir() == expected

    def test_config_dir_in_flatpak_uses_xdg(self, tmp_path):
        env = {"FLATPAK_ID": "x", "XDG_CONFIG_HOME": str(tmp_path)}
        with patch.dict(os.environ, env):
            result = platform_utils.get_config_dir()
            assert result == tmp_path / "glasssist"
            assert result.is_dir()

    def test_env_file_path_in_flatpak(self, tmp_path):
        env = {"FLATPAK_ID": "x", "XDG_CONFIG_HOME": str(tmp_path)}
        with patch.dict(os.environ, env):
            expected = tmp_path / "glasssist" / ".env"
            assert platform_utils.get_env_file_path() == expected

    def test_user_sound_dir_none_outside_flatpak(self):
        with patch.dict(os.environ, {}, clear=True):
            assert platform_utils.get_user_sound_dir() is None

    def test_user_sound_dir_in_flatpak(self, tmp_path):
        env = {"FLATPAK_ID": "x", "XDG_DATA_HOME": str(tmp_path)}
        with patch.dict(os.environ, env):
            result = platform_utils.get_user_sound_dir()
            assert result == tmp_path / "glasssist" / "sound"
            assert result.is_dir()
