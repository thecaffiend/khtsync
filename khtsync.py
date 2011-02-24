#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2010 Benoît HERVIER
# Licenced under GPLv3

from __future__ import with_statement

""" Sync two folder over ssh """

#TODO
#Implement unit test

import os
import glob
import paramiko
#import md5
import StringIO
import pickle
import relpth
import rsync
import sys
import shutil
import new

def _closed(self):
    return self._closed

class Sync():

    def __init__(self, hostname='127.0.0.1', port=22,
             username=None,
             password=None,
             private_key_path='',
             local_dir=None, remote_dir=None):

        self.hostname = hostname
        self.username = username
        self.port = port
        self.password = password
        self.private_key_path = private_key_path
        self.local_dir = local_dir
        self.remote_dir = remote_dir

    def connect(self):
        self.client = paramiko.SSHClient()
        self.client.load_system_host_keys()
        self.client.set_missing_host_key_policy(paramiko.WarningPolicy)
        print '*** Connecting...'
        self.client.connect(self.hostname,
                            self.port,
                            self.username,
                            self.password)

    def close(self):
        self.client.close()

    def run(self, command):
        log_fp = StringIO.StringIO()
        status = 0
        try:
            t = self.client.exec_command(command)
        except paramiko.SSHException:
            status = 1
        log_fp.write(t[1].read())
        log_fp.write(t[2].read())
        t[0].close()
        t[1].close()
        t[2].close()
        return (status, log_fp.getvalue())

    def isdir(self, path):
        status = self.run('[ -d %s ] || echo "FALSE"' % path)
        if status[1].startswith('FALSE'):
            return False
        return True

    def exists(self, path):
        status = self.run('[ -a %s ] || echo "FALSE"' % path)
        if status[1].startswith('FALSE'):
            return False
        return True

    def list_all(self, curr_path, remote_files, remote_dirs):
        dirlist = self.sftp.listdir(curr_path)
        for curr_file in dirlist:
            relpath = relpth.relpath(self.remote_dir,os.path.join(curr_path, curr_file))
            if self.isdir(os.path.join(curr_path, curr_file)):
                remote_dirs[relpath] = self.sftp.lstat(os.path.join(curr_path, curr_file)).st_mtime
                self.list_all(os.path.join(curr_path,
                        curr_file), remote_files,remote_dirs)
            else:
                remote_files[relpath] = \
                self.sftp.lstat(os.path.join(curr_path, curr_file)).st_mtime

    def patch_from_server(self,relpath):
        topatch = open(os.path.join(self.local_dir,relpath), "rb")
        hashes = rsync.blockchecksums(topatch)

        newfile = self.sftp.file(os.path.join(self.remote_dir,relpath))
        newfile.closed = new.instancemethod(_closed, newfile, paramiko.SFTPFile)
        delta = rsync.rsyncdelta(newfile, hashes)

        topatch.seek(0)
        fh = open(os.path.join(self.local_dir,relpath), "wb")
        rsync.patchstream(topatch, fh, delta)
        topatch.close()
        newfile.close()
        fh.close()        
    
    def patch_to_server(self,relpath):
        topatch = self.sftp.file(os.path.join(self.remote_dir,relpath), "rb")
        hashes = rsync.blockchecksums(topatch)

        newfile = open(os.path.join(self.local_dir,relpath))
        delta = rsync.rsyncdelta(newfile, hashes)

        topatch.seek(0)
        fh = self.sftp.file(os.path.join(self.remote_dir,relpath), "wb")
        rsync.patchstream(topatch, fh, delta)
        topatch.close()
        newfile.close()
        fh.close() 

    def buildUpdate(self):
        update = {}
        update['delete_local'] = []
        update['delete_remote'] = []
        update['update_local'] = []
        update['update_remote'] = []
                
        #Load remote last synced file
        print '*** Loading remote last synced dirs and files...'
        old_remote_files = {}
        old_remote_dirs = {}
        if self.exists(os.path.join(self.remote_dir,'.khtsync')):
            try:
                with self.sftp.file(os.path.join(self.remote_dir,'.khtsync') ,'rb') as fh:
                    old_remote_files, old_remote_dirs = pickle.load(fh)
            except:
                pass

        #Load local last synced file
        print '*** Loading local last synced dirs and files....'
        old_local_files = {}
        old_local_dirs = {}
        if os.path.exists(os.path.join(self.local_dir,'.khtsync')):
            try:
                with open(os.path.join(self.local_dir,'.khtsync') ,'rb') as fh:
                    old_local_files, old_local_dirs = pickle.load(fh)
            except:
                pass
                
        #List remote files and dirs
        print '*** Listing remote dirs and files...'
        remote_files = {}
        remote_dirs = {}
        self.list_all(self.remote_dir, remote_files, remote_dirs)
        if '.khtsync' in remote_files:
            del remote_files['.khtsync']
    
        #List local files ands dirs
        print '*** Listing local dirs and files...'
        local_files = {}
        local_dirs = {}
        for root, dirs, files in os.walk(self.local_dir):
            for afile in files:
                path = os.path.join(root, afile)
                local_files[relpth.relpath(self.local_dir,path)] = os.path.getmtime(path)
            for dir in dirs:
                path = os.path.join(root, dir)
                local_dirs[relpth.relpath(self.local_dir,path)] = os.path.getmtime(path)
                
        if '.khtsync' in local_files:
            del local_files['.khtsync']

        print '*** listing deleted files and dirs...'

        #Deleted local files
        alist = list(set(old_local_files) - set(local_files))
        for relpath in alist:
            if relpath in remote_files:
                if old_local_files[relpath]>=remote_files[relpath]:
                    update['delete_remote'].append(relpath)
            if relpath in remote_dirs:
                if old_local_files[relpath]>=remote_dirs[relpath]:
                    update['delete_remote'].append(relpath)

        #Deleted local dirs
        alist = list(set(old_local_dirs) - set(local_dirs))
        for relpath in alist:
            if relpath in remote_files:
                if old_local_dirs[relpath]>=remote_files[relpath]:
                    update['delete_remote'].append(relpath)
            if relpath in remote_dirs:
                if old_local_dirs[relpath]>=remote_dirs[relpath]:
                    update['delete_remote'].append(relpath)

        #Deleted remote files
        alist = list(set(old_remote_files) - set(remote_files))
        for relpath in alist:
            if relpath in local_files:
                if old_remote_files[relpath]>=local_files[relpath]:
                    update['delete_local'].append(relpath)
            if relpath in local_dirs:
                if old_remote_files[relpath]>=local_dirs[relpath]:
                    update['delete_local'].append(relpath)

        #Deleted remote dirs
        alist = list(set(old_remote_dirs) - set(remote_dirs))
        for relpath in alist:
            if relpath in local_files:
                if old_remote_dirs[relpath]>=local_files[relpath]:
                    update['delete_local'].append(relpath)
            if relpath in local_dirs:
                if old_remote_dirs[relpath]>=local_dirs[relpath]:
                    update['delete_local'].append(relpath)

        local_files.update(local_dirs)
        remote_files.update(remote_dirs)
        #New Local dirs
#        print '*** listing new local dirs...'
#        update['update_remote'].extend(list((set(local_dirs) - set(remote_dirs))))

        #New Local files
        print '*** listing new local files...'
        update['update_remote'].extend(list((set(local_files) - set(remote_files))))
                    
        #New Remote dirs
#        print '*** listing new remote dirs...'
#        update['update_local'].extend(list((set(remote_dirs) - set(local_dirs))))

        #New Remote files
        print '*** listing new remote files...'
        update['update_local'].extend(list((set(remote_files) - set(local_files))))

        #Check modified files
        print '*** listing modified files...'
        for relpath in set(remote_files).intersection(local_files):
            if local_files[relpath] > remote_files[relpath]:
                update['update_remote'].append(relpath)
            elif local_files[relpath] < remote_files[relpath]:
                update['update_local'].append(relpath)

        #Sorting update
        update['delete_local'].sort()
        update['delete_remote'].sort()
        update['delete_local'].reverse()
        update['delete_remote'].reverse()
        update['update_local'].sort()
        update['update_remote'].sort()
        return update
                            
    def sync(self):
        self.sftp = self.client.open_sftp()
        update = self.buildUpdate()

        print update

        print '*** Deleting remote files and dirs...'        
        for relpath in update['delete_remote']:
            if self.isdir(os.path.join(self.remote_dir,relpath)):
                self.sftp.rmdir(os.path.join(self.remote_dir,relpath))
            else:
                self.sftp.remove(os.path.join(self.remote_dir,relpath))

        print '*** Deleting local files and dirs...'        
        for relpath in update['delete_local']:
            if os.path.isdir(os.path.join(self.local_dir,relpath)):
                os.rmdir(os.path.join(self.local_dir,relpath))
            else:
                os.remove(os.path.join(self.local_dir,relpath))
                
        print '*** Uploading local files and dirs...'        
        for relpath in update['update_remote']:
            print 'DEBUG : Uploading : ', relpath
            if os.path.isdir(os.path.join(self.local_dir,relpath)):
                if self.exists(os.path.join(self.remote_dir,relpath)): #Old as a file
                    if not self.isdir(os.path.join(self.remote_dir,relpath)): #Old as a file
                        self.sftp.remove(os.path.join(self.local_dir,relpath))
                    else:
                        utime=os.path.getmtime(os.path.join(self.local_dir,relpath))
                        self.sftp.utime(os.path.join(self.remote_dir,relpath),(utime,utime))
                else:
                    print 'Debug mkdir ',os.path.join(self.remote_dir,relpath)
                    self.sftp.mkdir(os.path.join(self.remote_dir,relpath))
                    utime=os.path.getmtime(os.path.join(self.local_dir,relpath))
                    self.sftp.utime(os.path.join(self.remote_dir,relpath),(utime,utime))
            else:
                if self.exists(os.path.join(self.remote_dir,relpath)):
                    if self.isdir(os.path.join(self.remote_dir,relpath)):
                        self.sftp.rmdir(os.path.join(self.remote_dir,relpath))
                        self.sftp.put(os.path.join(self.local_dir,relpath),os.path.join(self.remote_dir,relpath))
                    else:
                        self.patch_to_server(relpath)
                else:
                    print 'Debug put ',os.path.join(self.local_dir,relpath),os.path.join(self.remote_dir,relpath)
                    self.sftp.put(os.path.join(self.local_dir,relpath),os.path.join(self.remote_dir,relpath))
                utime=os.path.getmtime(os.path.join(self.local_dir,relpath))
                self.sftp.utime(os.path.join(self.remote_dir,relpath),(utime,utime))
                                    
        print '*** Downloading local files and dirs...'        
        for relpath in update['update_local']:
            print 'DEBUG : Downloading : ', relpath
            if self.isdir(os.path.join(self.remote_dir,relpath)):
                if os.path.exists(os.path.join(self.local_dir,relpath)): #Old as a file
                    if not os.path.isdir(os.path.join(self.local_dir,relpath)): #Old as a file:
                        os.remove(os.path.join(self.local_dir,relpath))
                    else:
                        utime=self.sftp.lstat(os.path.join(self.remote_dir, relpath)).st_mtime
                        os.utime(os.path.join(self.local_dir,relpath),(utime,utime))
                else:
                    os.mkdir(os.path.join(self.local_dir,relpath))
                    utime=self.sftp.lstat(os.path.join(self.remote_dir, relpath)).st_mtime
                    os.utime(os.path.join(self.local_dir,relpath),(utime,utime))
            else:
                if os.path.exists(os.path.join(self.local_dir,relpath)):
                    if os.path.isdir(os.path.join(self.local_dir,relpath)):
                        os.rmdir(os.path.join(self.local_dir,relpath))
                        self.sftp.get(os.path.join(self.remote_dir,relpath),os.path.join(self.local_dir,relpath))
                    else:
                        self.patch_from_server(relpath)
                else:
                    self.sftp.get(os.path.join(self.remote_dir,relpath),os.path.join(self.local_dir,relpath))
                utime=self.sftp.lstat(os.path.join(self.remote_dir, relpath)).st_mtime
                os.utime(os.path.join(self.local_dir,relpath),(utime,utime))


                
#        try:
#
#            #Check new local dirs
#            print '*** Checking new local dirs...'
#            new_local = list((set(local_dirs) - set(remote_dirs)))
#            new_local.sort()
#            for relpath in new_local:
#                self.sftp.mkdir(os.path.join(self.remote_dir,relpath))
#                self.sftp.utime(os.path.join(self.remote_dir,relpath),(local_dirs[relpath],local_dirs[relpath]))
#            del new_local
#
#            #Check new remote dirs
#            print '*** Checking new remote dirs...'
#            new_remote = list((set(remote_dirs) - set(local_dirs)))
#            new_remote.sort()
#            for relpath in new_remote:
#                print 'Creating local dir %s' % (relpath)
#                os.makedirs(os.path.join(self.local_dir,relpath))
#                os.utime(os.path.join(self.local_dir,relpath),(remote_dirs[relpath],remote_dirs[relpath]))
#
#
#            #Check new remote files
#            print '*** Checking new remote files...'
#            for relpath in (set(remote_files) - set(local_files)):
#                self.sftp.get(os.path.join(self.remote_dir,relpath),os.path.join(self.local_dir,relpath))
#                os.utime(os.path.join(self.local_dir,relpath),(remote_files[relpath],remote_files[relpath]))
#
#            #Check new local files
#            print '*** Checking new local files...'
#            for relpath in (set(local_files) - set(remote_files)):
#                print 'Uploading %s to %s' % (relpath,os.path.join(self.remote_dir,relpath))
#                self.sftp.put(os.path.join(self.local_dir,relpath),os.path.join(self.remote_dir,relpath))
#                self.sftp.utime(os.path.join(self.remote_dir,relpath),(local_files[relpath],local_files[relpath]))
#
            #Check modified files
#            print '*** Checking modified files...'
#            for relpath in set(remote_files).intersection(local_files):
#                if local_files[relpath] > remote_files[relpath]:
#                    print 'RSync upload %s' % (relpath)                    
#                    self.patch_to_server(relpath)
#                    self.sftp.utime(os.path.join(self.remote_dir,relpath),(local_files[relpath],local_files[relpath]))
#    
#                elif local_files[relpath] < remote_files[relpath]:
#                    print 'Rsync download %s' % (relpath)
#                    self.patch_from_server(relpath)
#                    os.utime(os.path.join(self.local_dir,relpath),(remote_files[relpath],remote_files[relpath]))
#    
#                else:
#                    print 'Same %s' % (relpath,)
                
        #Write remote last synced files
        print '*** Writing remote last synced dirs and files...'
        remote_files = {}
        remote_dirs = {}
        self.list_all(self.remote_dir, remote_files,remote_dirs)
        if '.khtsync' in remote_files:
            del remote_files['.khtsync']
        fh = self.sftp.file(os.path.join(self.remote_dir,'.khtsync') ,'wb')
        pickle.dump((remote_files,remote_dirs),fh)
        fh.close()

        #Write local last synced files
        print '*** Writing local last synced dirs and files...'
        local_files = {}
        local_dirs = {}
        for root, dirs, files in os.walk(self.local_dir):
            for afile in files:
                path = os.path.join(root, afile)
                local_files[relpth.relpath(self.local_dir,path)] =  os.path.getmtime(path)
            for dir in dirs:
                path = os.path.join(root, dir)
                local_dirs[relpth.relpath(self.local_dir,path)] = os.path.getmtime(path)
        if '.khtsync' in local_files:
            del local_files['.khtsync']
        with open(os.path.join(self.local_dir,'.khtsync') ,'wb') as fh:
            pickle.dump((local_files,local_dirs),fh)
        
#        except:
#            raise

if __name__ == '__main__':
    if len(sys.argv)<7:
        print "Usage : host port login password local_dir remote_dir"
    else:
        s = Sync(hostname=sys.argv[1], port=int(sys.argv[2]), username=sys.argv[3], password=sys.argv[4], local_dir=sys.argv[5], remote_dir=sys.argv[6])
        s.connect()
        s.sync()
        s.close()
