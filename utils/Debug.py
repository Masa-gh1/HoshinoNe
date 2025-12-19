'''
デバッグ用ログシステム

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import datetime
import os
import traceback

class Debug:
    LEVEL_ALL   = 10
    LEVEL_ERROR = 7
    LEVEL_WARN  = 5
    LEVEL_INFO  = 3
    LEVEL_NONE  = 0

    LEVEL = LEVEL_NONE

    _debugReportLog = []

    @classmethod
    def isTestMode(cls):
        return os.getenv('DEBUG_TEST_MODE', '').lower() in ['1', 'true', 'yes']

    @classmethod
    def log(cls, name, message, excep=None):
        if excep:
            tb = traceback.format_exception(excep)
        else:
            tb = None

        t = datetime.datetime.now()
        context = (t , name, message, tb)
        cls._debugReportLog.append(context)

        if cls.isTestMode() or Debug.LEVEL_NONE < Debug.LEVEL:
            print(f"{t.isoformat()}: {name}: {message}")
            if tb:
                for s in tb:
                    print(s)
    
    @classmethod
    def getDebugReport(self):
        for t , name, message, tb in self._debugReportLog:
            yield f"{t.isoformat()}: {name}: {message}"
            if tb:
                for s in tb:
                    yield s
