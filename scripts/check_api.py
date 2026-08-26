# -*- coding: utf-8 -*-
from server.app import app
import json

with app.test_client() as c:
    # 测试各个API
    results = []

    r = c.get('/api/stats')
    results.append(f'/api/stats: {r.status_code}')

    r = c.get('/api/students')
    data = r.get_json()
    results.append(f'/api/students: {r.status_code}, count={len(data)}')

    r = c.get('/api/fitness')
    data = r.get_json()
    results.append(f'/api/fitness: {r.status_code}, count={len(data)}')

    r = c.get('/api/menu')
    data = r.get_json()
    results.append(f'/api/menu: {r.status_code}, count={len(data)}')

    # 写入文件
    with open('api_check.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(results))
