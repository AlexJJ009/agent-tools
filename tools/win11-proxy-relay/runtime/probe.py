"""Bounded HTTPS payload canary. No retry: expose the first failure."""
import argparse
import json
import time
import urllib.request


def probe(proxy, timeout=15):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({'http': proxy, 'https': proxy}))
    # ProxyHandler respects no_proxy; remove it for an explicit diagnostic route.
    import os
    for key in ('no_proxy', 'NO_PROXY'):
        os.environ.pop(key, None)
    cases = [
        ('cloudflare', 'https://www.cloudflare.com/cdn-cgi/trace', lambda b: any(x.startswith('ip=') for x in b.decode().splitlines())),
        ('pypi', 'https://pypi.org/pypi/six/1.17.0/json', lambda b: json.loads(b)['info']['version'] == '1.17.0' and json.loads(b)['info']['name'] == 'six'),
        ('huggingface', 'https://huggingface.co/gpt2/resolve/main/config.json', lambda b: json.loads(b)['model_type'] == 'gpt2'),
    ]
    results = []
    for name, url, validate in cases:
        started = time.monotonic()
        try:
            with opener.open(url, timeout=timeout) as response:
                body = response.read(1024 * 1024)
                ok = response.status == 200 and validate(body)
            result = {'site': name, 'ok': bool(ok), 'bytes': len(body)}
        except Exception as exc:
            result = {'site': name, 'ok': False, 'error': str(exc)}
        result['seconds'] = round(time.monotonic() - started, 3)
        results.append(result)
    return {'proxy': proxy, 'ok': all(r['ok'] for r in results), 'results': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--proxy', default='http://127.0.0.1:17897')
    parser.add_argument('--timeout', type=float, default=15)
    args = parser.parse_args()
    result = probe(args.proxy, args.timeout)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(0 if result['ok'] else 1)
