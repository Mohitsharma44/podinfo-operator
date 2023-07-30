import kopf
from kubernetes import client, config
from kubernetes.client import ApiException
from kubeutils import (
    create_deployment_object,
    teardown_deployment,
    teardown_service,
    get_deployment,
    create_service_object,
    create_or_update_deployment,
    create_or_update_service,
    api_core,
)

PODINFO_DEPLOYMENT_NAME = "podinfo"
PODINFO_PORT = 9898
REDIS_DEPLOYMENT_NAME = "redis"
REDIS_PORT = 6379
DEFAULT_STATUS = {"created_on": "Not Created", "uid": ""}

config.load_config()
api = client.AppsV1Api()


def create_deployment_and_service(
    name,
    namespace,
    image_repo,
    image_tag,
    replicas,
    resources,
    expose_port=None,
    env_vars=None,
):
    """
    Create a new Kubernetes deployment and service for the application.

    Parameters
    ----------
    name : str
        The name of the deployment and service.
    namespace : str
        The namespace where the deployment and service should be created.
    image_repo : str
        The container registry containing the image to be deployed.
    image_tag : str
        The tag of the container image to be deployed.
    replicas : int
        The number of replicas of the pod to be created.
    resources : kubernetes.client.V1ResourceRequirements
        The resource requirements for the container.
    expose_port : int, optional
        The port number to be exposed by the service.
    env_vars : List[kubernetes.client.V1EnvVar], optional
        The environment variables to be passed to the container.

    Returns
    -------
    Dict[str, Any]
        A dictionary containing metadata about the created deployment and service.
    """

    deploy_obj = create_deployment_object(
        name=name,
        namespace=namespace,
        image_registry=image_repo,
        image_tag=image_tag,
        replicas=replicas,
        resources=resources,
        expose_ports=[client.V1ContainerPort(container_port=expose_port)],
        env_vars=env_vars,
    )

    svc_obj = create_service_object(
        name=name,
        namespace=namespace,
        ports=[client.V1ServicePort(name=name, protocol="TCP", port=expose_port)],
        selector={"app.kubernetes.io/name": name},
    )

    kopf.adopt(deploy_obj)
    kopf.adopt(svc_obj)

    deployment = create_or_update_deployment(
        name=name, deploy_obj=deploy_obj, namespace=namespace
    )
    service = create_or_update_service(name=name, svc_obj=svc_obj, namespace=namespace)

    metadata = {
        "created_on": deployment.metadata.creation_timestamp.strftime("%c"),
        "uid": deployment.metadata.uid,
    }
    return metadata


def create_podinfo_deployment_and_service(namespace, spec):
    """
    Create a new PodInfo deployment and service in the specified namespace.

    Parameters
    ----------
    namespace : str
        The namespace where the deployment and service should be created.
    spec : dict
        A dictionary containing the specifications of the PodInfo deployment.

    Returns
    -------
    Dict[str, Any]
        A dictionary containing metadata about the created PodInfo deployment and service.
    """
    ui_vars = [
        client.V1EnvVar(name=f"PODINFO_UI_{k.upper()}", value=v)
        for k, v in spec.get("ui", {}).items()
    ]

    # TODO: Maybe we should set this only if redis.enabled is true otherwise set it to empty string?
    default_env_vars = [
        client.V1EnvVar(
            name=f"PODINFO_CACHE_SERVER",
            value=f"tcp://{REDIS_DEPLOYMENT_NAME}:{REDIS_PORT}",
        )
    ]
    env_vars = default_env_vars + ui_vars
    return create_deployment_and_service(
        name=PODINFO_DEPLOYMENT_NAME,
        namespace=namespace,
        image_repo=spec.get("image")["repository"],
        image_tag=spec.get("image")["tag"],
        replicas=spec.get("replicaCount"),
        resources=client.V1ResourceRequirements(
            requests={"cpu": spec.get("resources")["cpuRequest"]},
            limits={"memory": spec.get("resources")["memoryLimit"]},
        ),
        expose_port=PODINFO_PORT,
        env_vars=env_vars,
    )


def create_redis_deployment_and_service(namespace, spec):
    """
    Create a new Redis deployment and service in the specified namespace.

    Parameters
    ----------
    namespace : str
        The namespace where the deployment and service should be created.
    spec : dict
        A dictionary containing the specifications of the Redis deployment.

    Returns
    -------
    Dict[str, Any]
        A dictionary containing metadata about the created Redis deployment and service.
    """
    return create_deployment_and_service(
        name=REDIS_DEPLOYMENT_NAME,
        namespace=namespace,
        image_repo="redis",
        image_tag="7.0.12",
        replicas=1,
        resources=client.V1ResourceRequirements(
            requests={"cpu": "100m", "memory": "32Mi"},
            limits={"cpu": "1000m", "memory": "128Mi"},
        ),
        expose_port=REDIS_PORT,
    )


@kopf.on.create("my.api.group", "v1alpha1", "MyAppResource")
def on_create(meta, spec, namespace, logger, body, **kwargs):
    """
    Handler for the creation of the custom MyAppResource.

    Parameters
    ----------
    meta : dict
        Metadata of the custom resource.
    spec : dict
        Specifications of the custom resource.
    namespace : str
        The namespace in which the custom resource is created.
    logger : kopf.Logger
        Logger object for logging messages.
    body : dict
        The custom resource object itself.
    **kwargs : dict
        Additional arguments passed to the handler.

    Returns
    -------
    dict
        A dictionary containing the children resources created by the operator.
    """
    redis_enabled = spec.get("redis", {}).get("enabled")

    podinfo_status = create_podinfo_deployment_and_service(
        namespace=namespace, spec=spec
    )

    redis_status = DEFAULT_STATUS
    if redis_enabled:
        redis_status = create_redis_deployment_and_service(
            namespace=namespace, spec=spec
        )

    return {
        "children": {
            "redis": redis_status,
            "podInfo": podinfo_status,
        }
    }


@kopf.on.update("my.api.group", "v1alpha1", "MyAppResource")
def on_update(meta, spec, status, namespace, old, new, diff, logger, **kwargs):
    """
    Handler for the update of the custom MyAppResource.

    Parameters
    ----------
    meta : dict
        Metadata of the custom resource.
    spec : dict
        Specifications of the custom resource.
    status : dict
        Status of the custom resource.
    namespace : str
        The namespace in which the custom resource is located.
    old : dict
        The old state of the custom resource.
    new : dict
        The new state of the custom resource.
    diff : list
        List of differences between the old and new states.
    logger : kopf.Logger
        Logger object for logging messages.
    **kwargs : dict
        Additional arguments passed to the handler.

    Returns
    -------
    dict
        A dictionary containing the updated children resources managed by the operator.
    """
    new_status = status["on_create"]["children"]
    for oper, field, old_val, new_val in diff:
        if "redis" in field:
            # We currently only support enabling or disabling redis.
            redis_enabled = ("spec", "redis", "enabled") == field and new_val
            # If redis has been enabled but doesn't have a deployment yet, create it.
            if redis_enabled:
                if not get_deployment(name="redis", namespace=namespace):
                    redis_status = create_redis_deployment_and_service(
                        namespace=namespace, spec=spec
                    )
                    new_status.update({"redis": redis_status})
            else:
                # If redis has been disabled, teardown the deployment and service
                teardown_deployment(name="redis", namespace=namespace)
                teardown_service(name="redis", namespace=namespace)
                # TODO: Maybe we should also update podinfo deployment by setting its
                # PODINFO_CACHE_SERVER env var to an empty string
        else:
            # Update podInfo
            # If podinfo deployment has been created in the create stage, we should patch it
            # but if for some reason it wasn't, we should just ignore the change.
            if get_deployment(name="podinfo", namespace=namespace):
                podinfo_status = create_podinfo_deployment_and_service(
                    namespace=namespace, spec=spec
                )
                new_status.update({"podInfo": podinfo_status})

    return new_status
