"""Build private Windows sing-box configs from the local v2rayN database.

Never fetch or print subscription credentials. Run again after updating feitu
in v2rayN, validate the result, then reload the dedicated core explicitly.
"""
import argparse
import copy
import datetime
import json
import pathlib
import re
import shutil
import sqlite3
import sys

from settings import load_settings

ROOT = pathlib.Path(__file__).resolve().parent
SOURCES = ('feitu', 'miaomiao')
PREFIX_BY_SOURCE = {'feitu': 'feitu', 'miaomiao': 'miaomiao'}
METADATA_WORDS = ('剩余', '到期', '重置', '套餐', '官网', '公告', 'error')


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def default_db(settings):
    return pathlib.Path(settings['v2rayn_dir']) / 'guiConfigs' / 'guiNDB.db'


def is_metadata_row(name):
    lowered = (name or '').lower()
    return any(word.lower() in lowered for word in METADATA_WORDS)


def sing_box_utls_fingerprint(value):
    fingerprint = (value or '').strip().lower()
    if fingerprint == 'qq':
        return 'chrome'
    return fingerprint


def convert_profile_row(row, source, blocked_pattern):
    r = dict(row)
    tag = PREFIX_BY_SOURCE[source] + '-' + r['IndexId']
    name = r.get('Remarks') or ''
    if is_metadata_row(name):
        return None, {'tag': tag, 'source': source, 'name': name, 'reason': 'metadata_row'}
    if not r.get('Address') or not r.get('Port'):
        return None, {'tag': tag, 'source': source, 'name': name, 'reason': 'missing_address_or_port'}
    if blocked_pattern.search(name):
        return None, {'tag': tag, 'source': source, 'name': name, 'reason': 'blocked_by_policy'}

    extra = json.loads(r.get('ProtoExtra') or '{}')
    node = {'tag': tag, 'server': r['Address'], 'server_port': r['Port']}
    if r['ConfigType'] == 11:
        # v2rayN 7.19.5 EConfigType.Anytls = 11.
        node.update(type='anytls', password=r['Password'])
        node['tls'] = {'enabled': True, 'insecure': str(r.get('AllowInsecure')).lower() == 'true'}
        if r.get('Sni'):
            node['tls']['server_name'] = r['Sni']
        if r.get('Alpn'):
            node['tls']['alpn'] = r['Alpn'].split(',')
        if extra:
            raise RuntimeError('Unexpected AnyTLS options; conversion needs review')
    elif r['ConfigType'] == 3:
        method = extra.get('SsMethod') or r.get('Security')
        if not method:
            raise RuntimeError('Missing Shadowsocks method')
        node.update(type='shadowsocks', method=method, password=r['Password'])
    elif r['ConfigType'] == 5:
        if str(r.get('StreamSecurity') or '').lower() != 'reality':
            raise RuntimeError('Unsupported VLESS stream security: ' + str(r.get('StreamSecurity')))
        uuid = r.get('Id') or r.get('Username') or r.get('Password')
        if not uuid:
            raise RuntimeError('Missing VLESS uuid')
        node.update(type='vless', uuid=uuid, packet_encoding='xudp')
        flow = r.get('Flow') or extra.get('Flow')
        if flow:
            node['flow'] = flow
        tls = {
            'enabled': True,
            'server_name': r.get('Sni') or r['Address'],
            'reality': {
                'enabled': True,
                'public_key': r.get('PublicKey') or '',
                'short_id': r.get('ShortId') or '',
            },
        }
        fingerprint = sing_box_utls_fingerprint(r.get('Fingerprint'))
        if fingerprint:
            tls['utls'] = {'enabled': True, 'fingerprint': fingerprint}
        node['tls'] = tls
        if str(r.get('Network') or '').lower() not in ('', 'tcp'):
            raise RuntimeError('Unsupported VLESS network: ' + str(r.get('Network')))
    else:
        raise RuntimeError('Unsupported node type: ' + str(r['ConfigType']))
    return node, {'tag': tag, 'source': source, 'name': name, 'reason': 'included'}


def collect_nodes(con, blocked_pattern):
    nodes = []
    metadata = []
    blocked = []
    for source in SOURCES:
        for row in con.execute(
            'SELECT p.* FROM ProfileItem p JOIN SubItem s ON p.Subid=s.Id WHERE s.Remarks=? AND s.Enabled=1 ORDER BY p.IndexId',
            (source,),
        ):
            node, info = convert_profile_row(row, source, blocked_pattern)
            metadata.append(info)
            if node is None:
                blocked.append(info)
            else:
                nodes.append(node)
    return nodes, metadata, blocked


def build(settings, db_path=None, with_main_templates=False):
    v2rayn_dir = pathlib.Path(settings['v2rayn_dir'])
    state_dir = pathlib.Path(settings['state_dir'])
    db = pathlib.Path(db_path) if db_path else default_db(settings)
    if not db.exists():
        raise RuntimeError(
            'v2rayN database was not found; provide --db or set v2rayn_dir in settings.json. '
            'Existing state/server-config.json can still be supervised without rebuilding.'
        )
    con = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    policy = json.loads((ROOT / 'feitu-node-policy.json').read_text(encoding='utf-8'))
    blocked_pattern = re.compile(policy['blocked_name_pattern'], re.IGNORECASE)
    nodes, node_metadata, blocked = collect_nodes(con, blocked_pattern)
    if not nodes:
        raise RuntimeError('No relay nodes')
    sidecar = {
        'log': {'level': 'warn', 'timestamp': True},
        'dns': {'servers': [{'type': 'udp', 'tag': 'direct-dns', 'server': '223.5.5.5'}]},
        'inbounds': [
            {'type': 'mixed', 'tag': 'server-in', 'listen': '127.0.0.1', 'listen_port': settings['local_proxy_port']},
            {'type': 'mixed', 'tag': 'feitu-measure-in', 'listen': '127.0.0.1', 'listen_port': settings['feitu_measure_port']},
        ],
        'outbounds': [
            {'type': 'selector', 'tag': 'server-feitu', 'outbounds': ['feitu-quality', 'feitu-auto'] + [n['tag'] for n in nodes],
             'default': 'feitu-quality', 'interrupt_exist_connections': False},
            {'type': 'selector', 'tag': 'feitu-quality', 'outbounds': ['feitu-auto'] + [n['tag'] for n in nodes],
             'default': 'feitu-auto', 'interrupt_exist_connections': False},
            {'type': 'selector', 'tag': 'feitu-measure', 'outbounds': [n['tag'] for n in nodes],
             'default': nodes[0]['tag'], 'interrupt_exist_connections': False},
            {'type': 'urltest', 'tag': 'feitu-auto', 'outbounds': [n['tag'] for n in nodes],
             'url': 'https://www.gstatic.com/generate_204', 'interval': '3m', 'tolerance': 100,
             'idle_timeout': '30m', 'interrupt_exist_connections': False},
            *nodes
        ],
        'route': {'default_domain_resolver': 'direct-dns', 'auto_detect_interface': True,
                  'rules': [{'inbound': ['feitu-measure-in'], 'outbound': 'feitu-measure'}], 'final': 'server-feitu'},
        'experimental': {
            'clash_api': {'external_controller': f"127.0.0.1:{settings['controller_port']}"},
            'cache_file': {'enabled': True, 'path': str(state_dir / 'server-cache.db')}
        }
    }
    write(state_dir / 'server-config.json', sidecar)
    source_counts = {source: len([item for item in node_metadata if item['source'] == source and item['reason'] == 'included']) for source in SOURCES}
    write(state_dir / 'feitu-filter-result.json', {'included_nodes': len(nodes), 'included_by_source': source_counts, 'excluded_nodes': blocked})
    write(state_dir / 'node-labels.json', {item['tag']: item['name'] for item in node_metadata if item['reason'] == 'included'})
    write(state_dir / 'node-sources.json', {
        item['tag']: {'source': item['source'], 'name': item['name'], 'reason': item['reason']}
        for item in node_metadata
    })
    if not with_main_templates:
        con.close()
        print(json.dumps({'relay_nodes': len(nodes), 'included_by_source': source_counts, 'server_config': str(state_dir / 'server-config.json')}))
        return
    template = con.execute('SELECT * FROM FullConfigTemplateItem WHERE Enabled=1 AND Remarks=?', ('sing-box',)).fetchone()
    if not template or not template['AddProxyOnly']:
        raise RuntimeError('Expected enabled sing-box AddProxyOnly template for --with-main-templates')
    tun = json.loads(template['TunConfig'])
    for o in tun['outbounds']:
        if o.get('tag') == 'us-ai':
            o['outbounds'] = list(dict.fromkeys(['ai-auto-fallback', 'ai-quality', 'us-ai-auto-READONLY', 'proxy'] + o['outbounds']))
            o['default'] = 'ai-auto-fallback'
        if o.get('type') in ['selector', 'urltest']:
            o['interrupt_exist_connections'] = False
    ai_members = next(o['outbounds'] for o in tun['outbounds'] if o['tag'] == 'us-ai-auto-READONLY')
    tun['outbounds'] = [o for o in tun['outbounds'] if o['tag'] not in ['ai-auto-fallback', 'ai-quality', 'ai-measure']]
    tun['outbounds'] += [
        {'type': 'selector', 'tag': 'ai-quality', 'outbounds': ['us-ai-auto-READONLY'] + ai_members,
         'default': 'us-ai-auto-READONLY', 'interrupt_exist_connections': False},
        {'type': 'selector', 'tag': 'ai-measure', 'outbounds': ai_members,
         'default': ai_members[0], 'interrupt_exist_connections': False}
    ]
    tun['outbounds'].append({'type': 'selector', 'tag': 'ai-auto-fallback',
                            'outbounds': ['ai-quality', 'proxy'],
                            'default': 'ai-quality', 'interrupt_exist_connections': False})
    probe_tags = ['ai-primary-probe', 'ai-fallback-probe', 'ai-measure-probe']
    tun['inbounds'] = [i for i in tun['inbounds'] if i['tag'] not in probe_tags]
    tun['inbounds'] += [
        {'type': 'mixed', 'tag': 'ai-primary-probe', 'listen': '127.0.0.1', 'listen_port': settings['ai_primary_port']},
        {'type': 'mixed', 'tag': 'ai-fallback-probe', 'listen': '127.0.0.1', 'listen_port': settings['ai_fallback_port']},
        {'type': 'mixed', 'tag': 'ai-measure-probe', 'listen': '127.0.0.1', 'listen_port': settings['ai_measure_port']},
    ]
    # Exclude our independent sing-box process from TUN recapture. Existing
    # template already has a broad core-process bypass; preserve it.
    if not any(r.get('outbound') == 'direct' and 'sing-box.exe' in r.get('process_name', []) for r in tun['route']['rules']):
        tun['route']['rules'].insert(0, {'process_name': ['sing-box.exe'], 'outbound': 'direct'})
    tun['route']['rules'] = [r for r in tun['route']['rules'] if not any(t in r.get('inbound', []) for t in probe_tags)]
    tun['route']['rules'][:0] = [
        {'inbound': ['ai-primary-probe'], 'outbound': 'ai-quality'},
        {'inbound': ['ai-fallback-probe'], 'outbound': 'proxy'},
        {'inbound': ['ai-measure-probe'], 'outbound': 'ai-measure'}
    ]
    normal = copy.deepcopy(tun)
    normal['inbounds'] = [i for i in normal['inbounds'] if i['type'] != 'tun']
    normal_controller = settings['main_controller_ports'][-1]
    normal['experimental']['clash_api']['external_controller'] = f'127.0.0.1:{normal_controller}'
    normal['experimental']['cache_file']['store_fakeip'] = False
    # The normal template has the same AI/domain policy; only TUN capture is absent.
    write(state_dir / 'normal-template.json', normal)
    write(state_dir / 'tun-template.json', tun)
    # v2rayN injects its currently selected node as "proxy" when AddProxyOnly=1.
    current = json.loads((v2rayn_dir / 'binConfigs/config.json').read_text(encoding='utf-8-sig'))
    proxy = [o for o in current['outbounds'] if o['tag'] == 'proxy']
    if len(proxy) != 1:
        raise RuntimeError('Expected exactly one active proxy outbound')
    for name, data in [('normal-runtime', normal), ('tun-runtime', tun)]:
        runtime = copy.deepcopy(data)
        runtime['outbounds'] = [o for o in runtime['outbounds'] if o['tag'] != 'proxy'] + proxy
        write(state_dir / (name + '.json'), runtime)
    con.close()
    print(json.dumps({'relay_nodes': len(nodes), 'included_by_source': source_counts, 'normal_and_tun_staged': True}))


def apply(settings, db_path=None):
    state_dir = pathlib.Path(settings['state_dir'])
    v2rayn_dir = pathlib.Path(settings['v2rayn_dir'])
    db = pathlib.Path(db_path) if db_path else default_db(settings)
    normal = json.loads((state_dir / 'normal-template.json').read_text(encoding='utf-8'))
    tun = json.loads((state_dir / 'tun-template.json').read_text(encoding='utf-8'))
    backup = state_dir / ('backup-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir()
    con = sqlite3.connect(db)
    dest = sqlite3.connect(backup / 'guiNDB.db')
    con.backup(dest)
    dest.close()
    for rel in ['guiConfigs/guiNConfig.json', 'globalTUNfile.json', 'binConfigs/config.json']:
        source = v2rayn_dir / rel
        shutil.copy2(source, backup / source.name)
    with con:
        result = con.execute('UPDATE FullConfigTemplateItem SET Config=?,TunConfig=? WHERE Enabled=1 AND Remarks=?',
                             (json.dumps(normal, ensure_ascii=False), json.dumps(tun, ensure_ascii=False), 'sing-box'))
        if result.rowcount != 1:
            raise RuntimeError('Unexpected template row count')
    con.close()
    # Durable DB is the source; also update the generated TUN file for the current session.
    shutil.copy2(state_dir / 'tun-runtime.json', v2rayn_dir / 'globalTUNfile.json')
    print('Backup: ' + str(backup))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--settings', default=None)
    parser.add_argument('--db', default=None)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--with-main-templates', '--apply-main', action='store_true', dest='with_main_templates')
    args = parser.parse_args()
    loaded_settings = load_settings(args.settings)
    apply(loaded_settings, args.db) if args.apply else build(loaded_settings, args.db, args.with_main_templates)
