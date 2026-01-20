'''
Flow Control class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import MAX_WORKERS
from utils.ThreadPool import ProcessExecutorInNode
from utils.ThreadPool import PerResourceThreadPoolWrapper

# 同時ノード実行数
MAX_NODE_EXEC = min(4,MAX_WORKERS)

class FlowControl:
    def __init__(self):
        self._nodeExecutor = None
        self.elapsedMs     = 0
    
    def getMaxNodeWorkers(self):
        return MAX_NODE_EXEC
    
    def execute(self, nodes, sendMessage=None, reportProgress=None):
        """フローを実行"""
        if not sendMessage:
            sendMessage = lambda msg: print(msg)

        if not reportProgress:
            reportProgress = lambda id, text, msg, current=None, total=None: ""

        nodes = self._getNodes(nodes)

        startTime = time.time()
        try:
            maxWorkers = MAX_NODE_EXEC+MAX_WORKERS
            processInNodeWorkers = maxWorkers/min(2,MAX_NODE_EXEC)
            with ThreadPoolExecutor(max_workers=maxWorkers) as processExecutor:
                executor = processExecutor
                self._nodeExecutor = PerResourceThreadPoolWrapper()
                self._nodeExecutor.setExecutor(processExecutor, MAX_NODE_EXEC)
                ProcessExecutorInNode.setExecutor(processExecutor, processInNodeWorkers) # グローバルにスレッドプールを提供
                
                sendMessage("フロー実行中...\n") # ステータス表示
                
                # 入次数を計算
                inDegree = {node: 0 for node in nodes}
                for node in nodes:
                    for n in node.outputNodes:
                        if n in inDegree:
                            inDegree[n] += 1
                
                self.futures = {}
                while nodes:
                    # 実行可能なノード(入次数0)で実行不要なものを取り除き、後続ノードの入次数を減らす
                    for node in nodes.copy():
                        if 0 == inDegree[node] and not node.needsReprocessing():
                            nodes.remove(node)
                            for n in node.outputNodes:
                                if n in inDegree:
                                    inDegree[n] -= 1

                    # 実行可能なノード(入次数0)を初期キューに追加
                    readyNodes = [node for node in nodes if 0 == inDegree[node] and node.needsReprocessing() and not node in self.futures.values()]
                    text=""
                    sep="開始: "
                            
                    for node in readyNodes:
                        reportProgress( id(node), node.name, "待機中")
                        context = {
                            'progress_callback': lambda msg, current=None, total=None, id=id(node), t=node.name: reportProgress( id, t, msg, current, total)
                        }
                        future = self._nodeExecutor.submit(self, self._executeNode, node, context)
                        self.futures[future] = node
                        text +=f"{sep}{node.name}"
                        sep=","
                    
                    if 0<len(text):
                        sendMessage(f"{text}\n")

                    # ノード完了を監視し、後続ノードを起動
                    for future in as_completed(self.futures):
                        node        = self.futures.pop(future)
                        elapsedMs = future.result()
                        reportProgress(id(node), node.name, "完了", -1, -1)
                        sendMessage(f"完了: {node.name} ({elapsedMs} ms)\n")
                        break
        except:
            endTime = time.time()
            elapsedMs = int((endTime - startTime) * 1000)
            sendMessage(f"エラー終了: ({elapsedMs} ms)\n")
            raise
        finally:
            self._nodeExecutor = None
        
        endTime = time.time()
        elapsedMs = int((endTime - startTime) * 1000)
        self.elapsedMs = elapsedMs
        sendMessage(f"フロー実行完了: ({elapsedMs} ms)\n")
    
    def _getNodes(self, nodes):
        """ノードを入力方向に再帰的検索"""
        inNodes = set()
        for node in nodes:
            if not node in inNodes:
                inNodes.add(node)
                inNodes.update(self._getNodes([x for x in node.inputNodes if not x in inNodes]))
        return list(inNodes)
    
    def _executeNode(self, node, context):
        """ノード実行"""
        try:
            # 時間を測定
            startTime = time.time()
            node.execute(context)
            endTime = time.time()
            elapsedMs = int((endTime - startTime) * 1000)
            return elapsedMs
        except Exception as e:
            raise Exception(f"ノード '{node.name}' でエラー: {str(e)}") from e

    def stop(self):
        """ノードの実行を中断"""
        if self._nodeExecutor:
            ProcessExecutorInNode.shutdown(wait=False,cancel_futures=True)
            self._nodeExecutor.shutdown(wait=False,cancel_futures=True)
