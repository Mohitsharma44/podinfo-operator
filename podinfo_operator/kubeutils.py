from typing import Optional
from kubernetes import client, config
from kubernetes.client import ApiException


try:
    # outside k8s
    config.load_kube_config()
except config.config_exception.ConfigException:  # pragma: no cover
    try:
        # inside a k8s pod
        config.load_incluster_config()
    except config.config_exception.ConfigException:  # pragma: no cover
        raise Exception("Could not configure kubernetes python client")


api_apps: client.AppsV1Api = client.AppsV1Api()
api_core: client.CoreV1Api = client.CoreV1Api()


def create_deployment_object(
    name: str,
    namespace: str,
    image_registry: str,
    image_tag: str,
    replicas: int,
    resources: client.V1ResourceRequirements,
    expose_ports: Optional[client.V1ContainerPort] = None,
    env_vars: Optional[client.V1EnvVar] = None,
) -> client.V1Deployment:
    """
    Create a new Kubernetes deployment object.

    Parameters
    ----------
    name : str
        The name of the deployment.
    namespace : str
        The namespace where the deployment should be created.
    image_registry : str
        The container registry containing the image to be deployed.
    image_tag : str
        The tag of the container image to be deployed.
    replicas : int
        The number of replicas of the pod to be created.
    resources : kubernetes.client.V1ResourceRequirements
        The resource requirements for the container.
    expose_ports : kubernetes.client.V1ContainerPort, optional
        The ports to be exposed on the container.
    env_vars : kubernetes.client.V1EnvVar, optional
        The environment variables to be passed to the container.

    Returns
    -------
    kubernetes.client.V1Deployment
        A Kubernetes V1Deployment object representing the deployment.
    """
    # Configureate Pod template container
    container = client.V1Container(
        name=name,
        image=f"{image_registry}:{image_tag}",
        ports=expose_ports,
        resources=resources,
        env=env_vars,
    )

    # Create and configure a spec section
    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(
            labels={"app.kubernetes.io/name": name}, namespace=namespace
        ),
        spec=client.V1PodSpec(containers=[container]),
    )

    # Create the specification of deployment
    spec = client.V1DeploymentSpec(
        replicas=replicas,
        template=template,
        selector={"matchLabels": {"app.kubernetes.io/name": name}},
    )

    # Instantiate the deployment object
    deployment = client.V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        spec=spec,
    )

    return deployment


def create_or_update_deployment(
    name: str, deploy_obj: client.V1Deployment, namespace: str
):
    """
    Create or Update a deployment in the given namespace.

    Parameters
    ----------
    name : str
        The name of the deployment to create/ update.
    deploy_obj: client.V1Deployment
        The deployment object
    namespace : str
        The namespace in which the deployment should be created.

    Returns
    -------
    kubernetes.client.V1Status
    """
    try:
        deployment = api_apps.create_namespaced_deployment(
            body=deploy_obj, namespace=namespace
        )
    except ApiException as ex:
        # If deployment already exists, patch it instead
        if ex.status == 409:
            deployment = api_apps.patch_namespaced_deployment(
                name=name, namespace=namespace, body=deploy_obj
            )
    return deployment


def create_or_update_service(name: str, svc_obj: client.V1Service, namespace: str):
    """
    Create or Update a service in the given namespace.

    Parameters
    ----------
    name : str
        The name of the service to create/ update.
    svc_obj: client.V1Service
        The service object
    namespace : str
        The namespace in which the service should be created/ exists.

    Returns
    -------
    kubernetes.client.V1Status
    """
    try:
        service = api_core.create_namespaced_service(namespace=namespace, body=svc_obj)
    except ApiException as ex:
        # If service already exists, patch it instead
        if ex.status == 409:
            service = api_core.patch_namespaced_service(
                name=name, namespace=namespace, body=svc_obj
            )
    return service


def teardown_deployment(name: str, namespace: str):
    """
    Delete a deployment from the given namespace.

    Parameters
    ----------
    name : str
        The name of the deployment to delete.
    namespace : str
        The namespace in which the deployment exists.

    Returns
    -------
    kubernetes.client.V1Status
        The status of the delete operation.
    """
    try:
        return api_apps.delete_namespaced_deployment(name=name, namespace=namespace)
    except ApiException as ex:
        if not ex.status == 404:
            raise


def teardown_service(name: str, namespace: str):
    """
    Delete a service from the given namespace.

    Parameters
    ----------
    name : str
        The name of the service to delete.
    namespace : str
        The namespace in which the service exists.

    Returns
    -------
    kubernetes.client.V1Status
        The status of the delete operation.
    """
    try:
        return api_core.delete_namespaced_service(name=name, namespace=namespace)
    except ApiException as ex:
        if not ex.status == 404:
            raise


def get_deployment(name: str, namespace: str) -> Optional[client.V1Deployment]:
    """
    Retrieve a deployment from a given namespace.

    Parameters
    ----------
    name : str
        The name of the deployment to retrieve.
    namespace : str
        The namespace in which the deployment is located.

    Returns
    -------
    Optional[kubernetes.client.V1Deployment]
        A V1Deployment object matching the name and namespace criteria,
        or None if the deployment is not found.
    """
    deployments_dict = api_apps.list_namespaced_deployment(namespace=namespace)
    for deployment in deployments_dict.items:
        if deployment.metadata.name == name:
            return deployment
    return None


def create_service_object(
    name: str, namespace: str, ports: [client.V1ServicePort], selector: {str, str}
) -> client.V1Service:
    """
    Create a new Kubernetes service object of type ClusterIP.

    Parameters
    ----------
    name : str
        The name of the service.
    namespace : str
        The namespace where the service should be created.
    ports : List[kubernetes.client.V1ServicePort]
        A list of ports exposed by the service.
    selector : Dict[str, str]
        A dictionary containing labels used to select pods for the service.

    Returns
    -------
    kubernetes.client.V1Service
        A Kubernetes V1Service object representing the service.
    """
    spec = client.V1ServiceSpec(selector=selector, ports=ports, type="ClusterIP")

    svc = client.V1Service(
        api_version="v1",
        kind="Service",
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        spec=spec,
    )

    return svc
