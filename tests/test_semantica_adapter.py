from trama_platform.contracts import Evidence, MemoryCandidate
from trama_platform.semantica_adapter import SemanticaContextAdapter


class FakeContext:
    def __init__(self):
        self.stored = []

    def store(self, content, metadata=None, **kwargs):
        self.stored.append((content, metadata, kwargs))
        return "sem-memory-1"

    def retrieve(self, query, max_results=5):
        return [{
            "content": "Trigger writes an audit row",
            "metadata": {
                "candidate_id": "candidate-1", "organization_id": "org-a",
                "project_id": "demo", "agent_id": "specialist-db",
                "task_id": "task-1", "subject": "audit", "source": "semantica",
                "evidence": [{"source": "repo", "locator": "src/a.sql"}],
                "confidence": 0.9,
            },
        }]


def candidate():
    return MemoryCandidate(
        candidate_id="candidate-1", organization_id="org-a", project_id="demo",
        agent_id="specialist-db", task_id="task-1", source="semantica",
        subject="audit", fact="Trigger writes an audit row",
        evidence=[Evidence(source="repo", locator="src/a.sql")], confidence=0.9,
    )


def test_semantica_adapter_uses_native_agent_context_and_preserves_scope():
    context = FakeContext()
    adapter = SemanticaContextAdapter(context)

    assert adapter.put_candidate(candidate()) == "candidate-1"
    assert context.stored[0][0] == "audit: Trigger writes an audit row"
    assert context.stored[0][1]["organization_id"] == "org-a"
    assert context.stored[0][1]["agent_id"] == "specialist-db"
    assert len(adapter.search("org-a", "demo", "audit", agent_id="specialist-db")) == 1
    assert adapter.search("org-a", "other", "audit", agent_id="specialist-db") == []
