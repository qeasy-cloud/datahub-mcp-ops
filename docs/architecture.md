# Architecture

How this skill is put together, and how it maps onto the platform it operates.

---

## 1. System context

```mermaid
flowchart LR
    subgraph Agent runtime
        A[AI agent<br/>SKILL.md + references]
        C[dh.py CLI]
    end

    subgraph Datahub tenant
        M[MCP endpoint<br/>/api/mcp]
        P[(Platform data<br/>strategies · connectors · assets)]
        Q[(Queues<br/>SJOB / TJOB)]
        D[(Data records<br/>ADATA)]
        L[(Logs & exceptions)]
    end

    subgraph External systems
        S[Source system<br/>query API]
        E[Target system<br/>write API]
    end

    K[Public knowledge MCP<br/>mcp.qeasy.cloud]

    A -->|tools/call| M
    C -->|JSON-RPC over HTTP| M
    M --> P & Q & D & L
    Q -->|invoke| S
    Q -->|invoke| E
    A -.->|design-time facts| K
```

Two different MCP servers, deliberately separated:

| | Datahub MCP | Knowledge MCP |
|---|---|---|
| Purpose | read/write **your** tenant | read **documentation** |
| State | stateful (`Mcp-Session-Id`) | stateless (each request carries a key) |
| Auth | `sh-…` tenant key | `qk_live_…` agent-registrable key |
| Tools | 58 | 3 |

The skill uses the first to observe and act, the second only for facts a distilled document cannot hold
(object field lists, customer cases, cross-platform semantics).

---

## 2. Document layers (progressive disclosure)

```mermaid
flowchart TD
    S[SKILL.md<br/>~9.7k chars · 250 lines] -->|§9 index| R[references/]
    S -->|task recipes| P[playbooks/]
    S -->|copy-paste| X[examples/]
    R --> R1[01 platform-model]
    R --> R2[02 tool-catalog]
    R --> R3[03 debug-loop]
    R --> R4[04 write-recipe]
    R --> R5[05 diagnostics]
    R --> R6[06 knowledge-mcp]
    R --> R7[07 security-and-limits]
    R --> R8[08 anti-patterns]
    G[tools/manifest.json<br/>generated from server] -.->|CI consistency| R2
```

Rules that keep this cheap:

1. **One topic per file.** Mechanism → `references/`, procedure → `playbooks/`, instance → `examples/`.
2. **The entry point is bounded.** Anything that grows past ~300 lines moves into a reference.
3. **Never duplicate.** A fact lives in exactly one file; the rest link to it.
4. **Manifest is generated, not written.** `scripts/dh.py manifest` reads the live server; CI fails when
   documentation mentions a tool the server does not expose.

---

## 3. Runtime chain on the platform

```mermaid
sequenceDiagram
    participant Cron
    participant D as dispatcher
    participant A as Adapter
    participant Q as Queue (SJOB/TJOB)
    participant W as Worker
    participant X as External system

    Cron->>D: trigger strategy (source/target)
    D->>A: instantiate adapter (direction)
    A->>A: evaluate {{…}}, parsers, operation rows
    A->>Q: enqueue job with params
    W->>Q: claim job
    W->>X: connect + invoke
    X-->>W: response
    W->>W: validate otherResponse, persist data / write back
    W->>Q: finished or error (retry with backoff)
```

Where the skill intervenes when **no daemon exists**: instead of waiting for `W`, the agent calls
`strategy.queue.job.run`, which invokes the same adapter path synchronously and returns the outcome.

---

## 4. Tool layers and risk gates

```mermaid
flowchart LR
    subgraph read [🟢 read]
        r1[strategy.list/get/dbInfo]
        r2[queue.job.get · log.search]
        r3[asset.* · audit.search]
    end
    subgraph write [🟡 write]
        w1[source.update · target.update]
        w2[create · copy · data.import]
    end
    subgraph ops [🟠 ops]
        o1[dispatchSource/Target]
        o2[queue.job.run/update]
        o3[start · stop · online · offline]
        o4[data.setStatus · dbResetStatus]
    end
    subgraph destructive [🔴 destructive]
        d1[data.clean · queue.clean · data.cleanAll]
        d2[script.delete]
    end

    read --> write --> ops --> destructive
```

Gates applied before execution:

```mermaid
flowchart TD
    call[Tool call] --> risk{risk level?}
    risk -->|read| run[execute]
    risk -->|write/ops/destructive| preview[compute precheck<br/>blast radius]
    preview --> dry{dryRun?}
    dry -->|yes| stop[return precheck only]
    dry -->|no| trust{trust level<br/>+ impact}
    trust -->|full AND impact ≤ threshold| run
    trust -->|otherwise| token[return confirmationToken]
    token -->|replay with token| verify{valid & unused?}
    verify -->|no| reject[confirmation_token_invalid]
    verify -->|yes| run
```

Independent hard gate: `strategy.queue.job.run {direction:"target"}` requires `confirmWrite=true`.
Trust level does **not** bypass it — an external ERP write cannot be rolled back by the platform.

---

## 5. Debug loop as a state machine

```mermaid
stateDiagram-v2
    [*] --> Queued: dispatchSource
    Queued --> Running: queue.job.run
    Running --> Finished: ok && has_data
    Running --> Empty: ok && !has_data
    Running --> Error: exception
    Empty --> Queued: job.update (widen filter) + run(force)
    Error --> Queued: fix params/data + run(force)
    Finished --> [*]
    Error --> [*]: give up (documented)
```

The skill's judgement rules map one-to-one onto these transitions:

| State | Field to read | Action |
|---|---|---|
| Queued | `status=5` | `queue.job.run` |
| Finished | `ok=true, has_data=true` | proceed to target side |
| Empty | `ok=true, has_data=false` | `log.search(level=debug)` → widen filter → `run(force=true)` |
| Error | `ok=false` + `exceptions` | `log.search(level=error,fatal)` + `exception.search` |
| Re-run needed | `skipped=already_finished` | `force=true` |

---

## 6. Why the CLI exists next to MCP

| Concern | MCP client | `dh.py` |
|---|---|---|
| Tool discovery | native | `tools` |
| Session / SSE handling | client's job | built-in |
| 429 backoff | client-dependent | implemented |
| Reproducible evidence in CI | hard | `--json` output |
| Manifest regeneration | manual | `manifest` |
| Shell quoting on Windows | n/a | `--param` |

Neither replaces the other: MCP gives native tool use inside an agent turn; the CLI gives determinism for
humans, scripts and CI.
