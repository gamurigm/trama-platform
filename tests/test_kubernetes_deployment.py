import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class LocalKubernetesDeploymentTests(unittest.TestCase):
    def test_local_values_match_the_current_single_node_chart(self) -> None:
        values_path = ROOT / "deploy/helm/trama-gateway/values-local.yaml"
        self.assertTrue(values_path.is_file(), "local Helm values are missing")
        values = yaml.safe_load(values_path.read_text(encoding="utf-8"))

        self.assertEqual(values["fullnameOverride"], "trama-gateway")
        for component, repository in (
            ("gateway", "trama-gateway"),
            ("controlPlane", "trama-python"),
            ("outbox", "trama-outbox"),
            ("pythonWorker", "trama-python"),
        ):
            self.assertEqual(values[component]["replicaCount"], 1)
            self.assertEqual(values[component]["image"]["repository"], repository)
            self.assertEqual(values[component]["image"]["tag"], "local")
            self.assertEqual(values[component]["image"]["pullPolicy"], "Never")

        self.assertEqual(values["outbox"]["natsStreamReplicas"], 1)
        self.assertFalse(values["autoscaling"]["enabled"])
        self.assertFalse(values["podDisruptionBudget"]["enabled"])

    def test_stateful_dependency_images_use_the_available_legacy_catalog(self) -> None:
        for component in ("postgresql", "redis"):
            values_path = ROOT / f"deploy/ansible/values/{component}.yml"
            values = yaml.safe_load(values_path.read_text(encoding="utf-8"))
            self.assertEqual(
                values["image"]["repository"], f"bitnamilegacy/{component}"
            )
            if component == "redis":
                self.assertTrue(values["global"]["security"]["allowInsecureImages"])

    def test_ansible_validates_vault_before_creating_cluster_resources(self) -> None:
        tasks = yaml.safe_load(
            (ROOT / "deploy/ansible/tasks/preflight.yml").read_text(encoding="utf-8")
        )
        names = [task["name"] for task in tasks]

        load_name = "Load the encrypted local Vault file"
        validate_name = "Validate required deployment credentials"
        namespace_name = "Ensure the application namespace exists"
        self.assertIn(load_name, names)
        self.assertIn(validate_name, names)
        self.assertLess(names.index(load_name), names.index(validate_name))
        self.assertLess(names.index(validate_name), names.index(namespace_name))

    def test_ansible_targets_the_current_control_plane_and_persistent_services(self) -> None:
        tasks = yaml.safe_load(
            (ROOT / "deploy/ansible/tasks/application.yml").read_text(encoding="utf-8")
        )
        restart = next(
            task
            for task in tasks
            if task["name"] == "Restart TRAMA workloads after loading local images"
        )
        rollout = next(
            task for task in tasks if task["name"] == "Wait for TRAMA workloads to become ready"
        )
        self.assertLess(tasks.index(restart), tasks.index(rollout))
        self.assertEqual(
            restart["loop"],
            [
                "trama-gateway",
                "trama-gateway-outbox",
                "trama-gateway-control-plane",
                "trama-gateway-python-worker",
            ],
        )
        self.assertEqual(
            restart["ansible.builtin.command"]["argv"],
            [
                "kubectl",
                "rollout",
                "restart",
                "deployment/{{ item }}",
                "--namespace",
                "{{ kube_namespace }}",
            ],
        )
        self.assertEqual(
            rollout["loop"],
            [
                "trama-gateway",
                "trama-gateway-outbox",
                "trama-gateway-control-plane",
                "trama-gateway-python-worker",
            ],
        )

        pvc_check = next(
            task for task in tasks if task["name"] == "Confirm the persistent storage claims exist"
        )
        conditions = pvc_check["ansible.builtin.assert"]["that"]
        self.assertTrue(any("trama-postgresql" in condition for condition in conditions))
        self.assertTrue(any("trama-nats" in condition for condition in conditions))
        self.assertFalse(any("python-state" in condition for condition in conditions))

    def test_gateway_secret_provides_control_plane_internal_token(self) -> None:
        secret_template = (
            ROOT / "deploy/ansible/templates/gateway-secret.json.j2"
        ).read_text(encoding="utf-8")
        self.assertIn('"control-plane-internal-token"', secret_template)
        self.assertIn("local_vault.control_plane_internal_token", secret_template)


if __name__ == "__main__":
    unittest.main()
