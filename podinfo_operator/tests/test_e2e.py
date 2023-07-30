import unittest
import os
import sys
import yaml
import json
import time
import requests
import redis
import subprocess
from kubernetes import config, client, utils, stream
from kubernetes.client import ApiException
from kubernetes.utils.create_from_yaml import FailToCreateError
from utils import PrettyPrintTextTestRunner

TOP_LEVEL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROOT_DIR = os.path.abspath(os.path.join(TOP_LEVEL_DIR, ".."))
sys.path.append(TOP_LEVEL_DIR)


def setup_kubernetes_config():
    """Set up the Kubernetes configuration using kubernetes.config.

    This function first attempts to load the configuration from outside the cluster using
    'config.load_kube_config()' and if that fails, it tries to load the configuration from
    inside a Kubernetes pod using 'config.load_incluster_config()'.

    Raises:
        Exception: If the Kubernetes configuration cannot be set up.

    """
    try:
        # outside k8s
        config.load_kube_config()
    except config.config_exception.ConfigException:
        try:
            # inside a k8s pod
            config.load_incluster_config()
        except config.config_exception.ConfigException:
            raise Exception("Could not configure kubernetes python client")


def wait_for_resource_ready(namespace, resource_name, resource_type, timeout):
    """Wait for a Kubernetes resource to become ready.

    Args:
        namespace (str): The namespace of the resource.
        resource_name (str): The name of the resource.
        resource_type (str): The type of the resource. Can be "service" or "deployment".
        timeout (int): The maximum time to wait for the resource to become ready.

    Returns:
        bool: True if the resource becomes ready within the timeout, False otherwise.

    """
    start_time = time.time()
    api_apps = client.AppsV1Api()
    api_core = client.CoreV1Api()

    while True:
        try:
            if resource_type == "service":
                resource = api_core.read_namespaced_endpoints(resource_name, namespace)
                if len(resource.subsets) > 0:
                    return True

            elif resource_type == "deployment":
                resource = api_apps.read_namespaced_deployment(resource_name, namespace)
                if (
                    resource.status.ready_replicas is not None
                    and resource.status.ready_replicas > 0
                ):
                    return True

            else:
                raise ValueError(f"Unsupported resource type: {resource_type}")

        except ApiException as ex:
            if ex.status == 404:
                pass
            else:
                raise

        elapsed_time = time.time() - start_time
        if elapsed_time >= timeout:
            return False

        time.sleep(1)


def start_port_forwarding(deployment_name, namespace, local_port, pod_port):
    """Start port forwarding to a Kubernetes pod.

    Args:
        deployment_name (str): The name of the deployment containing the pod to port forward.
        namespace (str): The namespace of the deployment.
        local_port (int): The local port to forward to.
        pod_port (int): The port on the pod to forward from.

    Returns:
        subprocess.Popen: The subprocess that starts the port forwarding.

    Raises:
        Exception: If the pod cannot be found or if port forwarding fails to start.

    """
    api_core = client.CoreV1Api()

    try:
        pods = api_core.list_namespaced_pod(namespace=namespace).items
        pod_name = [
            pod.metadata.name
            for pod in pods
            if pod.metadata.labels.get("app.kubernetes.io/name") == deployment_name
        ][0]
    except client.rest.ApiException as e:
        raise Exception(
            f"Failed to get pod '{pod_name}' in namespace '{namespace}'. Error: {e}"
        )

    port_forward_command = [
        "kubectl",
        "port-forward",
        f"pod/{pod_name}",
        f"{local_port}:{pod_port}",
        f"--namespace={namespace}",
    ]

    try:
        return subprocess.Popen(
            port_forward_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
    except Exception as e:
        msg = f"Failed to establish port forward to pod '{pod_name}' in namespace '{namespace}'. Error: {e}"
        raise Exception(msg)


class E2e(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        setup_kubernetes_config()
        cls.test_namespace = f"podinfo-e2e-{int(time.time())}"
        cls.cleanup_tasks = []
        api_core = client.CoreV1Api()
        ns_body = client.V1Namespace(metadata=client.V1ObjectMeta(name=cls.test_namespace))
        try:
            api_core.create_namespace(ns_body)
        except ApiException as ex:
            if not ex.status == 409:
                raise
        cls.cleanup_tasks.append(
            lambda: api_core.delete_namespace(cls.test_namespace)
        )

    @classmethod
    def tearDownClass(cls):
        print("Cleaning up resources...")
        for cleanup_task in cls.cleanup_tasks[::-1]:
            cleanup_task()


    def test_01_create_crd(self):
        # Test case to create a custom resource definition
        crd_api = client.ApiextensionsV1Api()
        path_to_crd_yaml = os.path.join(ROOT_DIR, "deploy", "crd.yaml")
        k8s_client = client.api_client.ApiClient()

        try:
            utils.create_from_yaml(k8s_client, path_to_crd_yaml)
        except FailToCreateError as ex:
            if not ex.api_exceptions[0].status == 409:
                raise

        crd = crd_api.read_custom_resource_definition(
            name="myappresources.my.api.group"
        )
        self.assertIsNotNone(crd)
        self.assertIsInstance(
            crd, client.models.v1_custom_resource_definition.V1CustomResourceDefinition
        )

        self.cleanup_tasks.append(
            lambda: crd_api.delete_custom_resource_definition(
                "myappresources.my.api.group"
            )
        )

    def test_02_create_rbac(self):
        # Test case to create role-based access control resources
        api_core = client.CoreV1Api()
        api_rbac = client.RbacAuthorizationV1Api()

        path_to_rbac_yaml = os.path.join(ROOT_DIR, "deploy", "rbac.yaml")
        k8s_client = client.api_client.ApiClient()

        with open(path_to_rbac_yaml, "r") as fh:
            rbac_yaml = yaml.safe_load_all(fh)
            rbac_yaml_li = [x for x in rbac_yaml]

        for rbac in rbac_yaml_li:
            if rbac["metadata"].get("namespace"):
                rbac["metadata"]["namespace"] = self.test_namespace
            elif rbac.get("subjects"):
                rbac["subjects"][0]["namespace"] = self.test_namespace
            try:
                utils.create_from_dict(k8s_client, rbac)
            except FailToCreateError as ex:
                if not ex.api_exceptions[0].status == 409:
                    raise

        sa = api_core.read_namespaced_service_account(
            name="podinfo-account", namespace=self.test_namespace
        )
        cr = api_rbac.read_cluster_role("podinfo-role-cluster")
        cb = api_rbac.read_cluster_role_binding("podinfo-rolebinding-cluster")
        role = api_rbac.read_namespaced_role(
            name="podinfo-role-namespaced", namespace=self.test_namespace
        )
        rb = api_rbac.read_namespaced_role_binding(
            name="podinfo-rolebinding-namespaced", namespace=self.test_namespace
        )

        self.assertIsNotNone(sa)
        self.assertEqual(sa.metadata.name, "podinfo-account")
        self.assertIsInstance(sa, client.models.v1_service_account.V1ServiceAccount)

        self.assertIsNotNone(cr)
        self.assertEqual(cr.metadata.name, "podinfo-role-cluster")
        self.assertIsInstance(cr, client.models.v1_cluster_role.V1ClusterRole)

        self.assertIsNotNone(role)
        self.assertEqual(role.metadata.name, "podinfo-role-namespaced")
        self.assertIsInstance(role, client.models.v1_role.V1Role)

        self.assertIsNotNone(cb)
        self.assertEqual(cb.metadata.name, "podinfo-rolebinding-cluster")
        self.assertIsInstance(
            cb, client.models.v1_cluster_role_binding.V1ClusterRoleBinding
        )

        self.assertIsNotNone(rb)
        self.assertEqual(rb.metadata.name, "podinfo-rolebinding-namespaced")
        self.assertIsInstance(rb, client.models.v1_role_binding.V1RoleBinding)

        self.cleanup_tasks.append(
            lambda: api_core.delete_namespaced_service_account(
                name="podinfo-account", namespace=self.test_namespace
            )
        )
        self.cleanup_tasks.append(
            lambda: api_rbac.delete_cluster_role("podinfo-role-cluster")
        )
        self.cleanup_tasks.append(
            lambda: api_rbac.delete_cluster_role_binding("podinfo-rolebinding-cluster")
        )
        self.cleanup_tasks.append(
            lambda: api_rbac.delete_namespaced_role(
                name="podinfo-role-namespaced", namespace=self.test_namespace
            )
        )
        self.cleanup_tasks.append(
            lambda: api_rbac.delete_namespaced_role_binding(
                name="podinfo-rolebinding-namespaced", namespace=self.test_namespace
            )
        )

    def test_03_create_operator_deployment(self):
        # Test case to create the operator deployment
        api_apps = client.AppsV1Api()

        path_to_deployment_yaml = os.path.join(ROOT_DIR, "deploy", "deployment.yaml")
        k8s_client = client.api_client.ApiClient()

        with open(path_to_deployment_yaml, "r") as fh:
            deploy_dict = yaml.safe_load(fh)
        deploy_dict["metadata"]["namespace"] = self.test_namespace

        try:
            utils.create_from_dict(k8s_client, deploy_dict)
        except FailToCreateError as ex:
            if not ex.api_exceptions[0].status == 409:
                raise

        deploy = api_apps.read_namespaced_deployment(
            name="podinfo-operator", namespace=self.test_namespace
        )
        self.assertIsNotNone(deploy)
        self.assertEqual(deploy.metadata.name, "podinfo-operator")
        self.assertIsInstance(deploy, client.V1Deployment)

        self.cleanup_tasks.append(
            lambda: api_apps.delete_namespaced_deployment(
                name="podinfo-operator", namespace=self.test_namespace
            )
        )

    def test_04_create_cr(self):
        # Test case to create a custom resource
        api_custom = client.CustomObjectsApi()

        path_to_cr_yaml = os.path.join(ROOT_DIR, "deploy", "cr.yaml")
        k8s_client = client.api_client.ApiClient()

        with open(path_to_cr_yaml, "r") as fh:
            cr_dict = yaml.safe_load(fh)
        cr_dict["metadata"]["namespace"] = self.test_namespace
        cr_group, cr_version = cr_dict["apiVersion"].split("/")

        try:
            api_custom.create_namespaced_custom_object(
                group=cr_group,
                version=cr_version,
                body=cr_dict,
                namespace=self.test_namespace,
                plural="myappresources",
            )
        except ApiException as ex:
            if not ex.status == 409:
                raise

        cr = api_custom.get_namespaced_custom_object(
            group=cr_group,
            version=cr_version,
            name=cr_dict["metadata"]["name"],
            namespace=self.test_namespace,
            plural="myappresources",
        )

        self.assertIsNotNone(cr)
        self.assertIsInstance(cr, dict)
        self.assertEqual(cr["metadata"]["name"], cr_dict["metadata"]["name"])

        self.cleanup_tasks.append(
            lambda: api_custom.delete_namespaced_custom_object(
                group=cr_group,
                version=cr_version,
                name=cr_dict["metadata"]["name"],
                namespace=self.test_namespace,
                plural="myappresources",
            )
        )

    def test_05_get_podinfo_deployment(self):
        # Test case to get the podinfo deployment
        # It takes a few moments for test_04 to trigger creation of
        # deployments and services
        api_apps = client.AppsV1Api()

        deploy_ready = wait_for_resource_ready(
            namespace=self.test_namespace,
            resource_name="podinfo",
            resource_type="deployment",
            timeout=30,
        )
        if deploy_ready:
            deploy = api_apps.read_namespaced_deployment(
                name="podinfo", namespace=self.test_namespace
            )
            self.assertIsNotNone(deploy)
            self.assertEqual(deploy.metadata.name, "podinfo")
            self.assertIsInstance(deploy, client.V1Deployment)
        else:
            self.fail(
                "Deployment podinfo did not become ready within the timeout period."
            )

    def test_06_get_redis_deployment(self):
        # Test case to get the redis deployment
        # It takes a few moments for test_04 to trigger creation of
        # deployments and services
        api_apps = client.AppsV1Api()

        deploy_ready = wait_for_resource_ready(
            namespace=self.test_namespace,
            resource_name="redis",
            resource_type="deployment",
            timeout=30,
        )
        if deploy_ready:
            deploy = api_apps.read_namespaced_deployment(
                name="redis", namespace=self.test_namespace
            )
            self.assertIsNotNone(deploy)
            self.assertEqual(deploy.metadata.name, "redis")
            self.assertIsInstance(deploy, client.V1Deployment)
        else:
            self.fail(
                "Deployment redis did not become ready within the timeout period."
            )

    def test_07_get_podinfo_service(self):
        # Test case to get the podinfo service
        api_core = client.CoreV1Api()

        service_ready = wait_for_resource_ready(
            namespace=self.test_namespace,
            resource_name="podinfo",
            resource_type="service",
            timeout=30,
        )
        if service_ready:
            svc = api_core.read_namespaced_service(
                name="podinfo", namespace=self.test_namespace
            )
            self.assertIsNotNone(svc)
            self.assertEqual(svc.metadata.name, "podinfo")
            self.assertIsInstance(svc, client.V1Service)
        else:
            self.fail("Service did not become ready within the timeout period.")

    def test_08_get_redis_service(self):
        # Test case to get the podinfo service
        api_core = client.CoreV1Api()

        service_ready = wait_for_resource_ready(
            namespace=self.test_namespace,
            resource_name="redis",
            resource_type="service",
            timeout=30,
        )
        if service_ready:
            svc = api_core.read_namespaced_service(
                name="redis", namespace=self.test_namespace
            )
            self.assertIsNotNone(svc)
            self.assertEqual(svc.metadata.name, "redis")
            self.assertIsInstance(svc, client.V1Service)
        else:
            self.fail("Service did not become ready within the timeout period.")

    def test_09_port_forward_podinfo_and_test(self):
        namespace = self.test_namespace
        deployment_name = "podinfo"
        local_port = 9898
        remote_port = 9898

        # Start port-forwarding in the background
        self.port_forward_process = start_port_forwarding(
            deployment_name, namespace, local_port, remote_port
        )

        # Wait for a moment to make sure port-forwarding is established
        time.sleep(3)

        deploy_ready = wait_for_resource_ready(
            namespace=self.test_namespace,
            resource_name="podinfo",
            resource_type="deployment",
            timeout=30,
        )
        path_to_cr_yaml = os.path.join(ROOT_DIR, "deploy", "cr.yaml")
        with open(path_to_cr_yaml, "r") as fh:
            cr_dict = yaml.safe_load(fh)

        if deploy_ready:
            # Make a HTTP request to the forwarded port
            url = f"http://127.0.0.1:{local_port}"
            response = requests.get(url)

            # Check if the response status code is 200
            self.assertEqual(response.status_code, 200)
            if response.status_code == 200:
                body = json.loads(response.content.decode("utf-8"))
                self.assertEqual(body["color"], cr_dict["spec"]["ui"]["color"])
                self.assertEqual(body["message"], cr_dict["spec"]["ui"]["message"])
            else:
                self.fail("Could not get a 200 response.")
        else:
            self.fail("Service did not become ready within the timeout period.")

        self.port_forward_process.terminate()

    def test_10_port_forward_redis_and_test(self):
        namespace = self.test_namespace
        deployment_name = "redis"
        local_port = 6379
        remote_port = 6379

        # Start port-forwarding in the background
        self.port_forward_process = start_port_forwarding(
            deployment_name, namespace, local_port, remote_port
        )

        # Wait for a moment to make sure port-forwarding is established
        time.sleep(3)

        service_ready = wait_for_resource_ready(
            namespace=self.test_namespace,
            resource_name="redis",
            resource_type="service",
            timeout=30,
        )
        path_to_cr_yaml = os.path.join(ROOT_DIR, "deploy", "cr.yaml")
        with open(path_to_cr_yaml, "r") as fh:
            cr_dict = yaml.safe_load(fh)

        if service_ready:
            redis_client = redis.StrictRedis(host="127.0.0.1", port=local_port, decode_responses=True)
            test_key = "foo"
            test_value = "bar"
            redis_client.set(test_key, test_value)
            got_value = redis_client.get(test_key)

            # Check if the response status code is 200
            self.assertEqual(test_value, got_value)
        else:
            self.fail("There is a mismatch in what we stored in redis and the value we received back.")

        self.port_forward_process.terminate()


if __name__ == "__main__":  # pragma: no cover
    print("Running end-to-end tests for PodInfoOperator...")
    unittest.main(testRunner=PrettyPrintTextTestRunner(verbosity=0))
