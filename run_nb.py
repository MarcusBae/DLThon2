import json
import traceback
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

try:
    with open('test_workflow_demo.ipynb', encoding='utf-8') as f:
        nb = json.load(f)
    g = globals()
    for cell in nb['cells']:
        if cell['cell_type'] == 'code':
            source = ''.join(cell['source'])
            exec(source, g)
except Exception as e:
    traceback.print_exc()
