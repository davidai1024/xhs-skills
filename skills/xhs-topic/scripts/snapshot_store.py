#!/usr/bin/env python3
"""Local public-note snapshot store. No network or scheduled/background tasks.
Ingest accepts the notes[] schema used by build_evidence.py. Exports preserve
actual observations by note ID and capture time. Growth needs exact counts,
matching measurement/source, and minimum elapsed time, and is not virality.
"""
import argparse,json,sqlite3,re
from datetime import datetime,timezone
from pathlib import Path
from build_evidence import metric,instant

FIELDS=('note_id','title','author','author_id','date_raw','likes_raw','collects_raw','comments_raw','shares_raw','collected_at','created_at','created_at_verified','time_source','updated_at','query','sort','collection','exclusion_reason')

def connect(path):
    conn=sqlite3.connect(path)
    conn.execute('CREATE TABLE IF NOT EXISTS snapshots(note_id TEXT NOT NULL,collected_at TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(note_id,collected_at))')
    return conn

def ingest(conn,data):
    inserted=duplicate=skipped=0
    for row in data.get('notes',[]):
        if not re.fullmatch('[a-f0-9]{24}',str(row.get('note_id',''))) or not row.get('title'):
            skipped+=1;continue
        try: stamp=instant(row.get('collected_at')).isoformat()
        except ValueError: skipped+=1;continue
        item={k:row[k] for k in FIELDS if k in row};item['collected_at']=stamp
        item['source']='https://www.xiaohongshu.com/explore/'+item['note_id']
        item['likes']=metric(row.get('likes_raw'))
        old=conn.execute('SELECT payload FROM snapshots WHERE note_id=? AND collected_at=?',(item['note_id'],stamp)).fetchone()
        if old:
            # Re-querying is not a new time snapshot; merge complementary metadata.
            existing=json.loads(old[0])
            for key,value in item.items():
                if value is not None and value!='':
                    if key in ('created_at','created_at_verified','time_source') and existing.get('created_at_verified') is True and item.get('created_at_verified') is not True:continue
                    existing[key]=value
            item=existing;duplicate+=1
        else: inserted+=1
        conn.execute('INSERT OR REPLACE INTO snapshots VALUES(?,?,?)',(item['note_id'],stamp,json.dumps(item,ensure_ascii=False)))
    conn.commit()
    return {'inserted':inserted,'same_time_merged':duplicate,'skipped':skipped}

def export(conn):
    rows=[json.loads(r[0]) for r in conn.execute('SELECT payload FROM snapshots ORDER BY collected_at,note_id')]
    return {'run_at':datetime.now(timezone.utc).isoformat(),'window_hours':72,'notes':rows,'unique_notes':len({r['note_id'] for r in rows}),'snapshots':len(rows)}

def growth(conn,min_minutes=30):
    data=export(conn);grouped={}
    for r in data['notes']:grouped.setdefault(r['note_id'],[]).append(r)
    result=[]
    for nid,rows in grouped.items():
        rows.sort(key=lambda r:instant(r['collected_at']))
        if len(rows)<2:continue
        first,last=rows[0],rows[-1]
        minutes=(instant(last['collected_at'])-instant(first['collected_at'])).total_seconds()/60
        a,b=first['likes'],last['likes'];reason=None
        if minutes<min_minutes:reason='采集间隔不足'
        elif first.get('collection')!=last.get('collection'):reason='不同采集口径需先人工对齐'
        elif a['value'] is None or b['value'] is None:reason='点赞缺失'
        elif a['approximate'] or b['approximate']:reason='存在平台约数，不能报告精确增量'
        elif b['value']<a['value']:reason='计数下降，需核对口径或异常'
        result.append({'note_id':nid,'from':first['collected_at'],'to':last['collected_at'],'eligible':reason is None,'reason':reason,
          'likes_delta':None if reason else int(b['value']-a['value']),
          'likes_per_hour':None if reason else round((b['value']-a['value'])/(minutes/60),2),
          'meaning':'时段净增不是加速度；需作者或同龄样本基线才可评异常起量，不能保证会爆'})
    return {'comparisons':result,'single_snapshot_notes':sum(len(r)==1 for r in grouped.values())}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['ingest','export','growth']);p.add_argument('--db',required=True);p.add_argument('--input');p.add_argument('--output');p.add_argument('--min-minutes',type=float,default=30);a=p.parse_args()
    if a.min_minutes<=0:p.error('--min-minutes must be positive')
    if a.action=='ingest' and not a.input:p.error('ingest requires --input')
    conn=connect(a.db)
    try:r=ingest(conn,json.loads(Path(a.input).read_text())) if a.action=='ingest' else export(conn) if a.action=='export' else growth(conn,a.min_minutes)
    finally:conn.close()
    txt=json.dumps(r,ensure_ascii=False,indent=2)
    if a.output:Path(a.output).write_text(txt)
    print(txt if a.action=='ingest' or not a.output else '已保存 '+a.output)
if __name__=='__main__':main()
