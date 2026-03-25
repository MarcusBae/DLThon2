import json

with open('test_workflow_demo.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

for cell in nb['cells']:
    if cell.get('cell_type') == 'code':
        cell['outputs'] = []
        cell['execution_count'] = None

with open('test_workflow_demo.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
