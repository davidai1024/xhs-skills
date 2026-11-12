#!/usr/bin/env python3
"""Normalize already-collected XHS evidence; no network or scoring.

Candidates JSON: {"observed_at": ISO, "source": object, "candidates": [
  {"query": str, "name": str, "topic_id": 24hex, "metric_raw": "1.6亿浏览"}
]}. Samples JSON: {"observed_at": ISO, "samples": [
  {"id": 24hex, "title": str, "source_query": str, "source_sort": str,
   "published_ms": int, "updated_ms": int, "tag_list_complete": true,
   "tags": [{"id": 24hex, "name": str}],
   "interactions": {"likes": "12", "favorites": "1.2万"}}
]}. tags must come from the actual note, not generated text.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

IDENTITY = re.compile(r"[0-9a-fA-F]{24}")
COUNT = re.compile(r"(?P<n>\d+(?:\.\d+)?)\s*(?P<u>[万亿kKmM]?)(?P<plus>\+?)")


def parse_count(raw, suffix=None):
    result = {"raw": raw, "value": None, "approximate": None}
    if raw is None or isinstance(raw, bool):
        return result
    value = str(raw).strip()
    if suffix:
        if not value.endswith(suffix):
            return result
        value = value[:-len(suffix)].strip()
    match = COUNT.fullmatch(value)
    if not match:
        return result
    unit = match['u']
    factor = {'': 1, '万': 10000, '亿': 100000000, 'k': 1000, 'm': 1000000}[unit.lower()]
    numeric = Decimal(match['n']) * factor
    result.update(value=int(numeric) if numeric == int(numeric) else float(numeric),
                  approximate=bool(unit or match['plus'] or '.' in match['n']))
    if match['plus']:
        result['lower_bound'] = True
    return result


def identity(raw):
    if not isinstance(raw, str) or not IDENTITY.fullmatch(raw):
        raise ValueError('Missing or invalid 24-character object ID')
    return raw.lower()


def iso_ms(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError('Timestamp must be non-negative epoch milliseconds')
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()


def build(candidates_doc, samples_doc):
    topics = {}
    for row in candidates_doc['candidates']:
        tid = identity(row['topic_id'])
        name = row['name'].removeprefix('#')
        metric = parse_count(row.get('metric_raw'), suffix='浏览')
        if metric['value'] is None:
            raise ValueError(f'Unrecognized view metric for topic {tid}')
        if tid in topics:
            existing = topics[tid]
            if existing['name'] != name or existing['views']['raw'] != metric['raw']:
                raise ValueError(f'Conflicting observations for topic {tid}; retain separate dated snapshots')
            existing['queries'] = list(dict.fromkeys(existing['queries'] + [row.get('query')]))
            continue
        topics[tid] = {'topic_id': tid, 'name': name, 'queries': [row.get('query')],
                       'views': metric, 'metric_window': row.get('metric_window'),
                       'samples': [], 'warnings': []}

    clean_notes = []
    seen_notes = set()
    for note in samples_doc.get('samples', []):
        nid = identity(note['id'])
        if nid in seen_notes:
            raise ValueError(f'Duplicate note {nid}; deduplicate samples before aggregation')
        seen_notes.add(nid)
        tags = [{'id': identity(t['id']), 'name': t.get('name')} for t in note.get('tags', []) if t.get('id')]
        complete = note.get('tag_list_complete') is True and len(tags) == len(note.get('tags', []))
        metrics = note.get('interactions', {})
        clean_notes.append({'id': nid, 'title': note.get('title'),
                            'url': f'https://www.xiaohongshu.com/explore/{nid}',
                            'source_query': note.get('source_query'), 'source_sort': note.get('source_sort'),
                            'published_at': iso_ms(note.get('published_ms')),
                            'updated_at': iso_ms(note.get('updated_ms')), 'tags': tags,
                            'tag_list_complete': complete,
                            'interactions': {k: parse_count(metrics.get(k)) for k in ('likes','favorites','comments','shares')}})

    for topic in topics.values():
        for note in clean_notes:
            matching = any(t['id'] == topic['topic_id'] for t in note['tags'])
            same_name_other_ids = [t['id'] for t in note['tags'] if t.get('name') and
                                  t['name'].casefold() == topic['name'].casefold() and t['id'] != topic['topic_id']]
            if same_name_other_ids:
                topic['warnings'].append({'kind':'similar_name_different_id','note_id':note['id'],'other_topic_ids':same_name_other_ids})
            if matching or note['source_query'] in topic['queries']:
                topic['samples'].append({'note_id': note['id'], 'membership': 'id_verified' if matching else
                                         ('excluded_id_mismatch' if note['tag_list_complete'] else 'unknown_incomplete_tags')})
        topic['verified_sample_count'] = sum(s['membership'] == 'id_verified' for s in topic['samples'])
        topic['evidence_status'] = 'verified_exists_with_samples' if topic['verified_sample_count'] else 'verified_exists_only'

    return {'schema_version': '0.1', 'candidate_observed_at': candidates_doc.get('observed_at'),
            'sample_observed_at': samples_doc.get('observed_at'), 'source': candidates_doc.get('source'),
            'sampling_method': '关键词搜索抽样后按话题ID核验；不是完整话题笔记流',
            'topics': list(topics.values()), 'notes': clean_notes,
            'limitations': ['浏览量统计窗口未知；不是搜索量','样本为定向抽样，不估计总体命中率或话题总量',
                            '没有历史快照，不能计算增速','没有发布实验，不能归因流量效果']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates', required=True, type=Path)
    parser.add_argument('--samples', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = build(json.loads(args.candidates.read_text()), json.loads(args.samples.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'topics':len(result['topics']),'notes':len(result['notes']),
                      'topics_with_verified_samples':sum(bool(t['verified_sample_count']) for t in result['topics'])}))


if __name__ == '__main__':
    main()
