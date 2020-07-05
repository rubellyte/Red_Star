from collections import namedtuple
__all__ = ['version_tuple', 'version']


class VersionInfo(namedtuple("VersionInfo", 'major minor patch releaselevel')):
    def as_string(self):
        verstr = f"{self.major}.{self.minor}.{self.patch}"
        if self.releaselevel != "release":
            verstr += f"-{version_tuple.releaselevel}"
        return verstr


version_tuple = VersionInfo(major=2, minor=1, patch=6, releaselevel="beta")

version = version_tuple.as_string()
