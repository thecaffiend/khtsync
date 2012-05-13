#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2010 Benoît HERVIER
# Licenced under GPLv3

from __future__ import with_statement

""" Sync two folder over ssh : Daemon """

__version__ = '0.1.0'

#TODO
#Add better errors managment
#Keep the read/write/execute attributes over sync
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
import stat

logging.basicConfig()
log = logging.getLogger('khtsync')
log.setLevel(logging.DEBUG)

# directions sync can happen. up is from the local to the remote, down is from 
# the remote to the local, and both is, well, both. Both is only allowed for a 
# sync all operation (not specifying a set of files to sync)
UP = 'up'
DOWN = 'down'
BOTH = 'both'

def _closed(self):
    return self._closed

class Sync():

    def __init__(self, hostname='127.0.0.1', port=22,
             username=None,
             password=None,
             private_key_path='',
             local_dir=None, remote_dir=None, 
             ignored_files=['.khtsync']):

        self.hostname = hostname
        self.username = username
        self.port = port
        self.password = password
        self.private_key_path = private_key_path
        self.local_dir = local_dir
        self.remote_dir = remote_dir
        self.ignored_files = ignored_files

    def connect(self):
        try:
            self.client = paramiko.SSHClient()
            self.client.load_system_host_keys()
            self.client.set_missing_host_key_policy(paramiko.WarningPolicy())
            log.info('Connecting to ' + unicode(self.hostname))
            self.client.connect(self.hostname,
                                self.port,
                                self.username,
                                self.password)
        except paramiko.SSHException:
            log.exception('Connection to %s failed.' % self.hostname)
            raise

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
        # status = self.run('[ -d %s ] || echo "FALSE"' % path)
        # if status[1].startswith('FALSE'):
            # return False
        # return True
        try:
            statinfo = self.sftp.lstat(path)
        except IOError, e:
            if getattr(e,"errno",None) == 2:
                return False
            raise
        return stat.S_ISDIR(statinfo.st_mode)


    def exists(self, path):
        # status = self.run('[ -a %s ] || echo "FALSE"' % path)
        # if status[1].startswith('FALSE'):
            # return False
        # return True
        try:
            self.sftp.lstat(path)
        except IOError, e:
            if getattr(e,"errno",None) == 2:
                return False
            raise
        return True
        
    def list_all(self, curr_path, remote_objs):
        try:
            dirlist = self.sftp.listdir_attr(curr_path)
            for curr_file in dirlist:
                rempath = self.sanitize_remote_path(os.path.join(curr_path, curr_file.filename))
                relpath = self.sanitize_remote_path(relpth.relpath(self.remote_dir,rempath))
                if self.isdir(rempath):
                    remote_objs[relpath] = curr_file.st_mtime                
                    self.list_all(rempath, remote_objs)
                else:
                    remote_objs[relpath] = curr_file.st_mtime
        except IOError, err:
            log.info('Cannot read %s ' % curr_path)
            raise err
            
    def patch_from_server(self,relpath):
        '''
        Patch a single file from the server. The file must already exist locally.
        '''
        try:
            rempath = self.sanitize_remote_path(os.path.join(self.remote_dir,relpath))
            locpath = os.path.join(self.local_dir,relpath)
            log.debug("patch_from_server, relpath is: %s " % (relpath))
            topatch = open(locpath, "rb")
            hashes = rsync.blockchecksums(topatch)
    
            newfile = self.sftp.file(rempath)
            newfile.closed = new.instancemethod(_closed, newfile, paramiko.SFTPFile)
            delta = rsync.rsyncdelta(newfile, hashes)
    
            topatch.seek(0)
            readed = StringIO.StringIO(topatch.read())
            topatch.close()
            
            fh = open(locpath, "wb")
            rsync.patchstream(readed, fh, delta)
    
            newfile.close()
            fh.close()
 
        except IOError, err:
            log.info('Cannot patch from server %s : %s' % (relpath,str(err)))
            raise err
    
    def patch_to_server(self,relpath):
        '''
        Patch a single file to the server. The file must already exist on the server.
        '''
        try:
            rempath = self.sanitize_remote_path(os.path.join(self.remote_dir,relpath))
            locpath = os.path.join(self.local_dir,relpath)
            log.debug("patch_to_server, relpath is: %s " % (relpath))
            topatch = self.sftp.file(rempath, "rb")
            hashes = rsync.blockchecksums(topatch)
    
            newfile = open(locpath)
            delta = rsync.rsyncdelta(newfile, hashes)
    
            topatch.seek(0)
            readed = StringIO.StringIO(topatch.read())        
            topatch.close()
            fh = self.sftp.file(rempath, "wb")
            rsync.patchstream(readed, fh, delta)    
            newfile.close()
            fh.close()
            
        except IOError, err:
            log.info('Cannot patch to server %s : %s' % (relpath,str(err)))
            raise err
            
    def build_update_all(self, direction=BOTH):
        '''
        TODO: Change to use the direction constants UP, DOWN, or BOTH
        
        Build the updates for syncing, looking at all files for changes in the 
        desired directions. If direction is DOWN or BOTH, changes on the remote 
        server will be synced locally. If direction is UP or BOTH, local 
        changes will be synced to the remote server. currently the changes with the 
        latest mtime will be the sync winner in case of conflict.
        '''
        update = {}
        update['delete_local'] = []
        update['delete_remote'] = []
        update['update_local'] = []
        update['update_remote'] = []
                
        #Load remote last synced file
        ## If syncing remote to local (or both ways), you want old_remote_objs 
        ## so you can determine what has been deleted remotely that needs to be 
        ## deleted locally
        log.debug('*** Loading remote last synced dirs and files...')
        old_remote_objs = {}
        rempath = self.sanitize_remote_path(os.path.join(self.remote_dir,'.khtsync'))
        if self.exists(rempath):
            try:
                with self.sftp.file(rempath ,'rb') as fh:
                    old_remote_objs = pickle.load(fh)
                    if type(old_remote_objs) != dict:
                        raise
            except:
                old_remote_objs = {}

        #Load local last synced file
        ## If syncing local to remote (or both ways), you want old_local_objs 
        ## so you can determine what has been deleted locally that needs to be 
        ## deleted remotely
        log.debug('*** Loading local last synced dirs and files....')
        old_local_objs = {}
        locpath = os.path.join(self.local_dir,'.khtsync')
        if os.path.exists(locpath):
            try:
                with open(locpath ,'rb') as fh:
                    old_local_objs = pickle.load(fh)
                    if type(old_local_objs) != dict:
                        raise
            except:
                old_local_objs = {}
                
        #List remote files and dirs
        log.debug('*** Listing remote dirs and files...')
        remote_objs = {}
        
        self.list_all(self.remote_dir, remote_objs)
        
        # remove ignored files.
        for f in self.ignored_files:
            if f in remote_objs:
                del remote_objs[f]
            # this is to remove items that may be subdirectories of an ignored 
            # file. for instance you want to ignore .git, but don't want to have
            # to specify all subdirs to ignore (such as .git/objects). 
            #
            # TODO
            # CURRENTLY this will not allow syncing of .gitignore and similar 
            # things as they start with .git. figure out how to use blobs to 
            # remedy this. possibly jusy specify '.git/' as the ignored file?
            # that might not get .git though
            for k in remote_objs.keys():
                if k.startswith(f):
                    del remote_objs[k]
            
    
        #List local files ands dirs
        local_objs = {}
        for root, dirs, files in os.walk(self.local_dir):
            for afile in files:
                path = os.path.join(root, afile)
                local_objs[relpth.relpath(self.local_dir,path)] = os.path.getmtime(path)
            for dir in dirs:
                path = os.path.join(root, dir)
                print "path: %s" % path
                local_objs[relpth.relpath(self.local_dir,path)] = os.path.getmtime(path)
                
        # remove ignored files.
        for f in self.ignored_files:
            if f in local_objs:
                del local_objs[f]
            # this is to remove items that may be subdirectories of an ignored 
            # file. for instance you want to ignore .git, but don't want to have
            # to specify all subdirs to ignore (such as .git/objects). 
            #
            # TODO
            # CURRENTLY this will not allow syncing of .gitignore and similar 
            # things as they start with .git. figure out if this things should 
            # be rsyncable
            for k in local_objs.keys():
                if k.startswith(f):
                    del local_objs[k]

        log.debug('*** listing deleted files and dirs...')
        #Deleted local objs
        ## Only do this if syncing local to remote
        if direction == UP or direction == BOTH:
            alist = list(set(old_local_objs) - set(local_objs))
            for relpath in alist:
                if relpath in remote_objs:
                    if old_local_objs[relpath]>=remote_objs[relpath]:
                        update['delete_remote'].append(relpath)

        #Deleted remote objs
        ## Only do this if syncing remote to local
        if direction == DOWN or direction == BOTH:
            alist = list(set(old_remote_objs) - set(remote_objs))
            for relpath in alist:
                if relpath in local_objs:
                    if old_remote_objs[relpath]>=local_objs[relpath]:
                        update['delete_local'].append(relpath)
        
        #New Local files
        ## only do this if syncing local to remote
        if direction == UP or direction == BOTH:
            log.debug('*** listing new local files...')
            update['update_remote'].extend(list((set(local_objs) - set(remote_objs))))
                    
        #New Remote files
        ## only do this if syncing remote to local
        if direction == DOWN or direction == BOTH:
            log.debug('*** listing new remote files...')
            update['update_local'].extend(list((set(remote_objs) - set(local_objs))))
        
        #Check modified files
        log.debug('*** listing modified files...')

        for relpath in set(remote_objs).intersection(local_objs):
            if (local_objs[relpath] - remote_objs[relpath]) > 1:
                ## only do this if syncing local to remote
                if direction == UP or direction == BOTH:
                    log.debug('*** Modified local file : %s : %s < %s' % (relpath,unicode(local_objs[relpath]), unicode(remote_objs[relpath])))
                    update['update_remote'].append(relpath)
            elif (remote_objs[relpath] - local_objs[relpath]) > 1:
                ## only do this if syncing remote to local
                if direction == DOWN or direction == BOTH:
                    log.debug('*** Modified remote file : %s : %s < %s' % (relpath,unicode(local_objs[relpath]), unicode(remote_objs[relpath])))
                    update['update_local'].append(relpath)

        # Sorting update. reverse deleted so that the files get deleted before 
        # directories if necessary.
        update['delete_local'].sort()
        update['delete_remote'].sort()
        update['delete_local'].reverse()
        update['delete_remote'].reverse()
        update['update_local'].sort()
        update['update_remote'].sort()
        return (update,local_objs,remote_objs)
        
    def build_update_selected(self, direction=UP, selected_files=[]):
        '''
        Build the updates for syncing, looking at only the state of selected 
        files syncing in the selected direction.  
        
        File path should be of a unix style path, from the base (self.local_dir or 
        self.remote_dir) to the filename. this can be appended to the 
        self.local_dir or self.remote_dir to get the proper full path. e.g if 
        self.local_dir is /var/scm/git/repo and the full path to the selected file 
        is /var/scm/git/repo/path/to/file, the file path passed in should be 
        /path/to/file
        
        direction may only be UP or DOWN. Syncing in both directions is not 
        supported by this method.
        '''
        update = {}
        update['delete_local'] = []
        update['delete_remote'] = []
        update['update_local'] = []
        update['update_remote'] = []
        
        #List remote files and dirs. we care about this to find if the
        # selected files exist remotely or not
        # PERFORMANCE NOTE - we're loading all remote files to check against 
        # potentially a single selected file. this could be smarter
        log.debug('*** Listing remote dirs and files...')
        remote_objs = {}
        self.list_all(self.remote_dir, remote_objs)
        
        # remove ignored files.
        for f in self.ignored_files:
            if f in remote_objs:
                del remote_objs[f]
            # this is to remove items that may be subdirectories of an ignored 
            # file. for instance you want to ignore .git, but don't want to have
            # to specify all subdirs to ignore (such as .git/objects). 
            #
            # TODO
            # CURRENTLY this will not allow syncing of .gitignore and similar 
            # things as they start with .git. figure out if this things should 
            # be rsyncable
            for k in remote_objs.keys():
                if k.startswith(f):
                    del remote_objs[k]
        
        #List local files ands dirs. we care about this to find if the
        # selected files exist locally or not
        # PERFORMANCE NOTE - we're loading all remote files to check against 
        # potentially a single selected file. this could be smarter
        local_objs = {}
        for root, dirs, files in os.walk(self.local_dir):
            for afile in files:
                path = os.path.join(root, afile)
                local_objs[relpth.relpath(self.local_dir,path)] = os.path.getmtime(path)
            for dir in dirs:
                path = os.path.join(root, dir)
                local_objs[relpth.relpath(self.local_dir,path)] = os.path.getmtime(path)
                
        # remove ignored files.
        for f in self.ignored_files:
            if f in local_objs:
                del local_objs[f]
            # this is to remove items that may be subdirectories of an ignored 
            # file. for instance you want to ignore .git, but don't want to have
            # to specify all subdirs to ignore (such as .git/objects). 
            #
            # TODO
            # CURRENTLY this will not allow syncing of .gitignore and similar 
            # things as they start with .git. figure out if this things should 
            # be rsyncable
            for k in local_objs.keys():
                if k.startswith(f):
                    del local_objs[k]
        
        if direction == UP:
            # we don't need to futz with the old remote files. this operation will
            # force the state of the selected local files onto the server 
            # regardless of which is newer
            for file in selected_files:
                if file in remote_objs:
                    if file not in local_objs:
                        # file exists on the server but not locally. file should be
                        # removed on the server
                        update['delete_remote'].append(file)
                    else:
                        # file exists on both server and local, the state of the 
                        # local file should be pushed to the server (regardless of
                        # which is newer)
                        update['update_remote'].append(file)
                else:
                    # file exists locally but not remotely. local state should be 
                    # pushed to the server
                    update['update_remote'].append(file)
                
        elif direction == DOWN:
            # we don't need to futz with the old local files. this operation will
            # force the state of the selected remote files locally regardless of 
            # which is newer
            for file in selected_files:
                if file in local_objs:
                    if file not in remote_objs:
                        # file exists locally but not on the server. file should be
                        # removed locally
                        update['delete_local'].append(file)
                    else:
                        # file exists on both server and local, the state of the 
                        # server file should be pulled locally (regardless of
                        # which is newer)
                        update['update_local'].append(file)
                else:
                    # file exists on the server but not locally. server state 
                    # should be pulled from the server
                    update['update_local'].append(file)
        else:
            raise ValueError(
                'Invalid sync direction [%s] for syncing selected files' % direction)

        # Sorting update. reverse deleted so that the files get deleted before 
        # directories if necessary.
        update['delete_local'].sort()
        update['delete_remote'].sort()
        update['delete_local'].reverse()
        update['delete_remote'].reverse()
        update['update_local'].sort()
        update['update_remote'].sort()
        return (update,local_objs,remote_objs)
                            
    def sync(self, direction=BOTH, selected_files=None):
        '''
        TODO: Change to work with the direction constants.
        
        Sync remote changes to local and local changes to remote. The changes 
        on the server will take precedence if changes exist in both locations
        based on the way build updates currently works.
        '''
        self.sftp = self.client.open_sftp()
        
        if selected_files is None:
            update,local_objs,remote_objs = self.build_update_all(direction)
        else:
            log.warn('*** files %s ***' % files)
            update,local_objs,remote_objs = self.build_update_selected(direction, selected_files)
        
        self.errors = {}

        log.debug('*** Deleting remote files and dirs...')
        for relpath in update['delete_remote']:
            if not isinstance(relpath,unicode):
                relpath = relpath.decode('utf-8')
            rempath = self.sanitize_remote_path(os.path.join(self.remote_dir,relpath))
            if self.isdir(rempath):
                self.sftp.rmdir(rempath)
            else:
                self.sftp.remove(rempath)

        log.debug('*** Deleting local files and dirs...')
        for relpath in update['delete_local']:
            if not isinstance(relpath,unicode):
                relpath = relpath.decode('utf-8')
            locpath = os.path.join(self.local_dir,relpath)
            if os.path.isdir(locpath):
                os.rmdir(locpath)
            else:
                os.remove(locpath)
                
        log.debug('*** Uploading local files and dirs...')  
        self.errors['upload'] = []
        for relpath in update['update_remote']:
            if not isinstance(relpath,unicode):
                relpath = relpath.decode('utf-8')
            try:
                locpath = os.path.join(self.local_dir,relpath)
                rempath = self.sanitize_remote_path(os.path.join(self.remote_dir,relpath))
                log.debug('*** Uploading : %s' % relpath)  
                if os.path.isdir(locpath):
                    if self.exists(rempath): #Already exists
                        if not self.isdir(rempath): #Old as a file
                            self.sftp.remove(rempath)
                            log.debug('*** sftp.mkdir : %s' % rempath)  
                            self.sftp.mkdir(rempath)
                        utime=os.path.getmtime(locpath)
                        self.sftp.utime(rempath,(utime,utime))
                        remote_objs[relpath]=utime
                    else:
                        log.debug('*** sftp.mkdir : %s' % rempath)
                        self.sftp.mkdir(rempath)
                        utime=os.path.getmtime(locpath)
                        self.sftp.utime(rempath,(utime,utime))
                        remote_objs[relpath]=utime
                else:
                    if self.exists(rempath):
                        if self.isdir(rempath):
                            log.debug('*** sftp.rmdir : %s' % rempath)
                            self.sftp.rmdir(rempath)
                            log.debug('*** put : %s' % locpath)
                            self.sftp.put(locpath,rempath)
                        else:
                            self.patch_to_server(relpath)
                    else:
                        log.debug('put %s, %s' % (locpath,rempath))
                        self.sftp.put(locpath,rempath)
                    utime=os.path.getmtime(locpath)
                    self.sftp.utime(rempath,(utime,utime))
                    remote_objs[relpath]=utime
            except IOError,err:
                self.errors['upload'].append('%s : %s' % (relpath,unicode(err)))
                log.warning('Upload failed %s : %s' % (relpath,str(err))) 
                
        self.errors['download'] = []        
        for relpath in update['update_local']:
            if not isinstance(relpath,unicode):
                relpath = relpath.decode('utf-8')
            try:
                locpath = os.path.join(self.local_dir,relpath)
                rempath = self.sanitize_remote_path(os.path.join(self.remote_dir,relpath))
                log.debug('*** Downloading : %s' % relpath)  
                if self.isdir(rempath):
                    if os.path.exists(locpath): #Already exists
                        if not os.path.isdir(locpath): #Old as a file:
                            log.debug('remove %s' % locpath)
                            os.remove(locpath)
                            
                            log.debug('mkdir %s' % os.path.join(self.local_dir,relpath))
                            os.mkdir(os.path.join(self.local_dir,relpath))
                        utime=self.sftp.lstat(rempath).st_mtime
                        os.utime(locpath,(utime,utime))
                        local_objs[relpath]=utime
                    else:
                        log.debug('mkdir %s' % rempath)
                        os.mkdir(locpath)
                        log.debug('mkdir %s' % locpath)
                        utime=self.sftp.lstat(rempath).st_mtime
                        os.utime(locpath,(utime,utime))
                        local_objs[relpath]=utime
                else:
                    if os.path.exists(locpath):
                        if os.path.isdir(locpath):
                            os.rmdir(locpath)
                            log.debug('rmdir %s' % locpath)
                            self.sftp.get(locpath)
                            log.debug('get %s' % rempath)
                        else:
                            self.patch_from_server(relpath)
                    else:
                        self.sftp.get(rempath,locpath)
                        log.debug('get %s' % rempath)
                    utime=self.sftp.lstat(rempath).st_mtime
                    os.utime(locpath,(utime,utime))
                    local_objs[relpath]=utime
            except IOError,err:
                self.errors['download'].append('%s : %s' % (relpath,unicode(err)))
                log.warning('Download failed %s : %s' % (relpath,str(err)))             
               
        if '.khtsync' in remote_objs:
            del remote_objs['.khtsync']
        try:
            rempath = self.sanitize_remote_path(os.path.join(self.remote_dir,'.khtsync'))
            fh = self.sftp.file(rempath,'wb')
            pickle.dump(remote_objs,fh)
            fh.close()
        except IOError,err:
            log.warning('You have no access to remote dir, deletion will not work')

        if '.khtsync' in local_objs:
            del local_objs['.khtsync']
        with open(os.path.join(self.local_dir,'.khtsync') ,'wb') as fh:
            pickle.dump(local_objs,fh)
        
    def sanitize_remote_path(self, pth):
        '''
        If we're on a windows platform, the remote paths will be of the form
        remotedir/dir_name\\filename, which doesn't work out too well. change
        remote paths to remove the \\ separator
        '''
        if sys.platform == 'win32':
            if os.path.sep in pth:
                return pth.replace(os.path.sep, '/')
        return pth
            
        
    def sanitize_local_path(self):
        '''
        If we're on a windows platform, the remote paths for download will be 
        of the form remotedir/dir_name\\filename, which doesn't work out too well. 
        change these paths to remove the \\ separator
        
        HAVEN"T FOUND A NEED FOR THIS YET
        '''
        pass
        

if __name__ == '__main__':
    un='admin1'
    pw='foo'
    basedir='c:\\Users\\lp76\\tmp'
    ignored_files=['.khtsync','.git']
    rsynchost='192.168.56.101'
    rdir='/scm-repo/git/u/admin1/workspace-apd-lv-pdu-hdhdhf.git'
    # localdir is the concatenation of the local base directory (the working 
    # directory) and the remote directory (minus the leading slash)
    ldir=os.path.join(basedir, rdir[1:])
    syncport=8022
    
    # sync all both ways
    files = None
    d = BOTH
    
    # sync all up
    #d = UP
    
    # sync all down
    #d = DOWN
    
    # selected file tests
    # for up testing
    # files = ['IAmOnlyOnLocal.txt', 'file2.txt', 'weirdness.tst']
    # d = UP
    
    # for down testing
    # files = ['IAmOnlyOnServer.txt', 'um.sh', 'file.txt', 'weirdnesss-Copy.tst']
    # d = DOWN
    
    s = Sync(hostname=rsynchost, port=syncport, username=un, password=pw, local_dir=ldir, remote_dir=rdir, ignored_files=ignored_files)
    s.connect()
    s.sync(d, files)
    s.close()
    if len(s.errors['upload'])>0:
        print "Error occurs while uploading : ", s.errors['upload']
    if len(s.errors['download'])>0:
        print "Error occurs while downloading : ", s.errors['download']

    
    # Original main
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
