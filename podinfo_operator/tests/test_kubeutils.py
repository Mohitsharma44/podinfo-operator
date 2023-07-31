import unittest
import os
import sys
from unittest.mock import MagicMock, patch
from kubernetes import client
from kubernetes.client import ApiException
from utils import PrettyPrintTextTestRunner

TOP_LEVEL_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
    )
)
sys.path.append(TOP_LEVEL_DIR)

from kubeutils import (
    create_deployment_object,
    teardown_deployment,
    teardown_service,
    get_deployment,
    create_service_object,
    create_or_update_deployment,
    create_or_update_service,
)


class TestKubeUtils(unittest.TestCase):
    def setUp(self):
        self.namespace = "test-namespace"

    @patch("kubernetes.client.AppsV1Api.create_namespaced_deployment")
    def test_create_deployment_object(self, mock_create_namespaced_deployment):
        # Set up mock deployment creation
        mock_create_namespaced_deployment.return_value = client.V1Deployment(
            metadata=client.V1ObjectMeta(uid="my-uid")
        )

        # Call the create_deployment_object function
        deployment = create_deployment_object(
            name="my-deployment",
            namespace=self.namespace,
            image_registry="myregistry",
            image_tag="latest",
            replicas=3,
            resources=client.V1ResourceRequirements(
                requests={"cpu": "100m", "memory": "512Mi"},
                limits={"cpu": "200m", "memory": "1Gi"},
            ),
            expose_ports=[client.V1ContainerPort(container_port=80)],
            env_vars=[client.V1EnvVar(name="VAR1", value="value1")],
        )

        # Assertions
        self.assertIsInstance(deployment, client.V1Deployment)
        self.assertEqual(deployment.metadata.name, "my-deployment")
        self.assertEqual(deployment.metadata.namespace, self.namespace)
        self.assertEqual(deployment.spec.replicas, 3)

    @patch("kubernetes.client.AppsV1Api.create_namespaced_deployment")
    def test_create_deployment(self, mock_create_namespaced_deployment):
        mocked_deployment_obj = client.V1Deployment(
            metadata=client.V1ObjectMeta(name="my-deployment")
        )
        mock_create_namespaced_deployment.return_value = mocked_deployment_obj
        deployment_result = create_or_update_deployment(
            "my-deployment", mocked_deployment_obj, self.namespace
        )

        # Assertions
        self.assertEqual(deployment_result, mocked_deployment_obj)
        mock_create_namespaced_deployment.assert_called_once_with(
            body=mocked_deployment_obj, namespace=self.namespace
        )

    @patch("kubernetes.client.AppsV1Api.patch_namespaced_deployment")
    def test_update_deployment(self, mock_patch_namespaced_deployment):
        mocked_deployment_obj = client.V1Deployment(
            metadata=client.V1ObjectMeta(name="my-deployment")
        )
        mock_patch_namespaced_deployment.return_value = mocked_deployment_obj
        api_exception = ApiException(status=409)
        with patch(
            "kubernetes.client.AppsV1Api.create_namespaced_deployment",
            side_effect=api_exception,
        ) as mock_create_namespaced_deployment:
            deployment_result = create_or_update_deployment(
                "my-deployment", mocked_deployment_obj, self.namespace
            )

            # Assertions
            self.assertEqual(deployment_result, mocked_deployment_obj)
            mock_create_namespaced_deployment.assert_called_once_with(
                body=mocked_deployment_obj, namespace=self.namespace
            )
            mock_patch_namespaced_deployment.assert_called_once_with(
                name="my-deployment",
                namespace=self.namespace,
                body=mocked_deployment_obj,
            )

    @patch("kubernetes.client.CoreV1Api.create_namespaced_service")
    @patch("kubernetes.client.CoreV1Api.patch_namespaced_service")
    def test_create_or_update_service(
        self, mock_create_namespaced_service, mock_patch_namespaced_service
    ):
        mock_create_namespaced_service.return_value = client.V1Status()
        mock_patch_namespaced_service.return_value = client.V1Status()

        mocked_service_obj = client.V1Service(
            metadata=client.V1ObjectMeta(name="my-service")
        )
        status = create_or_update_service(
            "my-service", mocked_service_obj, self.namespace
        )

        self.assertIsInstance(status, client.V1Status)

    @patch("kubernetes.client.AppsV1Api.delete_namespaced_deployment")
    def test_teardown_deployment_success(self, mock_delete_namespaced_deployment):
        # Set up mock deployment deletion
        mock_delete_namespaced_deployment.return_value = client.V1Status()

        # Call the teardown_deployment function
        status = teardown_deployment("my-deployment", self.namespace)

        # Assertions
        self.assertIsInstance(status, client.V1Status)
        mock_delete_namespaced_deployment.assert_called_once_with(
            name="my-deployment", namespace=self.namespace
        )

    @patch("kubernetes.client.AppsV1Api.delete_namespaced_deployment")
    def test_teardown_deployment_not_found(self, mock_delete_namespaced_deployment):
        # Create a fake ApiException with status code 404 to simulate the deployment not found
        api_exception = ApiException(status=404)

        # Patch the delete_namespaced_deployment function to raise the fake ApiException
        with patch(
            "kubernetes.client.AppsV1Api.delete_namespaced_deployment",
            side_effect=api_exception,
        ) as mock_delete_namespaced_deployment:
            # Call the teardown_deployment function
            status_result = teardown_deployment(
                name="my-deployment", namespace=self.namespace
            )

            # Assertions
            self.assertIsInstance(status_result, type(None))
            mock_delete_namespaced_deployment.assert_called_once_with(
                name="my-deployment", namespace=self.namespace
            )

    @patch("kubernetes.client.AppsV1Api.delete_namespaced_deployment")
    def test_teardown_deployment_error(self, mock_delete_namespaced_deployment):
        # Create a fake ApiException with a status code other than 404
        api_exception = ApiException(status=500)

        # Patch the delete_namespaced_deployment function to raise the fake ApiException
        with patch(
            "kubernetes.client.AppsV1Api.delete_namespaced_deployment",
            side_effect=api_exception,
        ) as mock_delete_namespaced_deployment:
            # Call the teardown_deployment function and expect it to raise the ApiException
            with self.assertRaises(ApiException):
                teardown_deployment(name="my-deployment", namespace=self.namespace)

            mock_delete_namespaced_deployment.assert_called_once_with(
                name="my-deployment", namespace=self.namespace
            )

    @patch("kubernetes.client.CoreV1Api.delete_namespaced_service")
    def test_teardown_service_success(self, mock_delete_namespaced_service):
        # Set up mock service deletion
        mock_delete_namespaced_service.return_value = client.V1Status()

        # Call the teardown_service function
        status = teardown_service("my-service", self.namespace)

        # Assertions
        self.assertIsInstance(status, client.V1Status)
        mock_delete_namespaced_service.assert_called_once_with(
            name="my-service", namespace=self.namespace
        )

    @patch("kubernetes.client.CoreV1Api.delete_namespaced_service")
    def test_teardown_service_not_found(self, mock_delete_namespaced_service):
        # Create a fake ApiException with status code 404 to simulate the service not found
        api_exception = ApiException(status=404)

        # Patch the delete_namespaced_service function to raise the fake ApiException
        with patch(
            "kubernetes.client.CoreV1Api.delete_namespaced_service",
            side_effect=api_exception,
        ) as mock_delete_namespaced_service:
            status_result = teardown_service(
                name="my-service", namespace=self.namespace
            )

            # Assertions
            self.assertIsInstance(status_result, type(None))
            mock_delete_namespaced_service.assert_called_once_with(
                name="my-service", namespace=self.namespace
            )

    @patch("kubernetes.client.CoreV1Api.delete_namespaced_service")
    def test_teardown_service_error(self, mock_delete_namespaced_service):
        # Create a fake ApiException with status code 404 to simulate the service not found
        api_exception = ApiException(status=500)

        # Patch the delete_namespaced_service function to raise the fake ApiException
        with patch(
            "kubernetes.client.CoreV1Api.delete_namespaced_service",
            side_effect=api_exception,
        ) as mock_delete_namespaced_service:
            # Call the teardown_deployment function and expect it to raise the ApiException
            with self.assertRaises(ApiException):
                teardown_service(name="my-service", namespace=self.namespace)

            mock_delete_namespaced_service.assert_called_once_with(
                name="my-service", namespace=self.namespace
            )

    @patch("kubernetes.client.AppsV1Api.list_namespaced_deployment")
    def test_get_deployment(self, mock_list_namespaced_deployment):
        # Create a list of mocked deployments
        mocked_deployments = [
            client.V1Deployment(metadata=client.V1ObjectMeta(name="my-deployment")),
            client.V1Deployment(metadata=client.V1ObjectMeta(name="other-deployment")),
        ]

        # Set the return value of the mocked function
        mock_list_namespaced_deployment.return_value.items = mocked_deployments

        # Call the get_deployment function
        deployment = get_deployment("my-deployment", self.namespace)

        # Assert that the deployment is an instance of client.V1Deployment and has the correct name
        self.assertIsInstance(deployment, client.V1Deployment)
        self.assertEqual(deployment.metadata.name, "my-deployment")

    @patch("kubernetes.client.CoreV1Api.create_namespaced_service")
    def test_create_service_object(self, mock_create_namespaced_service):
        # Set up mock service creation
        mock_create_namespaced_service.return_value = client.V1Service()

        # Call the create_service_object function
        service = create_service_object(
            name="my-service",
            namespace=self.namespace,
            ports=[client.V1ServicePort(name="http", port=80, target_port=8080)],
            selector={"app": "my-app"},
        )

        # Assertions
        self.assertIsInstance(service, client.V1Service)
        self.assertEqual(service.metadata.name, "my-service")
        self.assertEqual(service.metadata.namespace, self.namespace)
        self.assertEqual(service.spec.type, "ClusterIP")
        self.assertEqual(len(service.spec.ports), 1)
        self.assertEqual(service.spec.ports[0].name, "http")
        self.assertEqual(service.spec.ports[0].port, 80)
        self.assertEqual(service.spec.ports[0].target_port, 8080)
        self.assertEqual(service.spec.selector, {"app": "my-app"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main(testRunner=PrettyPrintTextTestRunner(verbosity=0))
