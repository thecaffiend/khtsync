#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2010 Benoît HERVIER
# Licenced under GPLv3

from __future__ import with_statement

""" Sync two folder over ssh : Daemon """

__version__ = '0.0.5'

#TODO
#Add better errors managment
#Implement better unit test

import logging

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
import daemon

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
        logging.debug('Connecting to ' + unicode(self.hostname))
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

    def list_all(self, curr_path, remote_objs):
        dirlist = self.sftp.listdir_attr(curr_path)
        for curr_file in dirlist:
            relpath = relpth.relpath(self.remote_dir,os.path.join(curr_path, curr_file.filename))
            if self.isdir(os.path.join(curr_path, curr_file.filename)):
                remote_objs[relpath] = curr_file.st_mtime
                self.list_all(os.path.join(curr_path,
                        curr_file.filename), remote_objs)
            else:
                remote_objs[relpath] = curr_file.st_mtime
                
    def patch_from_server(self,relpath):
        topatch = open(os.path.join(self.local_dir,relpath), "rb")
        hashes = rsync.blockchecksums(topatch)

        newfile = self.sftp.file(os.path.join(self.remote_dir,relpath))
        newfile.closed = new.instancemethod(_closed, newfile, paramiko.SFTPFile)
        delta = rsync.rsyncdelta(newfile, hashes)

        topatch.seek(0)
        readed = StringIO.StringIO(topatch.read())
        topatch.close()
        
        fh = open(os.path.join(self.local_dir,relpath), "wb")
        rsync.patchstream(readed, fh, delta)

        newfile.close()
        fh.close()        
    
    def patch_to_server(self,relpath):
        topatch = self.sftp.file(os.path.join(self.remote_dir,relpath), "rb")
        hashes = rsync.blockchecksums(topatch)

        newfile = open(os.path.join(self.local_dir,relpath))
        delta = rsync.rsyncdelta(newfile, hashes)

        topatch.seek(0)
        readed = StringIO.StringIO(topatch.read())        
        topatch.close()
        fh = self.sftp.file(os.path.join(self.remote_dir,relpath), "wb")
        rsync.patchstream(readed, fh, delta)

        newfile.close()
        fh.close() 

    def buildUpdate(self):
        update = {}
        update['delete_local'] = []
        update['delete_remote'] = []
        update['update_local'] = []
        update['update_remote'] = []
                
        #Load remote last synced file
        logging.debug('*** Loading remote last synced dirs and files...')
        old_remote_objs = {}
        if self.exists(os.path.join(self.remote_dir,'.khtsync')):
            try:
                with self.sftp.file(os.path.join(self.remote_dir,'.khtsync') ,'rb') as fh:
                    old_remote_objs = pickle.load(fh)
                    if type(old_remote_objs) != dict:
                        raise
            except:
                old_remote_objs = {}

        #Load local last synced file
        logging.debug('*** Loading local last synced dirs and files....')
        old_local_objs = {}
        if os.path.exists(os.path.join(self.local_dir,'.khtsync')):
            try:
                with open(os.path.join(self.local_dir,'.khtsync') ,'rb') as fh:
                    old_local_objs = pickle.load(fh)
                    if type(old_local_objs) != dict:
                        raise
            except:
                old_local_objs = {}
                
        #List remote files and dirs
#        print '*** Listing remote dirs and files...'
        logging.debug('*** Listing remote dirs and files...')
        remote_objs = {}
        self.list_all(self.remote_dir, remote_objs)
        if '.khtsync' in remote_objs:
            del remote_objs['.khtsync']
    
        #List local files ands dirs
#        print '*** Listing local dirs and files...'
        local_objs = {}
        for root, dirs, files in os.walk(self.local_dir):
            for afile in files:
                path = os.path.join(root, afile)
                local_objs[relpth.relpath(self.local_dir,path)] = os.path.getmtime(path)
            for dir in dirs:
                path = os.path.join(root, dir)
                local_objs[relpth.relpath(self.local_dir,path)] = os.path.getmtime(path)
                
        if '.khtsync' in local_objs:
            del local_objs['.khtsync']

#        print '*** listing deleted files and dirs...'
        logging.debug('*** listing deleted files and dirs...')
        #Deleted local objs
        alist = list(set(old_local_objs) - set(local_objs))
        for relpath in alist:
            if relpath in remote_objs:
                if old_local_objs[relpath]>=remote_objs[relpath]:
                    update['delete_remote'].append(relpath)

        #Deleted remote objs
        alist = list(set(old_remote_objs) - set(remote_objs))
        for relpath in alist:
            if relpath in local_objs:
                if old_remote_objs[relpath]>=local_objs[relpath]:
                    update['delete_local'].append(relpath)
        
        #New Local files
#        print '*** listing new local files...'
        logging.debug('*** listing new local files...')
        update['update_remote'].extend(list((set(local_objs) - set(remote_objs))))
                    
        #New Remote files
#        print '*** listing new remote files...'
        logging.debug('*** listing new remote files...')
        update['update_local'].extend(list((set(remote_objs) - set(local_objs))))

#        print 'DEBUG : New remote files :',update['update_local']
        
        #Check modified files
#        print '*** listing modified files...'
        logging.debug('*** listing modified files...')

        for relpath in set(remote_objs).intersection(local_objs):
            if (local_objs[relpath] - remote_objs[relpath]) > 1:
                logging.debug('*** Modified local file : %s : %s < %s' % (relpath,unicode(local_objs[relpath]), unicode(remote_objs[relpath])))
#                print 'DEBUG : Modified local file : %s : %s < %s' % (relpath,unicode(local_files[relpath]), unicode(remote_files[relpath]))
                update['update_remote'].append(relpath)
            elif (remote_objs[relpath] - local_objs[relpath]) > 1:
                logging.debug('*** Modified remote file : %s : %s < %s' % (relpath,unicode(local_objs[relpath]), unicode(remote_objs[relpath])))
#                print 'DEBUG : Modified remote file : %s : %s < %s' % (relpath,unicode(local_files[relpath]), unicode(remote_files[relpath]))
                update['update_local'].append(relpath)

        #Sorting update
        update['delete_local'].sort()
        update['delete_remote'].sort()
        update['delete_local'].reverse()
        update['delete_remote'].reverse()
        update['update_local'].sort()
        update['update_remote'].sort()
        return (update,local_objs,remote_objs)
                            
    def sync(self):
        self.sftp = self.client.open_sftp()
        update,local_objs,remote_objs = self.buildUpdate()
        self.errors = {}

#        print '*** Deleting remote files and dirs...'  
        logging.debug('*** Deleting remote files and dirs...')
        for relpath in update['delete_remote']:
            if self.isdir(os.path.join(self.remote_dir,relpath)):
                self.sftp.rmdir(os.path.join(self.remote_dir,relpath))
                del remote_objs[relpath]
            else:
                self.sftp.remove(os.path.join(self.remote_dir,relpath))
                del remote_objs[relpath]

#        print '*** Deleting local files and dirs...'  
        logging.debug('*** Deleting local files and dirs...')
        for relpath in update['delete_local']:
            if os.path.isdir(os.path.join(self.local_dir,relpath)):
                os.rmdir(os.path.join(self.local_dir,relpath))
                del local_objs[relpath]
            else:
                os.remove(os.path.join(self.local_dir,relpath))
                del local_objs[relpath]
                
#        print '*** Uploading local files and dirs...'      
        logging.debug('*** Uploading local files and dirs...')  
        self.errors['upload'] = []
        for relpath in update['update_remote']:
            try:
#                print 'DEBUG : Uploading : ', relpath
                logging.debug('*** Uploading : %s' % relpath)  
                if os.path.isdir(os.path.join(self.local_dir,relpath)):
                    if self.exists(os.path.join(self.remote_dir,relpath)): #Already exists
                        if not self.isdir(os.path.join(self.remote_dir,relpath)): #Old as a file
                            self.sftp.remove(os.path.join(self.remote_dir,relpath))
#                           print 'Debug sftp.mkdir ',os.path.join(self.remote_dir,relpath)
                            logging.debug('*** sftp.mkdir : %s' % os.path.join(self.remote_dir,relpath))  
                            self.sftp.mkdir(os.path.join(self.remote_dir,relpath))
                        utime=os.path.getmtime(os.path.join(self.local_dir,relpath))
                        self.sftp.utime(os.path.join(self.remote_dir,relpath),(utime,utime))
                        remote_objs[relpath]=utime
                    else:
#                        print 'Debug sftp.mkdir ',os.path.join(self.remote_dir,relpath)
                        logging.debug('*** sftp.mkdir : %s' % os.path.join(self.remote_dir,relpath))
                        self.sftp.mkdir(os.path.join(self.remote_dir,relpath))
                        utime=os.path.getmtime(os.path.join(self.local_dir,relpath))
                        self.sftp.utime(os.path.join(self.remote_dir,relpath),(utime,utime))
                        remote_objs[relpath]=utime
                else:
                    if self.exists(os.path.join(self.remote_dir,relpath)):
                        if self.isdir(os.path.join(self.remote_dir,relpath)):
                            logging.debug('*** sftp.rmdir : %s' % os.path.join(self.remote_dir,relpath))
                            self.sftp.rmdir(os.path.join(self.remote_dir,relpath))
                            logging.debug('*** put : %s' % os.path.join(self.local_dir,relpath))
                            self.sftp.put(os.path.join(self.local_dir,relpath),os.path.join(self.remote_dir,relpath))
                        else:
                            self.patch_to_server(relpath)
                    else:
#                        print 'Debug put ',os.path.join(self.local_dir,relpath),os.path.join(self.remote_dir,relpath)
                        logging.debug('put %s' % os.path.join(self.local_dir,relpath),os.path.join(self.remote_dir,relpath))
                        self.sftp.put(os.path.join(self.local_dir,relpath),os.path.join(self.remote_dir,relpath))
                    utime=os.path.getmtime(os.path.join(self.local_dir,relpath))
                    self.sftp.utime(os.path.join(self.remote_dir,relpath),(utime,utime))
                    remote_objs[relpath]=utime
            except IOError,err:
                self.errors['upload'].append('%s : %s' % (relpath,unicode(err)))
                
#        print '*** Downloading local files and dirs...'   
        self.errors['download'] = []        
        for relpath in update['update_local']:
            try:
#                print 'DEBUG : Downloading : ', relpath
                if self.isdir(os.path.join(self.remote_dir,relpath)):
                    if os.path.exists(os.path.join(self.local_dir,relpath)): #Already exists
                        if not os.path.isdir(os.path.join(self.local_dir,relpath)): #Old as a file:
                            logging.debug('remove %s' % os.path.join(self.local_dir,relpath))
                            os.remove(os.path.join(self.local_dir,relpath))
#                            print 'Debug mkdir ',os.path.join(self.remote_dir,relpath)
                            
                            logging.debug('mkdir %s' % os.path.join(self.local_dir,relpath))
                            os.mkdir(os.path.join(self.local_dir,relpath))
                        utime=self.sftp.lstat(os.path.join(self.remote_dir, relpath)).st_mtime
                        os.utime(os.path.join(self.local_dir,relpath),(utime,utime))
                        local_objs[relpath]=utime
                    else:
#                        print 'Debug mkdir ',os.path.join(self.remote_dir,relpath)
                        logging.debug('mkdir %s' % os.path.join(self.remote_dir,relpath))
                        os.mkdir(os.path.join(self.local_dir,relpath))
                        logging.debug('mkdir %s' % os.path.join(self.local_dir,relpath))
                        utime=self.sftp.lstat(os.path.join(self.remote_dir, relpath)).st_mtime
                        os.utime(os.path.join(self.local_dir,relpath),(utime,utime))
                        local_objs[relpath]=utime
                else:
                    if os.path.exists(os.path.join(self.local_dir,relpath)):
                        if os.path.isdir(os.path.join(self.local_dir,relpath)):
                            os.rmdir(os.path.join(self.local_dir,relpath))
                            logging.debug('rmdir %s' % os.path.join(self.local_dir,relpath))
                            self.sftp.get(os.path.join(self.remote_dir,relpath),os.path.join(self.local_dir,relpath))
                            logging.debug('get %s' % os.path.join(self.remote_dir,relpath))
                        else:
                            self.patch_from_server(relpath)
                    else:
                        self.sftp.get(os.path.join(self.remote_dir,relpath),os.path.join(self.local_dir,relpath))
                        logging.debug('get %s' % os.path.join(self.remote_dir,relpath))
                    utime=self.sftp.lstat(os.path.join(self.remote_dir, relpath)).st_mtime
                    os.utime(os.path.join(self.local_dir,relpath),(utime,utime))
                    local_objs[relpath]=utime
            except IOError,err:
                self.errors['download'].append('%s : %s' % (relpath,unicode(err)))
               
        if '.khtsync' in remote_objs:
            del remote_objs['.khtsync']
        fh = self.sftp.file(os.path.join(self.remote_dir,'.khtsync') ,'wb')
        pickle.dump(remote_objs,fh)
        fh.close()

        if '.khtsync' in local_objs:
            del local_objs['.khtsync']
        with open(os.path.join(self.local_dir,'.khtsync') ,'wb') as fh:
            pickle.dump(local_objs,fh)
        

# if __name__ == '__main__':
    # if len(sys.argv)<7:
        # print "Usage : host port login password local_dir remote_dir"
    # else:
       # with daemon.DaemonContext():
        # s = Sync(hostname=sys.argv[1], port=int(sys.argv[2]), username=sys.argv[3], password=sys.argv[4], local_dir=sys.argv[5], remote_dir=sys.argv[6])
        # s.connect()
        # s.sync()
        # s.close()
        # if len(s.errors['upload'])>0:
            # print "Error occurs while uploading : ", s.errors['upload']
        # if len(s.errors['download'])>0:
            # print "Error occurs while downloading : ", s.errors['download']
