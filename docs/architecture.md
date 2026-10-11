# System Architecture & Worker Internals

A detailed architectural breakdown of the Remote Code Execution Engine, showing how traffic flows from the browser to the sandbox worker and back.

---

## 1. End-to-End Component Architecture

```text
 ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
 │   Web Browser   │       │   Mobile App    │       │    AI Agent     │
 └────────┬────────┘       └────────┬────────┘       └────────┬────────┘
          │                         │                         │
          └─────────────────────────┼─────────────────────────┘
                                    │ HTTPS / WSS
                                    ▼
                      ┌───────────────────────────┐
                      │    Cloudflare / WAF       │
                      │  - Rate Limiting (DDOS)   │
                      │  - Max Payload: 64 KB     │
                      └─────────────┬─────────────┘
                                    │
                                    ▼
                      ┌───────────────────────────┐
                      │    API Gateway Cluster    │
                      │  - Auth & Token Billing   │
                      │  - Input Sanitization     │
                      └─────────────┬─────────────┘
                                    │
                                    ▼
                      ┌───────────────────────────┐
                      │  Task Broker (Redis / MQ) │
                      │  - Queue: priority_high   │
                      │  - Queue: contest_default │
                      └─────────────┬─────────────┘
                                    │
              ┌─────────────────────┴─────────────────────┐
              ▼                                           ▼
   ┌───────────────────────┐                   ┌───────────────────────┐
   │ Worker Node 1 (Linux) │                   │ Worker Node 2 (Linux) │
   │                       │                   │                       │
   │  ┌─────────────────┐  │                   │  ┌─────────────────┐  │
   │  │ Warm Pool (x25) │  │                   │  │ Warm Pool (x25) │  │
   │  └────────┬────────┘  │                   │  └────────┬────────┘  │
   │           ▼           │                   │           ▼           │
   │   [Active Sandbox]    │                   │   [Active Sandbox]    │
   │   - Watchdog Timer    │                   │   - Watchdog Timer    │
   │   - Output Grabber    │                   │   - Output Grabber    │
   └───────────────────────┘                   └───────────────────────┘
```

---

## 2. Step-by-Step Execution Journey

When a user clicks "Run Code", here is the exact chronological sequence of events:

1. **Edge Filtering:** The request hits the API Gateway. The gateway verifies that the code size is within limits ($<64 \text{ KB}$) and verifies the user's rate limit quota (e.g. max 10 submissions per minute).
2. **Task Enqueueing:** The gateway creates an execution ticket:
   ```json
   { "ticket_id": "job_9812", "lang": "python", "code": "...", "timeout": 2000 }
   ```
   and pushes it to an in-memory Redis Stream.
3. **Worker Pickup:** An available Worker Node pulls the job.
4. **Acquiring a Warm Box:** The Worker pops an idle, pre-warmed sandbox from its local pool (takes $<2\text{ms}$).
5. **Watchdog Initialization:** The worker arms a local hardware/OS watchdog timer set to `timeout + 100ms`.
6. **Execution:** Code is injected into the sandbox via standard input (`stdin`) and execution begins.
7. **Output Harvesting:** The worker captures `stdout` (up to 1MB to prevent terminal spam), `stderr` and the exit code.
8. **Watchdog Disarmed:** If the process completes normally, the timer is cancelled. If the process hangs, the watchdog sends an uncatchable `SIGKILL` (-9).
9. **Instant Sanitation:** The executed sandbox is terminated. Its memory and temporary filesystem are discarded immediately.
10. **Background Refill:** The worker asynchronously triggers a replacement sandbox initialization to maintain the warm pool count.
11. **Return:** Result JSON is returned to the user via HTTP response or WebSocket message.
