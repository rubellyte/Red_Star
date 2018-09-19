from collections import namedtuple
__all__ = ['version_tuple', 'version']

_VersionInfo = namedtuple("VersionInfo", 'major minor patch releaselevel')
version_tuple = _VersionInfo(major=2, minor=0, patch=0, releaselevel="beta")

version = f"{version_tuple.major}.{version_tuple.minor}"
if version_tuple.patch > 0:
    version += f".{version_tuple.patch}"
if version_tuple.releaselevel != "release":
    version += f"-{version_tuple.releaselevel}"
