# -*- coding: utf-8 -*-
"""ID 库:读 games/<slug>/items.txt (utf-8,三列 ID/名称/分类)."""


def load_items(path):
    items = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if not line.strip():
                continue
            p = line.split('\t')
            try:
                iid = int(p[0])
            except ValueError:
                continue
            items.append({
                'id': iid,
                'name': p[1] if len(p) > 1 else '',
                'type': p[2] if len(p) > 2 else '',
            })
    items.sort(key=lambda x: x['id'])
    return items
