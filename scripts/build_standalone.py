#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打包脚本：将所有JS模块内联到HTML中，生成独立文件
"""

import re
import os

def read_file(filepath):
    """读取文件内容"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"读取文件失败 {filepath}: {e}")
        return ""

def build_standalone():
    # 读取主HTML文件
    html_content = read_file('baoshan_v4.7.html')
    
    # 定义需要内联的JS文件（按顺序）
    js_files = [
        ('js/api.js', '<script src="js/api.js"></script>'),
        ('js/student-service.js', '<script src="js/student-service.js"></script>'),
        ('js/menu_data.js', '<script src="js/menu_data.js"></script>'),
        ('js/modules/dashboard.js', '<script src="js/modules/dashboard.js"></script>'),
        ('js/modules/canteen.js', '<script src="js/modules/canteen.js"></script>'),
        ('js/modules/resources.js', '<script src="js/modules/resources.js"></script>'),
        ('js/modules/awards.js', '<script src="js/modules/awards.js"></script>'),
        ('js/modules/ai-tools.js', '<script src="js/modules/ai-tools.js"></script>'),
    ]
    
    # 逐个替换script标签为内联代码
    for js_path, script_tag in js_files:
        js_content = read_file(js_path)
        if js_content:
            # 创建内联script标签
            inline_script = f'<script>\n{js_content}\n</script>'
            # 替换原script标签
            html_content = html_content.replace(script_tag, inline_script)
            print(f"[OK] 已内联: {js_path}")
        else:
            print(f"[SKIP] 跳过: {js_path}")
    
    # 移除Dexie.js外部引用（使用CDN或内联简化版）
    # 这里我们保留CDN链接，因为Dexie较大
    
    # 创建dist目录
    os.makedirs('dist', exist_ok=True)
    
    # 写入独立HTML文件
    output_path = 'dist/宝山实验智慧教育平台.html'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"\n[Done] 打包完成: {output_path}")
    
    # 计算文件大小
    file_size = os.path.getsize(output_path)
    print(f"[Size] 文件大小: {file_size / 1024:.1f} KB")
    
    return output_path

if __name__ == '__main__':
    build_standalone()
