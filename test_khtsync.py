#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2010 Benoît HERVIER
# Licenced under GPLv3

global USER
global PASSWORD
USER = ''
PASSWORD = ''

"""Unit test for khtsync.py"""

import khtsync
import unittest
import os
import shutil
import hashlib
import time
import sys

class TestSync(unittest.TestCase):

    def testCreateFolder(self):
        """ Check the upload and download of folder """
        global USER
        global PASSWORD
        try:
            shutil.rmtree('/tmp/origin')
            shutil.rmtree('/tmp/dest')
        except:
            pass
        os.mkdir('/tmp/origin')
        os.mkdir('/tmp/dest')
        os.mkdir('/tmp/origin/test_origin_dir')
        os.mkdir('/tmp/dest/test_dest_dir')
        s = khtsync.Sync('127.0.0.1',22,USER,PASSWORD,local_dir = '/tmp/origin',remote_dir = '/tmp/dest')
        s.connect()
        s.sync()
        s.close()
        assert os.path.isdir('/tmp/origin/test_dest_dir') , 'Syncing folder from ssh didn work'
        assert os.path.isdir('/tmp/dest/test_origin_dir') , 'Syncing folder to ssh didn work'

    def testCreateFile(self):
        """ Check the upload and download of files """
        global USER
        global PASSWORD
        try:
            shutil.rmtree('/tmp/origin')
            shutil.rmtree('/tmp/dest')
        except:
            pass
        os.mkdir('/tmp/origin')
        os.mkdir('/tmp/dest')
        fh = open('/tmp/dest/test_origin','w')
        fh.write('test_origin')
        fh.close()
        fh = open('/tmp/origin/test_dest','w')
        fh.write('test_dest')
        fh.close()
        s = khtsync.Sync('127.0.0.1',22,USER,PASSWORD,local_dir='/tmp/origin',remote_dir='/tmp/dest')
        s.connect()
        s.sync()
        s.close()
        assert os.path.isfile('/tmp/origin/test_dest') , 'Syncing file from ssh didn work'
        assert os.path.isfile('/tmp/dest/test_origin') , 'Syncing file to ssh didn work'
        fh = open('/tmp/dest/test_origin','r')
        origin = fh.read()
        fh.close()
        fh = open('/tmp/origin/test_dest','r')
        dest = fh.read()
        fh.close()
        assert hashlib.md5(origin) != hashlib.md5('test_origin') , 'Syncing file to ssh didn work diff in the md5'
        assert hashlib.md5(dest) != hashlib.md5('test_dest') , 'Syncing file to ssh didn work diff in the md5'

    def testFolderReplacedByFile(self):
        global USER
        global PASSWORD
        try:
            shutil.rmtree('/tmp/origin')
            shutil.rmtree('/tmp/dest')
        except:
            pass
        os.mkdir('/tmp/origin')
        os.mkdir('/tmp/dest')
        fh = open('/tmp/origin/test_origin','w')
        fh.write('test_origin')
        fh.close()
        time.sleep(1)
        os.mkdir('/tmp/dest/test_origin')
        os.mkdir('/tmp/origin/test_dest')
        time.sleep(1)
        fh = open('/tmp/dest/test_dest','w')
        fh.write('test_dest')
        fh.close()
        s = khtsync.Sync('127.0.0.1',22,USER,PASSWORD,local_dir='/tmp/origin',remote_dir='/tmp/dest')
        s.connect()
        s.sync()
        s.close()
        assert os.path.isfile('/tmp/origin/test_dest') , 'Syncing file from ssh didn work'
        assert os.path.isdir('/tmp/dest/test_origin') , 'Syncing file to ssh didn work'
        fh = open('/tmp/origin/test_dest','r')
        dest = fh.read()
        fh.close()
        assert hashlib.md5(dest) != hashlib.md5('test_dest') , 'Syncing file to ssh didn work'
        
    def testRsyncedFile(self):
        global USER
        global PASSWORD
        try:
            shutil.rmtree('/tmp/origin')
            shutil.rmtree('/tmp/dest')
        except:
            pass
        os.mkdir('/tmp/origin')
        os.mkdir('/tmp/dest')
        fh = open('/tmp/dest/test_origin','w')
        fh.write('test_origin1')
        fh.close()
        time.sleep(1)
        fh = open('/tmp/origin/test_origin','w')
        fh.write('test_origin')
        fh.close()
        fh = open('/tmp/origin/test_dest','w')
        fh.write('test_dest1')
        fh.close()
        time.sleep(1)
        fh = open('/tmp/dest/test_dest','w')
        fh.write('test_origin')
        fh.close()
        s = khtsync.Sync('127.0.0.1',22,USER,PASSWORD,local_dir='/tmp/origin',remote_dir='/tmp/dest')
        s.connect()
        s.sync()
        s.close()
        fh = open('/tmp/origin/test_origin','r')
        origin_test_origin = fh.read()
        fh.close()
        fh = open('/tmp/dest/test_origin','r')
        dest_test_origin = fh.read()
        fh.close()
        fh = open('/tmp/origin/test_dest','r')
        origin_test_dest = fh.read()
        fh.close()
        fh = open('/tmp/dest/test_dest','r')
        dest_test_dest = fh.read()
        fh.close()
        assert hashlib.md5(origin_test_origin) != hashlib.md5(dest_test_origin) , 'Rsynced upload differ'
        assert hashlib.md5(origin_test_dest) != hashlib.md5(dest_test_dest) , 'Rsynced download differ'
                        
if __name__ == "__main__":
    USER = sys.argv[1]
    PASSWORD = sys.argv[2]
    del sys.argv[2]
    del sys.argv[1]
    unittest.main()   
