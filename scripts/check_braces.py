import re

with open('hongkou_v4.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 提取第一个 script 块
m = re.search(r'<script>(.*?)</script>', content, re.DOTALL)
if m:
    script = m.group(1)
    print(f"Script length: {len(script)}")
    # 只统计不在字符串中的花括号
    depth = 0
    in_string = False
    string_char = None
    escape = False
    
    for i, c in enumerate(script):
        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c in '"\'`':
            if not in_string:
                in_string = True
                string_char = c
            elif c == string_char:
                in_string = False
                string_char = None
        elif not in_string:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth < 0:
                    # 找到问题！显示前后上下文
                    print(f"Extra }} at position {i}")
                    ctx = script[max(0,i-50):i+50]
                    ctx_safe = ''.join(c if ord(c) < 128 else '.' for c in ctx)
                    print(f"Context: ...{ctx_safe}...")
                    break
    if depth >= 0:
        print(f"Final depth: {depth}")
else:
    print("No script found")
