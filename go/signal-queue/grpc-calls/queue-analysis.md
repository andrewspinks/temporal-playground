# Task Queue Analysis

## Namespace: `default`

### `MacBook-Pro-4.local:214a46d6-97bc-4d66-9923-d52ce0acc103`

| | |
|---|---|
| Kind | STICKY *(sticky for: signal-queue)* |
| Poll type | Workflow |
| Got tasks | **yes** (4) |
| Total polls | 6 |
| Identity | `13676@MacBook-Pro-4.local@` |

### `signal-queue`

| | |
|---|---|
| Kind | NORMAL |
| Poll type | Activity + Workflow |
| Got tasks | **yes** (3) |
| Total polls | 7 |
| Identity | `13676@MacBook-Pro-4.local@` |

---

## All Tasks Delivered

- [8] **Workflow task** — `LandingZoneDeploymentWorkflow` attempt 1
  - Queue: `signal-queue (NORMAL)`
  - Workflow: `lz-7`
  - Run: `a8745820-42e9-4878-8698-19de63935b08`
  - Triggered by: Workflow Execution Started, Workflow Execution Signaled *(coalesced into one task)*
  - Delivered to: `13676@MacBook-Pro-4.local@`

- [11] **Workflow task** — `LandingZoneDeploymentWorkflow` attempt 1
  - Queue: `MacBook-Pro-4.local:214a46d6-97bc-4d66-9923-d52ce0acc103 (STICKY)`
  - Workflow: `lz-7`
  - Run: `a8745820-42e9-4878-8698-19de63935b08`
  - Delivered to: `13676@MacBook-Pro-4.local@`

- [14] **Workflow task** — `DeployChangesWorkflow` attempt 1
  - Queue: `MacBook-Pro-4.local:214a46d6-97bc-4d66-9923-d52ce0acc103 (STICKY)`
  - Workflow: `lz-7-vpc-req-1`
  - Run: `019d046c-8394-7cda-b806-9c3342f2de99`
  - Triggered by: Workflow Execution Started
  - Delivered to: `13676@MacBook-Pro-4.local@`

- [17] **Workflow task** — `LandingZoneDeploymentWorkflow` attempt 1
  - Queue: `signal-queue (NORMAL)`
  - Workflow: `lz-7`
  - Run: `a8745820-42e9-4878-8698-19de63935b08`
  - Delivered to: `13676@MacBook-Pro-4.local@`

- [20] **Workflow task** — `DeployChangesWorkflow` attempt 1
  - Queue: `MacBook-Pro-4.local:214a46d6-97bc-4d66-9923-d52ce0acc103 (STICKY)`
  - Workflow: `lz-7-vpc-req-1`
  - Run: `019d046c-8394-7cda-b806-9c3342f2de99`
  - Triggered by: Timer Fired
  - Delivered to: `13676@MacBook-Pro-4.local@`

- [23] **Workflow task** — `LandingZoneDeploymentWorkflow` attempt 1
  - Queue: `MacBook-Pro-4.local:214a46d6-97bc-4d66-9923-d52ce0acc103 (STICKY)`
  - Workflow: `lz-7`
  - Run: `a8745820-42e9-4878-8698-19de63935b08`
  - Triggered by: Child Workflow Execution Completed
  - Delivered to: `13676@MacBook-Pro-4.local@`

- [29] **Workflow task** — `LandingZoneDeploymentWorkflow` attempt 1
  - Queue: `signal-queue (NORMAL)`
  - Workflow: `lz-7`
  - Run: `a8745820-42e9-4878-8698-19de63935b08`
  - Triggered by: Timer Fired, Timer Fired *(coalesced into one task)*
  - Delivered to: `13676@MacBook-Pro-4.local@`
