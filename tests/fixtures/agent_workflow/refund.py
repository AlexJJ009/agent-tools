"""In-memory fixture only; no payment service connection."""
def refund(ledger, key, amount):
    if key not in ledger['requests']:
        ledger['balance'] += amount
        ledger['requests'].add(key)
    return ledger['balance']
