#!/usr/bin/env python3
"""分析最近两轮 L3 高阶考试数据"""
import json, sqlite3, sys

db_path = sys.argv[1] if len(sys.argv) > 1 else "exam.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT exam_token, data, created_at FROM exam_sessions WHERE exam_id='v3' ORDER BY created_at DESC LIMIT 2"
).fetchall()

for row in rows:
    d = json.loads(row['data'])
    print('='*80)
    print(f"Token: {row['exam_token']}")
    print(f"Agent: {d['agent_name']} ({d['agent_version']})")
    print(f"Model: {d['model_name']}")
    print(f"Time:  {row['created_at']}")
    print(f"Completed: {d['completed']}")
    print()
    
    total = 0
    max_total = 0
    for tid, r in d.get('results', {}).items():
        total += r['score']
        max_total += r['max_score']
        answer = r.get('submitted_answer', '')
        if len(answer) > 150:
            answer = answer[:150] + '...'
        print(f"  {tid}: {r['score']}/{r['max_score']}")
        print(f"    Answer: {answer}")
        fb = r.get('feedback', '')
        print(f"    Feedback: {fb}")
        details = r.get('details', {})
        if details:
            breakdown = details.get('score_breakdown', {})
            if breakdown:
                print(f"    Breakdown: {breakdown}")
            actions = r.get('execution_summary', {}).get('action_types', [])
            print(f"    Actions: {actions}")
        print()
    print(f"  TOTAL: {total}/{max_total}")
    print()
