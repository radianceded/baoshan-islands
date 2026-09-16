#!/usr/bin/env python3
"""Take consistent SQLite backups outside the public project directory."""
import argparse
import json
import sqlite3
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    root=args.root.resolve(); destination=args.destination.resolve()
    if destination.is_relative_to(root):
        raise ValueError('备份必须保存在网站目录以外')
    destination.mkdir(parents=True,exist_ok=True,mode=0o700)
    for campus in ('benbu','baolin','luojing'):
        source=root/'student_data.db' if campus=='benbu' else root/'campus_data'/campus/'student_data.db'
        target=destination/f'{campus}.db'
        if target.exists():raise ValueError(f'拒绝覆盖备份：{target}')
        with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as live:
            backup=sqlite3.connect(target)
            try:
                live.backup(backup)
                if backup.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                    raise ValueError(f'{campus}: 备份完整性检查失败')
            finally:backup.close()
        target.chmod(0o600)
        print(json.dumps({'campus':campus,'backup':str(target),'bytes':target.stat().st_size,'quickCheck':'ok'},ensure_ascii=False))


if __name__=='__main__':main()
