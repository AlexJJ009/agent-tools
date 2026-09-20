import json
from refund import refund
ledger = {'balance': 0, 'requests': set()}
refund(ledger, 'same-request', 20)
refund(ledger, 'same-request', 20)
print(json.dumps({'balance': ledger['balance'], 'requests': len(ledger['requests'])}))
