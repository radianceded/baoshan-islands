# -*- coding: utf-8 -*-
"""
启动宝山实验智慧教育平台 API 服务
"""
import os
import sys

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.app import app, DB_PATH

if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        print(f"错误: 数据库文件不存在 {DB_PATH}")
        print("请先运行 database_builder.py 构建数据库")
        sys.exit(1)
    
    print("=" * 50)
    print("宝山实验智慧教育平台")
    print("=" * 50)
    print(f"访问地址: http://localhost:5000")
    print(f"数据库: {DB_PATH}")
    print("=" * 50)
    print("按 Ctrl+C 停止服务")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
