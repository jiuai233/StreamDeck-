# -*- coding: utf-8 -*-
"""
UUID管理模块
处理配置文件的UUID存储和管理
"""

import json
import uuid
import pathlib
from config import UUID_FILE


def load_or_generate_uuids():
    """加载或生成UUID映射"""
    uuid_file = pathlib.Path(UUID_FILE)
    if uuid_file.exists():
        try:
            with open(uuid_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # 检查是否是旧格式，如果是则转换为新格式
                if "home" not in data and "models" not in data:
                    # 旧格式转换
                    home_uuid = data.get("Home", str(uuid.uuid4()).upper())
                    models = {k: v for k, v in data.items() if k != "Home"}
                    return {
                        "home": home_uuid,
                        "models": models
                    }
                else:
                    # 新格式直接返回
                    return data
        except:
            pass
    
    # 生成新的UUID映射
    uuids = {
        "home": str(uuid.uuid4()).upper(),
        "models": {}
    }
    
    # 保存UUID映射
    with open(uuid_file, 'w', encoding='utf-8') as f:
        json.dump(uuids, f, indent=2, ensure_ascii=False)
    
    return uuids


def get_home_uuid():
    """获取Home UUID"""
    uuids = load_or_generate_uuids()
    return uuids["home"]


def get_model_uuid(model_name):
    """获取模型UUID"""
    uuids = load_or_generate_uuids()
    if model_name not in uuids["models"]:
        uuids["models"][model_name] = str(uuid.uuid4()).upper()
        # 保存更新的映射
        with open(UUID_FILE, 'w', encoding='utf-8') as f:
            json.dump(uuids, f, indent=2, ensure_ascii=False)
    return uuids["models"][model_name]