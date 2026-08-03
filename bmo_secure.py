"""BMO security helpers - hardening for anything that unpacks remote data."""

import os


def safe_extract_members(tf, dest):
    """Extract a tar archive while refusing path traversal / absolute paths.

    Raises ValueError on a dangerous member instead of writing anywhere.
    """
    dest = os.path.realpath(dest)
    for member in tf.getmembers():
        member_path = member.name.replace("\\", "/")
        joined = os.path.realpath(os.path.join(dest, member.name))
        if member_path.startswith("/") or ".." in member_path.split("/"):
            raise ValueError("unsafe path in archive: %r" % member.name)
        if not (joined == dest or joined.startswith(dest + os.sep)):
            raise ValueError("archive escapes target dir: %r" % member.name)
    tf.extractall(dest)


def safe_extract_zip(zf, dest):
    """Extract a zip archive while refusing path traversal / absolute paths."""
    dest = os.path.realpath(dest)
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        joined = os.path.realpath(os.path.join(dest, info.filename))
        if name.startswith("/") or ".." in name.split("/"):
            raise ValueError("unsafe path in archive: %r" % info.filename)
        if not (joined == dest or joined.startswith(dest + os.sep)):
            raise ValueError("archive escapes target dir: %r" % info.filename)
    zf.extractall(dest)
