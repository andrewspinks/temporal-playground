# Generate NDE execption on update

> "Nondeterminism error: Update machine does not handle this event: HistoryEvent(id: 16, ActivityTaskScheduled)"

Simulates a workflow change that can generate the error above.

1. Start worker
```
npm start
```

2. Start workflow
```
npm run workflow
```

3. Kill worker
4. Uncomment `updateDone` related code in src/workflow.ts
5. Restart worker
6. Signal workflow

This causes the event history to change from:
```
Activity Task Completed
Activity Task Started
Workflow Execution Update Completed
Activity Task Scheduled
Workflow Task Completed
Workflow Task Started
Workflow Task Scheduled
Activity Task Completed
Activity Task Started
Workflow Execution Update Accepted
...
Workflow Execution Started
```

To:
```
Activity Task Completed
Activity Task Started
Activity Task Scheduled <<<<<<
Workflow Execution Update Completed <<<<< These two events are reversed
Workflow Task Completed
Workflow Task Started
Workflow Task Scheduled
Activity Task Completed
Activity Task Started
Workflow Execution Update Accepted
...
Workflow Execution Started
```
