# PodInfo Operator

![Tests](https://github.com/mohitsharma44/podinfo-operator/actions/workflows/main.yml/badge.svg)

This repository contains an operator implementation for managing `MyAppResource` custom resources in a Kubernetes cluster. 
The operator handles the creation and management of the [PodInfo](https://github.com/stefanprodan/podinfo) and [Redis](https://hub.docker.com/_/redis) deployment and their corresponding services based on the provided specifications in the custom resource.

- [PodInfo Operator](#podinfo-operator)
  - [Instructions](#instructions)
    - [Using run.sh script](#using-runsh-script)
    - [Manually](#manually)
  - [Usage](#usage)
  - [Cleanup](#cleanup)
  - [Development](#development)
  - [Test](#test)
  - [License](#license)

## Instructions

Before you begin, you'll need the following installed on your MacOS/ Linux machines:

1. [Docker](https://www.docker.com/products/docker-desktop/) or [Podman](https://podman.io/docs/installation)
2. [Kind](https://kind.sigs.k8s.io/docs/user/quick-start/) or any other kubernetes cluster

Once you have installed the above two dependencies, you can use the `./run.sh` convenience script or checkout manual steps.

### Using run.sh script

This operator comes with a handy bash script aptly named `run.sh` that you can use to:

```bash
❯❯❯ ./run.sh
Usage: run.sh [command]

Commands:
  create_cluster     Spin up a Kind cluster.
  install_operator   Install podinfo-operator on the active cluster.
  uninstall_operator Uninstall podinfo-operator on the active cluster.
  unit_test          Run unit tests
  e2e_test           Run e2e test on the active cluster.
  cleanup            Cleanup the operator and delete the Kind cluster
```

### Manually

1. Create a kind cluster
   ```bash
   kind create cluster --name podinfo-cluster
   ```

2. Install the operator
   ```bash
   kubectl apply -f deploy/crd.yaml,deploy/rbac.yaml,deploy/deployment.yaml
   ```

3. Install the custom resource sample
   ```bash
   kubectl apply -f deploy/cr.yaml
   ```

4. Check the deployments, services and the custom resource
   ```bash
   # You should see podinfo-operator, podinfo and redis deployments
   kubectl get deployments -n default 

   # You should see podinfo and redis services
   kubectl get service -n default

   # You should see a MyAppResource with the name whatever and some of its children\'s status (podinfo and redis) 
   kubectl get MyAppResource whatever
   ```

5. Run some tests
   ```bash
   cd podinfo_operator/tests
   
   # unit tests
   python test_kubeutils.py
   python test_podinfo_operator.py

   # e2e tests
   python test_e2e.py
   ```

6. Delete the custom resource
   ```bash
   kubectl delete -f deploy/cr.yaml   
   ```

7. Remove the operator
   ```bash
   kubectl delete -f deploy/deployment.yaml,deploy/rbac.yaml,deploy/crd.yaml
   ```

8. Delete the cluster
   ```bash
   kind delete cluster --name podinfo-cluster
   ```


## Usage

To use the operator, create or update `MyAppResource` custom resources with the desired specifications. 

The operator will automatically create and manage the PodInfo and Redis applications based on the provided configuration.

> Note: The operator gets deployed on the cluster as a Deployment with 1 Replica. We must not increase the replica count to > 1 until we can implement peering. Refer https://kopf.readthedocs.io/en/stable/peering/#peering


Here's an example `MyAppResource` custom resource specification:

```yaml
apiVersion: my.api.group/v1alpha1
kind: MyAppResource
metadata:
  name: whatever
spec:
  replicaCount: 2
  resources:
    memoryLimit: 64Mi
    cpuRequest: 100m
  image:
    repository: ghcr.io/stefanprodan/podinfo
    tag: "latest"
  ui:
    color: "#34577c"
    message: "some string"
  redis:
    enabled: true

```

In the above example, the operator will create a PodInfo deployment and service along with a Redis deployment and service in the `default` namespace. The PodInfo application will use the specified container image and resource requirements along with the ui attributes as environment variables. Similarly, the Redis application will use the default Redis image and resource requirements.


## Cleanup

To cleanup the operator and delete the cluster, run the following command:

```bash
./run.sh cleanup
```

## Development

To setup your machine for development, you'll need to install a few python packages. You can do that by running:
```bash
pip install -r requirements.txt
```

The operator behavior can be customized by modifying the `podinfo_operator.py` file. 
The file contains the main logic for handling `MyAppResource` custom resources, including deployment and service creation, patching, and teardown.
Some kubernetes-specific helper functions are in kubeutils.

For iterative development, you can run:
```bash
kopf run podinfo_operator.py --verbose
```
and have the operator logs stream on your dev machine.

Once you are happy, you can create the container image for the operator by running
```bash
docker build -t mohitsharma44/podinfo_operator . --platform=linux/amd64
```

## Test

For testing, we simply use python's unittest library with some custom reporting.
One can run tests using the `run.sh` script as:
```bash
# To run unit tests
./run.sh unit_test

# To run e2e tests (this is non exhaustive and still a WIP)
./run.sh e2e_test
```

## License

This project is licensed under the [MIT License](LICENSE).
