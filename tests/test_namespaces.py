import pytest

from trama_platform.contracts import ProjectManifest
from trama_platform.namespaces import ScopedStore, namespace_key


def test_scoped_store_keeps_same_id_in_separate_organizations():
    store = ScopedStore[ProjectManifest]()
    first = ProjectManifest(
        project_id="demo", organization_id="org-a", repository="repo-a"
    )
    second = ProjectManifest(
        project_id="demo", organization_id="org-b", repository="repo-b"
    )

    store[namespace_key(first.organization_id, first.project_id)] = first
    store[namespace_key(second.organization_id, second.project_id)] = second

    assert store.find("demo", organization_id="org-a") == first
    assert store.find("demo", organization_id="org-b") == second


def test_scoped_store_rejects_ambiguous_lookup_without_organization():
    store = ScopedStore[ProjectManifest]()
    for organization_id in ("org-a", "org-b"):
        project = ProjectManifest(
            project_id="demo", organization_id=organization_id, repository="repo"
        )
        store[namespace_key(organization_id, project.project_id)] = project

    with pytest.raises(ValueError, match="ambigua"):
        store.find("demo")


def test_scoped_store_updates_from_another_scoped_store():
    source = ScopedStore[ProjectManifest]()
    project = ProjectManifest(
        project_id="demo", organization_id="org-a", repository="repo-a"
    )
    source[namespace_key(project.organization_id, project.project_id)] = project

    target = ScopedStore[ProjectManifest]()
    target.update(source)

    assert target.find("demo", organization_id="org-a") == project
