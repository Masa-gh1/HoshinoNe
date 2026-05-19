'''
Flow File class

Copyright (c) 2025 Masakazu Inoue
All rights reserved.

@author: Masakazu Inoue
'''
import json

from Version import VERSION

class FlowFile:
    def __init__(self):
        pass
    
    def save(self, filePath, canvas, editor, nodes, trays):
        serial = {
            "version": VERSION,
            "nodes": [],
            "trays": [],
        }
        
        # ノードの index マッピングを作成
        nodeIdxs = {id(node): index for index, node in enumerate(nodes)}        
        
        # ノードとトレイの最小座標を取得
        minNodeX = min(node.view.x for node in nodes)
        minNodeY = min(node.view.y for node in nodes)
        minTrayX = min(tray.x for tray in trays) if trays else None
        minTrayY = min(tray.y for tray in trays) if trays else None
        minX = min(minNodeX, minTrayX) if minTrayX else minNodeX
        minY = min(minNodeY, minTrayY) if minTrayY else minNodeY
        
        # オフセットを計算(マージンを加える)
        offsetX = -minX + 40
        offsetY = -minY + 40
        
        # ノード情報を保存
        for node in nodes:
            # ノードのZ-orderを取得
            allItems = canvas.find_all()
            nodeZOrder = max(allItems.index(node.view.rect), allItems.index(node.view.label))
            
            # データを保存
            nodeSerial = {
                "index" : nodeIdxs[id(node)],
                "zOrder": nodeZOrder
            }
            nodeSerial.update(node.serialize())
            nodeSerial["x"] += offsetX
            nodeSerial["y"] += offsetY
            serial["nodes"].append(nodeSerial)
            
            # 接続ノードを index に変換
            connections = []
            for nodeid in nodeSerial["connections"]:
                connections.append(nodeIdxs[nodeid])
            nodeSerial["connections"] = connections
        
        # トレイ情報を保存
        for tray in trays:
            # トレイのZ-orderを取得
            allItems = canvas.find_all()
            trayZOrder = max(allItems.index(tray.rect), allItems.index(tray.label))
            traySerial = {
                "zOrder": trayZOrder,
            }
            traySerial.update(tray.serialize())
            traySerial["x"] += offsetX
            traySerial["y"] += offsetY
            serial["trays"].append(traySerial)

        if filePath:
            with open( filePath, 'w', encoding='utf-8') as f:
                import numpy as np
                class JSONEncoder(json.JSONEncoder):
                    def default( self, obj):
                        if isinstance( obj, np.floating):
                            return float(obj)
                        else:
                            return json.JSONEncoder.default(self, obj)
                
                json.dump(serial, f, ensure_ascii=False, indent=2, cls=JSONEncoder)
        
        return(serial)

    def load(self, filePath, create, canvas, editor):
        # return nodes, trays, connections, zOrderObj
        try:
            with open(filePath, 'r', encoding='utf-8') as f:
                serial = json.load(f)
            if not "version" in serial:
                var = [0,0,0]
            else:
                # format 99.99.99999999
                var = [int(x) for x in serial["version"].split(".")]

            if [0,0,0] == var:
                old = oldFlowFile()
                return old.load_20251129(serial, create, canvas, editor)
            elif var <= [0,2,20260207]:
                old = oldFlowFile()
                return old.load_20260207(serial, create, canvas, editor)
            else:
                return self.load_now(serial, create, canvas, editor)
        except:
            raise
    
    @staticmethod
    def load_now(serial, create, canvas, editor):
        # zOrder 順を収集
        zOrderMap = {}

        # 接続を収集
        connectionIds = []

        # ノードをファイル順序で作成
        nodeIdxMap = {}
        nodes = []
        for nodeSerial in serial["nodes"]:
            node = create(nodeSerial["type"])
            node.deserialize(nodeSerial)
            node._loadIndex = nodeSerial["index"]
            nodes.append(node)
            nodeIdxMap[nodeSerial["index"]] = node
            zOrderMap[nodeSerial["zOrder"]] = node
            for toId in nodeSerial["connections"]:
                connectionIds.append((node, toId))

        # トレイをファイル順序で作成
        trays = []
        for traySerial in serial["trays"]:
            tray = create("Tray")
            tray.deserialize(traySerial)
            trays.append(tray)
            zOrderMap[traySerial["zOrder"]] = tray

        # 接続を作成（双方向）
        connections = []
        for fromNode, toId in connectionIds:
            toNode = nodeIdxMap[toId]
            fromNode.outputNodes.append(toNode)
            toNode.inputNodes.append(fromNode)
            connections.append((fromNode, toNode))

        # Z-orderでソートされたオブジェクト
        zOrderMap =  {key: zOrderMap[key] for key in sorted(zOrderMap)}
        zOrderObj = list(zOrderMap.values())
            
        return nodes, trays, connections, zOrderObj

######################
# ここから旧ファイル対応
class oldFlowFile:
    @staticmethod
    def load_20260207(serial, create, canvas, editor):
        """
        旧フォーマットのロード
        {
            ...
            "nodes": [
                {
                ...
                "type": "tensor"
                "planeCount": 3,  # del
                "planeNames": [   # -> "planes": [
                ...
                },
                {
                ...
                "type": "coefficients"
                "planeCount": 3,  # del
                "planeNames": [   # -> "planes": [
                ...
                }
            ]
            ...
        }
        """

        for node in serial["nodes"]:
            if node["type"] in ("tensor", "coefficients"):
                node["planes"] = node["planeNames"]
                del node["planeCount"]
                del node["planeNames"]

        return FlowFile.load_now(serial, create, canvas, editor)

    @staticmethod
    def load_20251129(serial, create, canvas, editor):
        """
        旧フォーマットのロード
        {
            "nodes": [
                {
                "id": 0,
                "type": "xxx",
                "x": 186,
                "y": 629,
                "text": "XXX",
                "zOrder": 55,
                "yyy": "YYY"
                },,,
            ],
            "connections": [
                {
                "from": 1,
                "to": 7
                },,,
            ],
            "trays": [
                {
                "x": 93,
                "y": 188,
                "width": 227,
                "height": 204,
                "title": "XXX",
                "zOrder": 1
                },,,
            ]
        }
        """
        
        # zOrder 順を収集
        zOrderMap = {}

        # ノードをファイル順序で作成
        nodeIdMap = {}
        nodes = []
        for nodeSerial in serial["nodes"]:
            node = create(nodeSerial["type"])
            node.deserialize(nodeSerial)
            node._loadIndex = nodeSerial["id"]
            nodes.append(node)
            nodeIdMap[nodeSerial["id"]] = node
            zOrderMap[nodeSerial["zOrder"]] = node
        
        # トレイをファイル順序で作成
        trays = []
        if "trays" in serial:
            for traySerial in serial["trays"]:
                tray = create("Tray")
                tray.deserialize(traySerial)
                trays.append(tray)
                zOrderMap[traySerial["zOrder"]] = tray
        
        # 接続を作成（双方向）
        connections = []
        for connection in serial["connections"]:
            fromNode = nodeIdMap[connection["from"]]
            toNode = nodeIdMap[connection["to"]]
            fromNode.outputNodes.append(toNode)
            toNode.inputNodes.append(fromNode)
            connections.append((fromNode, toNode))

        # Z-orderでソートされたオブジェクト
        zOrderMap =  {key: zOrderMap[key] for key in sorted(zOrderMap)}
        zOrderObj = list(zOrderMap.values())
        
        return nodes, trays, connections, zOrderObj
