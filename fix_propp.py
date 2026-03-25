import json

with open('test_workflow_demo.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

for cell in nb['cells']:
    if cell.get('cell_type') == 'code':
        source = cell['source']
        for i, line in enumerate(source):
            if 'theory_type = "propp"' in line:
                source[i] = line.replace('"propp"', '"THEORY_PROPP_VOGLER_HYBRID"')
                
with open('test_workflow_demo.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
