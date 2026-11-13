#!/usr/bin/env python3
"""Normalize collected public note evidence; does NOT collect data or rank topics.
Input JSON: run_at (timezone-aware ISO), window_hours, notes[]. Each observation:
note_id,title,author,source,collected_at,likes_raw,created_at (ISO or null),
created_at_verified (bool),time_source. query,sort,date_raw,updated_at optional.
Unknown or merely edited times never pass the publication gate. Retains snapshots
by note ID, discards non-note cards, and preserves raw abbreviated counts.
"""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import re


def instant(value):
    if not isinstance(value, str):
        raise ValueError('missing timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamp must include timezone')
    return parsed


def metric(raw):
    value = str(raw or '').strip().replace(',', '')
    match = re.fullmatch(r'(\d+(?:\.\d+)?)(万|亿|[wWkK])?(\+)?', value)
    if not match:
        return {'raw': raw, 'value': None, 'approximate': None}
    number, unit, plus = match.groups()
    return {'raw': raw, 'value': float(number) * {None: 1, '万': 10000, '亿': 100000000, 'w': 10000, 'k': 1000}.get(unit.lower() if unit else None, 1), 'approximate': bool(unit or plus)}


def build(data):
    end = instant(data['run_at'])
    start = end - timedelta(hours=data.get('window_hours', 72))
    grouped, discarded = {}, 0
    for row in data['notes']:
        nid = str(row.get('note_id', ''))
        if not re.fullmatch(r'[0-9a-f]{24}', nid) or not row.get('title'):
            discarded += 1
            continue
        # Whitelist avoids retaining session tokens or arbitrary payloads.
        keys = ('note_id', 'title', 'author', 'author_id', 'date_raw', 'likes_raw', 'collects_raw', 'comments_raw', 'shares_raw', 'collected_at', 'created_at', 'created_at_verified', 'time_source', 'updated_at', 'query', 'sort', 'detail_date_raw', 'detail_likes_raw', 'detail_collected_at', 'exclusion_reason', 'content_summary', 'collection')
        item = {k: row[k] for k in keys if k in row}
        item['source'] = f'https://www.xiaohongshu.com/explore/{nid}'
        item['likes'] = metric(row.get('likes_raw'))
        reasons = []
        collected = None
        try:
            collected = instant(row.get('collected_at'))
            if collected > end or collected < start:
                reasons.append('采集时间不在本轮窗口内')
        except ValueError:
            reasons.append('采集时间无效')
        try:
            created = instant(row.get('created_at'))
            if row.get('created_at_verified') is not True or not row.get('time_source'):
                reasons.append('缺原始发布时间核验来源')
            if not start <= created <= end:
                reasons.append('原始发布时间不在近72小时窗口内')
            if collected is not None and created > collected:
                reasons.append('发布时间晚于采集时间')
        except ValueError:
            reasons.append('原始发布时间未核实；搜索或编辑日期不能替代')
        if item['likes']['value'] is None:
            reasons.append('点赞数不可见或不可解析')
        if not row.get('author'):
            reasons.append('作者缺失')
        item['publication_evidence_gate'] = not reasons
        item['gate_reasons'] = reasons
        grouped.setdefault(nid, []).append(item)
    notes = []
    for nid, observations in grouped.items():
        eligible = [o for o in observations if o['publication_evidence_gate']]
        notes.append({'note_id': nid, 'observations': observations, 'publication_evidence_gate': bool(eligible), 'growth_verified': False, 'growth_note': '本工具不因多次检索或高累计点赞自动确认起量；需不同采集时点的可比快照、误差检查及基线分析。'})
    return {'run_at': end.isoformat(), 'window_start': start.isoformat(), 'window_end': end.isoformat(), 'unique_notes': len(notes), 'discarded_non_note_observations': discarded, 'eligible_recent_note_count': sum(n['publication_evidence_gate'] for n in notes), 'meaning': '入门槛仅说明近72小时发布与当前点赞证据完整，不等于高赞、多人跟进、突然爆发或推荐选题。', 'notes': notes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = build(json.loads(Path(args.input).read_text()))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: result[k] for k in ('unique_notes', 'eligible_recent_note_count', 'discarded_non_note_observations')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
