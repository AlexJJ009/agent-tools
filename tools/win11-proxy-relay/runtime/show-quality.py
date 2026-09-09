"""Render the latest measured quality evidence without reading credentials."""
import datetime
import json
import pathlib
import sys

from settings import default_state_path, load_settings

sys.stdout.reconfigure(encoding='utf-8')

settings = load_settings()
state_root = pathlib.Path(settings['state_dir'])
path = default_state_path('quality-manager-state.json', settings)
if not path.exists():
    raise SystemExit('No quality assessment has completed yet.')
state = json.loads(path.read_text(encoding='utf-8'))
labels_path = state_root / 'node-labels.json'
labels = json.loads(labels_path.read_text(encoding='utf-8')) if labels_path.exists() else {}
lines = ['# 节点质量最近一次测量', '', '生成时间：' + datetime.datetime.now().isoformat(timespec='seconds'), '',
         '失败率来自 HTTP 探测，不是 IP 丢包率。下载速度是 512 KiB 短文件的有效吞吐，不是线路带宽上限。', '']
for name, pool in state.get('pools', {}).items():
    event = pool.get('last_assessment', {})
    lines += ['## ' + name, '', '测量时间：' + str(event.get('started_at', 'unknown')),
              '', '选路记录：`' + str(pool.get('current')) + '`；决定：`' + str(event.get('action')) + '`。', '',
              '| 候选节点 | 延时中位数 ms | 波动 ms | 请求失败率 | 短下载 Mbps | 得分（低为优） |',
              '|---|---:|---:|---:|---:|---:|']
    for entry in event.get('ranked', [])[:10]:
        node = entry['node']
        label = labels.get(node, node).replace('|', '/')
        lines.append('| {} | {:.0f} | {:.0f} | {:.0%} | {:.2f} | {:.1f} |'.format(
            label, entry.get('median_ms', 0), entry.get('jitter_ms', 0),
            entry.get('request_failure_ratio', 0), entry.get('mbps', 0), entry.get('score', 0)))
    lines += ['', '候选总数：' + str(event.get('candidate_count', 0)) + '；未进入表格的节点可能失败、尚未完成下载检测或没有新鲜的检测数据。', '']
output = '\n'.join(lines) + '\n'
(state_root / 'QUALITY-STATUS.md').write_text(output, encoding='utf-8')
print(output)
