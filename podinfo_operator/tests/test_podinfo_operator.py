import os
import sys
import unittest
import datetime
from unittest.mock import MagicMock, patch
from kubernetes import client
from utils import PrettyPrintTextTestRunner

TOP_LEVEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(TOP_LEVEL_DIR)

from podinfo_operator import (
    create_deployment_and_service,
    teardown_deployment,
    teardown_service,
    get_deployment,
    create_podinfo_deployment_and_service,
    create_redis_deployment_and_service,
)
from kopf.testing import KopfRunner


class TestPodInfoOperator(unittest.TestCase):
    def setUp(self):
        self.namespace = "test-namespace"
        self.operator_file = os.path.join(TOP_LEVEL_DIR, "podinfo_operator.py")

    @patch("kopf.adopt")
    @patch("kubernetes.client.AppsV1Api.create_namespaced_deployment")
    @patch("kubernetes.client.CoreV1Api.create_namespaced_service")
    def test_create_deployment_and_service(self, mock_create_namespaced_service, mock_create_namespaced_deployment, mock_kopf_adopt):
        # Set up mock deployment and service creation
        mock_create_namespaced_deployment.return_value = client.V1Deployment(
            metadata=client.V1ObjectMeta(uid="my-uid", creation_timestamp=datetime.datetime(2023, 7, 29, 1, 8, 24, 508213))
        )
        mock_create_namespaced_service.return_value = client.V1Service()

        mock_kopf_adopt.__enter__ = MagicMock()
        mock_kopf_adopt.__exit__ = MagicMock()

        # Call the create_deployment_and_service function using KopfRunner
        with KopfRunner(['run', '--namespace', self.namespace, self.operator_file]) as runner:
            spec = {
                "image": {"repository": "myrepo", "tag": "latest"},
                "replicaCount": 3,
                "resources": {"cpuRequest": "100m", "memoryLimit": "512Mi"},
            }
            status = create_deployment_and_service(
                name="my-deployment",
                namespace=self.namespace,
                image_repo=spec["image"]["repository"],
                image_tag=spec["image"]["tag"],
                replicas=spec["replicaCount"],
                resources=client.V1ResourceRequirements(
                    requests={"cpu": spec["resources"]["cpuRequest"]},
                    limits={"memory": spec["resources"]["memoryLimit"]},
                ),
                expose_port=9898,
                env_vars=None,
            )

        # Assertions
        expected_status = {
            "created_on": "Sat Jul 29 01:08:24 2023",
            "uid": "my-uid",
        }
        self.assertEqual(status, expected_status)

    @patch("kubernetes.client.CoreV1Api.delete_namespaced_service")
    def test_teardown_service(self, mock_delete_namespaced_service):
        # Set up mock service deletion
        mock_delete_namespaced_service.return_value = client.V1Status()

        # Call the teardown_service function using KopfRunner
        with KopfRunner(['run', '--namespace', self.namespace, self.operator_file]) as runner:
            status = teardown_service("my-service", self.namespace)

        # Assertions (you may add more assertions depending on the logic)
        self.assertIsInstance(status, client.V1Status)

    @patch("kubernetes.client.AppsV1Api.delete_namespaced_deployment")
    def test_teardown_deployment(self, mock_delete_namespaced_deployment):
        # Set up mock deployment deletion
        mock_delete_namespaced_deployment.return_value = client.V1Status()

        # Call the teardown_deployment function using KopfRunner
        with KopfRunner(['run', '--namespace', self.namespace, self.operator_file]) as runner:
            status = teardown_deployment("my-deployment", self.namespace)

        # Assertions (you may add more assertions depending on the logic)
        self.assertIsInstance(status, client.V1Status)

    @patch("kubernetes.client.AppsV1Api.list_namespaced_deployment")
    def test_get_deployment(self, mock_list_namespaced_deployment):
        # Create a list of mocked deployments
        mocked_deployments = [
            client.V1Deployment(metadata=client.V1ObjectMeta(name="my-deployment")),
            client.V1Deployment(metadata=client.V1ObjectMeta(name="other-deployment")),
        ]

        # Set the return value of the mocked function
        mock_list_namespaced_deployment.return_value.items = mocked_deployments

        # Call the get_deployment function using KopfRunner
        with KopfRunner(['run', '--namespace', self.namespace, self.operator_file]) as runner:
            deployment = get_deployment("my-deployment", self.namespace)

        # Assert that the deployment is an instance of client.V1Deployment and has the correct name
        self.assertIsInstance(deployment, client.V1Deployment)
        self.assertEqual(deployment.metadata.name, "my-deployment")

    @patch("kubernetes.client.AppsV1Api.list_namespaced_deployment")
    def test_get_deployment_not_found(self, mock_list_namespaced_deployment):
        # Create an empty list of deployments to simulate no deployments found
        mocked_deployments = []

        # Set the return value of the mocked function
        mock_list_namespaced_deployment.return_value.items = mocked_deployments

        # Call the get_deployment function using KopfRunner when no deployments are found
        with KopfRunner(['run', '--namespace', self.namespace, self.operator_file]) as runner:
            deployment = get_deployment("non-existent-deployment", self.namespace)

        # Assert that the deployment is None since it was not found
        self.assertIsNone(deployment)

    @patch("kopf.adopt")
    @patch("kubernetes.client.AppsV1Api.create_namespaced_deployment")
    @patch("kubernetes.client.CoreV1Api.create_namespaced_service")
    @patch("kubeutils.create_deployment_object")
    @patch("kubeutils.create_service_object")
    def test_create_podinfo_deployment_and_service(self, mock_create_namespaced_deployment, mock_create_namespaced_service, mock_create_service_object, mock_create_deployment_object, mock_kopf_adopt):
        # Set up mock deployment and service creation
        mock_create_namespaced_deployment.return_value = client.V1Deployment(
            metadata=client.V1ObjectMeta(uid="my-uid", creation_timestamp=datetime.datetime(2023, 7, 29, 1, 8, 24, 508213))
        )
        mock_create_namespaced_service.return_value = client.V1Service()
        mock_create_deployment_object.return_value = client.V1Deployment(
            metadata=client.V1ObjectMeta(uid="my-uid", creation_timestamp=datetime.datetime(2023, 7, 29, 1, 8, 24, 508213))
        )
        mock_create_service_object.return_value = client.V1Service()

        mock_kopf_adopt.__enter__ = MagicMock()
        mock_kopf_adopt.__exit__ = MagicMock()

        # Call the create_podinfo_deployment_and_service function using KopfRunner
        with KopfRunner(['run', '--namespace', self.namespace, self.operator_file]) as runner:
            spec = {
                "image": {"repository": "myrepo", "tag": "latest"},
                "replicaCount": 3,
                "resources": {"cpuRequest": "100m", "memoryLimit": "512Mi"},
                "ui": {"UI_VERSION": "v2"},
            }
            status = create_podinfo_deployment_and_service(
                namespace=self.namespace, spec=spec
            )

        # Assertions
        expected_status = {
            "created_on": "Sat Jul 29 01:08:24 2023",
            "uid": "my-uid",
        }
        self.assertEqual(status, expected_status)

    @patch("kopf.adopt")
    @patch("kubernetes.client.AppsV1Api.create_namespaced_deployment")
    @patch("kubernetes.client.CoreV1Api.create_namespaced_service")
    @patch("kubeutils.create_deployment_object")
    @patch("kubeutils.create_service_object")
    def test_create_redis_deployment_and_service(self, mock_create_namespaced_deployment, mock_create_namespaced_service, mock_create_service_object, mock_create_deployment_object, mock_kopf_adopt):
        # Set up mock deployment and service creation
        mock_create_namespaced_deployment.return_value = client.V1Deployment(
            metadata=client.V1ObjectMeta(uid="my-uid", creation_timestamp=datetime.datetime(2023, 7, 29, 1, 8, 24, 508213))
        )
        mock_create_namespaced_service.return_value = client.V1Service()
        mock_create_deployment_object.return_value = client.V1Deployment(
            metadata=client.V1ObjectMeta(uid="my-uid", creation_timestamp=datetime.datetime(2023, 7, 29, 1, 8, 24, 508213))
        )
        mock_create_service_object.return_value = client.V1Service()
        
        mock_kopf_adopt.__enter__ = MagicMock()
        mock_kopf_adopt.__exit__ = MagicMock()

        # Call the create_redis_deployment_and_service function using KopfRunner
        with KopfRunner(['run', '--namespace', self.namespace, self.operator_file]) as runner:
            spec = {
                "image": {"repository": "redis", "tag": "7.0.12"},
                "replicaCount": 1,
                "resources": {"cpuRequest": "100m", "memoryLimit": "32Mi"},
            }
            status = create_redis_deployment_and_service(
                namespace=self.namespace, spec=spec
            )

        # Assertions
        expected_status = {
            "created_on": "Sat Jul 29 01:08:24 2023",
            "uid": "my-uid",
        }
        self.assertEqual(status, expected_status)

if __name__ == "__main__":  # pragma: no cover
    unittest.main(testRunner=PrettyPrintTextTestRunner(verbosity=0))
