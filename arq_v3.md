                           ┌─────────────────────┐
                           │        USER         │
                           │       AGENTS        │
                           └──────────┬──────────┘
                                      │
                                      ▼
                           ┌─────────────────────┐
                           │       HERMES        │
                           │   Agent / Client    │
                           └──────────┬──────────┘
                                      │ MCP / stdio
                                      ▼
                           ┌─────────────────────┐
                           │    MCP SERVER       │
                           │       Python        │
                           │  No business state  │
                           └──────────┬──────────┘
                                      │ HTTP
                                      ▼
                    ┌─────────────────────────────────┐
                    │          GO GATEWAY             │
                    │                                 │
                    │ High Concurrency                │
                    │ Rate Limiting                   │
                    │ Backpressure                    │
                    │ Connection Pooling              │
                    │ Routing / Timeouts               │
                    │ Streaming / Cancellation        │
                    └───────────────┬─────────────────┘
                                    │
                     ┌──────────────┴──────────────┐
                     │                             │
                     ▼                             ▼
             ┌───────────────┐             ┌───────────────┐
             │     REST      │             │    GraphQL    │
             │   Commands    │             │    Queries    │
             └───────┬───────┘             └───────┬───────┘
                     │                             │
                     └──────────────┬──────────────┘
                                    ▼
                         ┌─────────────────────┐
                         │   TRAMA RUNTIME     │
                         │       Python        │
                         │                     │
                         │ Projects            │
                         │ Tasks               │
                         │ Policies            │
                         │ Memory              │
                         │ Evidence            │
                         │ Knowledge           │
                         │ CCCC Adapter        │
                         └──────────┬──────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                │                   │                   │
                ▼                   ▼                   ▼
       ┌────────────────┐   ┌───────────────┐   ┌───────────────┐
       │   PostgreSQL   │   │     Redis     │   │     NATS      │
       │                │   │               │   │               │
       │ Source of      │   │ Cache / Rate  │   │ Events /      │
       │ Truth          │   │ Limit / Locks │   │ Queue         │
       └────────────────┘   └───────────────┘   └───────┬───────┘
                                                        │
                                      ┌─────────────────┼─────────────────┐
                                      │                 │                 │
                                      ▼                 ▼                 ▼
                                ┌──────────┐      ┌──────────┐      ┌──────────┐
                                │ Worker 1 │      │ Worker 2 │ ...  │ Worker N │
                                │   Go     │      │   Go     │      │ Go/Py    │
                                └────┬─────┘      └────┬─────┘      └────┬─────┘
                                     │                 │                 │
                                     └─────────────────┼─────────────────┘
                                                       ▼
                                                  ┌─────────┐
                                                  │  CCCC   │
                                                  │Coordina │
                                                  │  Agent  │
                                                  └─────────┘