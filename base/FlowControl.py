'''
Flow Control class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import MAX_WORKERS
from utils.ThreadPool import ProcessExecutor

# 同時ノード実行数
MAX_NODE_WORKERS = 4

class FlowControl:
    def __init__(self):
        pass
    
    def getMaxNodeWorkers(self):
        return MAX_NODE_WORKERS
    
    def execute(self, nodes, sendMessage=None, reportProgress=None):
        self.nodes = nodes

        if not sendMessage:
            sendMessage = lambda msg: print(msg)

        if not reportProgress:
            reportProgress = lambda id, text, msg, current=None, total=None: ""

        startTime = time.time()
        try:
            with(ThreadPoolExecutor(max_workers=MAX_NODE_WORKERS) as nodeExecutor,
                 ThreadPoolExecutor(max_workers=MAX_WORKERS)      as processExecutor):
                
                ProcessExecutor.setExecutor(processExecutor) # グローバルにスレッドプールを提供

                # ステータス表示
                sendMessage("フロー実行中...\n")
                
                # トポロジカルソートで処理レベルを決定
                processLevels = self.getProcessLevels()
                
                for level, nodes in enumerate(processLevels):
                    if nodes:
                        # 同レベルのノードを並列実行
                        text=""
                        sep="開始: "
                        
                        futures = []
                        for node in nodes:
                            # 再処理が必要かチェック
                            if node.needsReprocessing():
                                reportProgress( id(node), node.text, "待機中")
                                context = {
                                    'progress_callback': lambda msg, current=None, total=None, id=id(node), t=node.text: reportProgress( id, t, msg, current, total)
                                }
                                future = nodeExecutor.submit(self._executeNode, node, context)
                                futures.append((node, future))
                                text +=f"{sep}{node.text}"
                                sep=","
                        
                        if 0<len(text):
                            sendMessage(f"{text}\n")

                        # 同レベルの全ノードの完了を待つ
                        futureToNode = {future: node for node, future in futures}
                        for future in as_completed([f for n, f in futures]):
                            node = futureToNode[future]
                            elapsedMs = future.result()
                            reportProgress(id(node), node.text, "完了", -1, -1)
                            sendMessage(f"完了: {node.text} ({elapsedMs}ms)\n")
        except:
            endTime = time.time()
            elapsedMs = int((endTime - startTime) * 1000)
            sendMessage(f"エラー終了:({elapsedMs}ms)\n")
            raise
        
        endTime = time.time()
        elapsedMs = int((endTime - startTime) * 1000)
        sendMessage(f"フロー実行完了:({elapsedMs}ms)\n")

    def getProcessLevels(self):
        """ノードを依存レベル別にグループ化"""
        # 入次数を計算
        inDegree = {node: 0 for node in self.nodes}
        for node in self.nodes:
            for connectedNode in node.outputNodes:
                inDegree[connectedNode] += 1
        
        levels = []
        remaining = set(self.nodes)
        
        while remaining:
            # 現在のレベルで実行可能なノードを収集
            currentLevel = [node for node in remaining if inDegree[node] == 0]
            if not currentLevel:
                break
            
            levels.append(currentLevel)
            
            # 処理したノードを削除し、後続ノードの入次数を更新
            for node in currentLevel:
                remaining.remove(node)
                for connectedNode in node.outputNodes:
                    if connectedNode in remaining:
                        inDegree[connectedNode] -= 1
        
        return levels
    
    def _executeNode(self, node, context):
        """ノード実行"""
        try:
            # 時間を測定
            startTime = time.time()
            node.execute(context)
            # 実行後にハッシュを更新
            endTime = time.time()
            elapsedMs = int((endTime - startTime) * 1000)
            return elapsedMs
        except Exception as e:
            raise Exception(f"ノード '{node.text}' でエラー: {str(e)}") from e
