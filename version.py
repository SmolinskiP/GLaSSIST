"""Single source of truth for the application version.

Keep this in sync with setup.iss (#define MyAppVersion) and the Flatpak
metainfo.xml <release> entry when cutting a new release.
"""

__version__ = "3.6.0"

# GitHub repository used for the update check (owner/repo).
GITHUB_REPO = "SmolinskiP/GLaSSIST"
