#!/usr/bin/env bash

export TQ="park2";
export WID="park2-wf-3"
export FIX="${FIX:-0}";
export TOTAL="${TOTAL:-200}";
export GATE_HOLD_S="${GATE_HOLD_S:-2.0}"

mise exec -- bundle exec ruby worker.rb &
sleep 1

PID=$!

temporal workflow start --type Fanout --input "$TOTAL" --task-queue "$TQ" \
  --workflow-id "$WID"

show(){ temporal workflow show --workflow-id "$WID" --output json 2>/dev/null; }

echo "== [3] recorded per-timer-group ScheduleActivity split =="
show > /tmp/park2_history.json
python3 -c "
import json
evs=json.load(open('/tmp/park2_history.json'))['events']
groups=[]; cur=None
for e in evs:
    t=e['eventType']
    if t=='EVENT_TYPE_TIMER_STARTED':
        if cur is not None: groups.append(cur)
        cur=0
    elif t=='EVENT_TYPE_ACTIVITY_TASK_SCHEDULED': cur=(cur or 0)+1
if cur is not None: groups.append(cur)
print('   split:', groups)
print('   PARTIAL COMMIT (a group != 100) =>', any(g!=100 for g in groups[:-1]) if len(groups)>1 else (groups and groups[0]!=200))
"

kill $PID
