from collections import namedtuple
__all__ = ['version_tuple', 'version', 'VersionInfo']


class VersionInfo(namedtuple("VersionInfo", 'major minor patch releaselevel')):
    def as_string(self):
        verstr = f"{self.major}.{self.minor}.{self.patch}"
        if self.releaselevel != "release":
            verstr += f"-{version_tuple.releaselevel}"
        return verstr


version_tuple = VersionInfo(major=2, minor=2, patch=1, releaselevel="release")

version = version_tuple.as_string()
