# The contrib hook copies metadata for "webrtcvad", but we install the
# webrtcvad-wheels distribution, whose module reads its own version.
from PyInstaller.utils.hooks import copy_metadata

datas = copy_metadata('webrtcvad-wheels')
