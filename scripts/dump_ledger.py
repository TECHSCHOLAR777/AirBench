import sqlite3
import json
import sys

def run():
    conn = sqlite3.connect('.airbench-node-ledger.sqlite')
    c = conn.cursor()
    c.execute("SELECT event_json FROM ledger_events WHERE event_type='task.created' AND task_id='d46bb15a-c2aa-59db-9ff3-624e25f8133c'")
    row = c.fetchone()
    if row:
        print(json.dumps(json.loads(row[0]), indent=2))
    else:
        print("Not found")

if __name__ == '__main__':
    run()
