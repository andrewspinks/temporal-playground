#!/usr/bin/env python3
"""Read worker trace logs and report the thing we are hunting: a Workflow Task delivered as
more than one activation.

    python3 analyze.py worker1.log worker2.log

historyLength is set once per Workflow Task, so two live activations reporting the same
(workflowId, historyLength) are two activations of ONE Workflow Task.
"""
import re, sys, collections

acts = []
for f in sys.argv[1:]:
    cur = None
    for line in open(f, errors='replace'):
        m = re.search(r'activate wf=(\S+) hl=(\d+) replaying=(\w+) jobs=\[(.*)\]', line)
        if m:
            cur = (m.group(1), int(m.group(2)), m.group(3) == 'true', m.group(4))
            continue
        if 'commands=' in line and cur:
            acts.append((*cur, line.split('commands=')[1].strip()))
            cur = None

live = [a for a in acts if not a[2]]
print(f'activations: {len(acts)} total, {len(live)} live (replaying=false)')

groups = collections.defaultdict(list)
for wf, hl, _, jobs, cmds in live:
    groups[(wf, hl)].append((jobs, cmds))
multi = {k: v for k, v in groups.items() if len(v) > 1}

print(f'Workflow Tasks delivered as >1 live activation: {len(multi)}')
for (wf, hl), v in multi.items():
    print(f'  wf={wf} historyLength={hl}')
    for jobs, cmds in v:
        print(f'      jobs=[{jobs}] -> {cmds}')

print('\n=== command patterns for multi-signal tasks ===')
c = collections.Counter((jobs, cmds) for _, _, _, jobs, cmds in live if 'signalWorkflow x' in jobs)
for (j, cm), n in c.most_common(10):
    print(f'  x{n:<3} [{j}] -> {cm}')
