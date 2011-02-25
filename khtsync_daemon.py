#!/usr/bin/env python
 
import sys, time
from daemon import Daemon
from PyQt4.QtCore import QSettings

import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S',
                    filename='/tmp/khtsync.log',
                    filemode='w')

import khtsync
                    
class KhtSyncDaemon(Daemon):
    def run(self):
        settings = QSettings("KhtSync", "Khertan Softwares")
        logging.debug('Setting loaded')
        while True:
            try:
                #Re read the settings
                settings.sync()
                logging.debug('Setting synced')
                
                #Verify the default interval
                if not settings.contains('refresh_interval'):
                    refresh_interval = 600
                else:
                    refresh_interval = int(settings.value('refresh_interval'))*60
                    if refresh_interval<600:
                        refresh_interval = 600
                logging.debug('refresh interval loaded')
                        
                nb_accounts = settings.beginReadArray('accounts')
                for index in range(nb_accounts):
                    settings.setArrayIndex(index)
                    sync = khtsync.Sync(hostname=settings.value('hostname'), \
                        port=int(settings.value('port')), \
                        username=settings.value('username'), \
                        password=settings.value('password'), \
                        local_dir=settings.value('local_dir'), \
                        remote_dir=settings.value('remote_dir'))
                    s.connect()
                    s.sync()
                    s.close()   
                settings.endArray()
                logging.debug('Finished loop')
                                
            except Error,err:
                logging.exception(unicode(err))
                        
            time.sleep(refresh_interval)
 
if __name__ == "__main__":
        daemon = KhtSyncDaemon('/tmp/khtsync.pid')
        if len(sys.argv) == 2:
                if 'start' == sys.argv[1]:
                        daemon.start()
                elif 'stop' == sys.argv[1]:
                        daemon.stop()
                elif 'restart' == sys.argv[1]:
                        daemon.restart()
                else:
                        print "Unknown command"
                        sys.exit(2)
                sys.exit(0)
        else:
                print "usage: %s start|stop|restart" % sys.argv[0]
                sys.exit(2)