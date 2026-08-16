'''
デバッグ用ログシステム

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import datetime
import os
import sys
import traceback

class Debug:
    LEVEL_ALL   = 10
    LEVEL_ERROR = 7
    LEVEL_WARN  = 5
    LEVEL_INFO  = 3
    LEVEL_NONE  = 0

    LEVEL = LEVEL_NONE

    _debugReportLog = []
    _debugRecord    = {}

    applicationHome = None

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
    def getDebugReport(cls):
        for t , name, message, tb in cls._debugReportLog:
            yield f"{t.isoformat()}: {name}: {message}"
            if tb:
                for s in tb:
                    yield s

    @classmethod
    def record(cls, name, item, num):
        from config import MAX_CACHE_SIZE_GB
        from config import BLOCK_SIZE
        from config import MAX_CACHE_SIZE
        from config import MAX_WORKERS
        if cls.applicationHome:
            # name がパスだと仮定して相対パスに変換
            if os.path.isabs(name):
                name = os.path.relpath(name, cls.applicationHome)
                name = name.replace("\\", "/")

            localDir = os.path.join(cls.applicationHome, "local")
            os.makedirs(localDir, exist_ok=True)
            filename = os.path.join(localDir, f"record_{MAX_CACHE_SIZE_GB}GB_{BLOCK_SIZE}px_{MAX_CACHE_SIZE}_{MAX_WORKERS}.csv")
            if not os.path.exists(filename):
                with open(os.path.join(filename), "w") as file:
                    file.write("dummy\n")

            try:
                with open(os.path.join(filename), "r") as file:
                    head  = file.readline().strip()
                    lines = file.readlines()
                out = []
                for line in lines:
                    _name, _item, _min, _wma, _latestMax, _max = line.strip().split(",")
                    if name == _name and item == _item:
                        _min       = int(_min)
                        _wma       = int(_wma)
                        _latestMax = int(_latestMax)
                        _max       = int(_max)

                        _latestMax = max(_latestMax, num) if _min<num else num
                        _min       = min(_min, num)
                        _wma       = (_wma*9 + num)//10 if _wma//20 < abs(_wma-num) else _wma
                        _max       = max(_max, num)
                        out.append(f"{_name},{_item},{_min},{_wma},{_latestMax},{_max}\n")
                        name = None
                    else:
                        out.append(line)
                if name:
                    out.append(f"{name},{item},{num},{num},{num},{num}\n")
                
                out = sorted(out, key=lambda x: (x.split(",")[1],int(x.split(",")[2])))

                with open(os.path.join(filename), "w") as file:
                    file.write("name,item,min,wma,latestMax,max\n")
                    file.writelines(out)
            except Exception as e:
                cls.log(cls.__name__, f"Failed to write record.csv", e)
