#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2010 Benoît HERVIER
# Licenced under GPLv3

""" Sync two folder over ssh : Config GUI"""

import sip
sip.setapi('QString', 2)
sip.setapi('QVariant', 2)

import khtsync
__version__ = khtsync.__version__

DAEMON_PATH = '/home/user/MyDocs/Projects/khtsync/khtsync_daemon.py'

import os
from subprocess import Popen

from PyQt4.QtGui import QMainWindow, \
    QSizePolicy, \
    QApplication, \
    QPushButton, \
    QGridLayout, \
    QWidget, \
    QScrollArea, \
    QLabel, \
    QSpinBox, \
    QDialog, \
    QLineEdit, \
    QVBoxLayout, \
    QHBoxLayout, \
    QLayout, \
    QListView, \
    QAbstractItemView
    
    
from PyQt4.QtCore import QSettings, \
    Qt, pyqtSignal, QAbstractListModel, QModelIndex

class AccountDialog(QDialog):
    """ Edit an account dialog """
    save = pyqtSignal(int, unicode,unicode,unicode, \
                      unicode,unicode,unicode)
    delete = pyqtSignal(int)
    
    def __init__(self, parent=None,index=0,account=None):
        super(QDialog, self).__init__(parent)
        self.index = index
        self.hostname = QLineEdit(account.hostname)
        self.hostname.setInputMethodHints(Qt.ImhNoAutoUppercase)
        self.port = QLineEdit(unicode(account.port))
        self.port.setInputMethodHints(Qt.ImhNoAutoUppercase)
        self.username = QLineEdit(account.username)
        self.username.setInputMethodHints(Qt.ImhNoAutoUppercase)
        self.password = QLineEdit(account.password)
        self.password.setInputMethodHints(Qt.ImhNoAutoUppercase)
        self.local_dir = QLineEdit(account.local_dir)
        self.local_dir.setInputMethodHints(Qt.ImhNoAutoUppercase)
        self.remote_dir = QLineEdit(account.remote_dir)
        self.remote_dir.setInputMethodHints(Qt.ImhNoAutoUppercase)

        self.save_button = QPushButton('Save')
        self.delete_button = QPushButton('Delete')
        
        gridLayout =  QGridLayout()
        leftLayout =  QVBoxLayout()

        gridLayout.addWidget(QLabel('Hostname'), 0, 0)
        gridLayout.addWidget(self.hostname, 0, 1)

        gridLayout.addWidget(QLabel('Port'), 1, 0)
        gridLayout.addWidget(self.port, 1, 1)

        gridLayout.addWidget(QLabel('Username'), 2, 0)
        gridLayout.addWidget(self.username, 2, 1)

        gridLayout.addWidget(QLabel('Password'), 3, 0)
        gridLayout.addWidget(self.password, 3, 1)

        gridLayout.addWidget(QLabel('Local dir'), 4, 0)
        gridLayout.addWidget(self.local_dir, 4, 1)

        gridLayout.addWidget(QLabel('Remote dir'), 5, 0)
        gridLayout.addWidget(self.remote_dir, 5, 1)
        
        leftLayout.addLayout(gridLayout)
        buttonLayout =  QVBoxLayout()
        buttonLayout.addWidget(self.save_button)
        buttonLayout.addWidget(self.delete_button)
        buttonLayout.addStretch()
        mainLayout =  QHBoxLayout()
        mainLayout.addLayout(leftLayout)
        mainLayout.addLayout(buttonLayout)
        self.setLayout(mainLayout)

        mainLayout.setSizeConstraint( QLayout.SetFixedSize)

        self.save_button.clicked.connect(self.saveit)
        self.delete_button.clicked.connect(self.deleteit)
        self.setWindowTitle("Edit account")

    def deleteit(self):
        self.delete.emit(self.index)
        self.hide()

    def saveit(self):
        self.save.emit(self.index, \
                       self.hostname.text(), \
                       self.port.text(), \
                       self.username.text(),
                       self.password.text(), \
                       self.local_dir.text(), \
                       self.remote_dir.text())
        self.hide()
        
class AccountsModel(QAbstractListModel):
    dataChanged = pyqtSignal(QModelIndex,QModelIndex)
    
    def __init__(self):
        QAbstractListModel.__init__(self)
        self._items = []

    def set(self,mlist):
        self._items =mlist
        self.dataChanged.emit(self.createIndex(0, 0),
                              self.createIndex(0,
                              len(self._items)))
        
    def rowCount(self, parent = QModelIndex()):
        return len(self._items)
        
    def data(self, index, role = Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return self._items[index.row()].hostname
        else:
            return None

class AccountsView(QListView):
    def __init__(self, parent = None):
        QListView.__init__(self, parent)   
        self.setEditTriggers(QAbstractItemView.SelectedClicked)
            
class SSHSyncAccount():
    def __init__(self, hostname='Unknow', username='', password='', port=22, local_dir='', remote_dir=''):
       self.hostname = hostname
       self.username = username
       self.password = password
       self.port = 22
       self.local_dir = local_dir
       self.remote_dir = remote_dir
    
class KhtSettings(QMainWindow):
    def __init__(self, parent=None):
        global isMAEMO
        QMainWindow.__init__(self,parent)
        self.parent = parent

        try:
            self.setAttribute(Qt.WA_Maemo5AutoOrientation, True)
            self.setAttribute(Qt.WA_Maemo5StackedWindow, True)
            isMAEMO = True
        except:
            isMAEMO = False
        self.setWindowTitle("KhtSync Config")

        #Resize window if not maemo
        if not isMAEMO:
            self.resize(800, 600)
            
        self.settings = QSettings()
        
        self.setupGUI()        
        self.loadPrefs()
        self.accounts_model.set(self.accounts)
        self.show()

    def isRunning(self):
        return os.path.isfile('/tmp/khtsync.pid')

    def runorstop(self):
        if self.isRunning():
            os.system('/usr/bin/python ' + DAEMON_PATH + ' stop')
            self.daemon_button.setText('Run')
        else:
            os.system('/usr/bin/python ' + DAEMON_PATH + ' start')
            self.daemon_button.setText('Stop')
            
    def loadPrefs(self):
        if self.settings.contains('refresh_interval'):
            self.refresh_interval.setValue(int(self.settings.value('refresh_interval')))
        #Load account
        self.accounts = []
        nb_accounts = self.settings.beginReadArray('accounts')
        for index in range(nb_accounts):
            self.settings.setArrayIndex(index)
            self.accounts.append(SSHSyncAccount(hostname=self.settings.value('hostname'), \
                port=int(self.settings.value('port')), \
                username=self.settings.value('username'), \
                password=self.settings.value('password'), \
                local_dir=self.settings.value('local_dir'), \
                remote_dir=self.settings.value('remote_dir')))
        self.settings.endArray()
    
    def savePrefs(self):
        self.settings.setValue('refresh_interval',self.refresh_interval.value())
        self.settings.beginWriteArray("accounts")
        for index,account in enumerate(self.accounts):
            self.settings.setArrayIndex(index)
            self.settings.setValue("hostname", account.hostname)
            self.settings.setValue("port", account.port )
            self.settings.setValue("username", account.username )
            self.settings.setValue("password",  account.password )
            self.settings.setValue("local_dir", account.local_dir )
            self.settings.setValue("remote_dir", account.remote_dir )
        self.settings.endArray()
     
    def closeEvent(self,widget,*args):
        self.savePrefs()
                     
    def setupGUI(self):
        global isMAEMO
        self.aWidget = QWidget(self)
        self._rmain_layout = QVBoxLayout(self.aWidget)
        
        self._main_layout = QGridLayout()
        self.aWidget.setSizePolicy( QSizePolicy.Expanding, QSizePolicy.Expanding)

        gridIndex = 0

        if self.isRunning():
            self.daemon_button = QPushButton('Stop')
        else:
            self.daemon_button = QPushButton('Run')
        self.daemon_button.clicked.connect(self.runorstop)
        
        self._main_layout.addWidget(self.daemon_button,gridIndex,0)

        self.show_log = QPushButton('Show logs')
        self.show_log.clicked.connect(self.showlog)
        self._main_layout.addWidget(self.show_log,gridIndex,1)
        gridIndex += 1                

        self._main_layout.addWidget(QLabel('Refresh interval (min)'),gridIndex,0)

        self.refresh_interval = QSpinBox()
        self.refresh_interval.setMinimum(10)
        self._main_layout.addWidget(self.refresh_interval,gridIndex,1)
        gridIndex += 1

        self.accounts_model = AccountsModel()
        self.accounts_view = AccountsView()
        self.accounts_view.clicked.connect(self.edit_account)
        self.accounts_view.setModel(self.accounts_model)
        self._rmain_layout.addLayout(self._main_layout)
        self.add_acc_button = QPushButton('Add account')
        self.add_acc_button.clicked.connect(self.add_account)
        self._rmain_layout.addWidget(self.add_acc_button)
        self._rmain_layout.addWidget(self.accounts_view)
        
        self.aWidget.setLayout(self._rmain_layout)
        self.setCentralWidget(self.aWidget)

    def showlog(self):
        import commands
        fileHandle = open('/tmp/khtsync.sh', 'wb')
        fileHandle.write('#!/bin/sh\n/usr/bin/tail -f /tmp/khtsync.log\n')
        fileHandle.close()
        commands.getoutput("chmod +x /tmp/khtsync.sh")
        
        os.system('/usr/bin/osso-xterm /tmp/khtsync.sh')
        
    def add_account(self):
        self.accounts.append(SSHSyncAccount())
        self.accounts_model.set(self.accounts)
    
    def edit_account(self):
        for index in self.accounts_view.selectedIndexes():
            account_index = index.row()
        self.accountDlg = AccountDialog(self,account_index,self.accounts[account_index])
        self.accountDlg.save.connect(self.save_account)
        self.accountDlg.delete.connect(self.delete_account)
        self.accountDlg.show()

    def delete_account(self, index):
        del self.accounts[index]
        self.accounts_model.set(self.accounts)
        
    def save_account(self, index, hostname, port, username, password, local_dir, remote_dir):
        self.accounts[index].hostname = hostname
        self.accounts[index].username = username
        self.accounts[index].port = port
        self.accounts[index].username = username
        self.accounts[index].local_dir = local_dir
        self.accounts[index].remote_dir = remote_dir
        self.accounts_model.set(self.accounts)
        
if __name__ == '__main__':
    import sys
    app = QApplication(sys.argv)
    app.setOrganizationName("Khertan Software")
    app.setOrganizationDomain("khertan.net")
    app.setApplicationName("KhtSync")
    
    khtsettings = KhtSettings()
    sys.exit(app.exec_())