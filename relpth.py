#!/usr/bin/python
# -*- coding: utf-8 -*-

from os.path import abspath, dirname, normcase, normpath, splitdrive
from os.path import join as path_join, commonprefix
import os



def commonpath(a, b):
    """Returns the longest common to 'paths' path.

    Unlike the strange commonprefix:
    - this returns valid path
    - accepts only two arguments
    """
    a = normpath(normcase(a))
    b = normpath(normcase(b))

    if a == b:
        return a

    while len(a) > 0:
        if a == b:
            return a

        if len(a) > len(b):
            a = dirname(a)
        else:
            b = dirname(b)

    return None


def relpath(base_path,target):
    """\
    Return a relative path to the target from either the current directory
    or an optional base directory.

    Base can be a directory specified either as absolute or relative
    to current directory."""

    # changing case here was causing issues. local_objs in khtsync had all 
    # lowercase names, which was a problem when the selected file syncing was
    # implemented (as it relied on actual filenames with upper and lower case)
#    base_path = normcase(abspath(normpath(base_path)))
#    target = normcase(abspath(normpath(target)))
    base_path = abspath(normpath(base_path))
    target = abspath(normpath(target))

    if base_path == target:
        return '.'

    # On the windows platform the target may be on a different drive.
    if splitdrive(base_path)[0] != splitdrive(target)[0]:
        return None

    common_path_len = len(commonpath(base_path, target))

    # If there's no common prefix decrease common_path_len should be less by 1
    base_drv, base_dir = splitdrive(base_path)
    if common_path_len == len(base_drv) + 1:
        common_path_len -= 1

    # if base_path is root directory - no directories up
    if base_dir == os.sep:
        dirs_up = 0
    else:
        dirs_up = base_path[common_path_len:].count(os.sep)

    ret = os.sep.join([os.pardir] * dirs_up)
    if len(target) > common_path_len:
        ret = path_join(ret, target[common_path_len + 1:])

    return ret
