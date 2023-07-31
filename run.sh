#!/usr/bin/env bash

COLOR_RESET='\033[0m'
COLOR_DEBUG='\033[1;36m'
COLOR_INFO='\033[1;32m'
COLOR_ERROR='\033[1;31m'

get_date_time() {
  date +"%Y-%m-%d %H:%M:%S"
}

run_command() {
  echo -e "[$(get_date_time)] Running command: $1"
  eval "$1"
  exit_code=$?
  if [ $exit_code -eq 0 ]; then
    echo -e "[$(get_date_time)] Command '$1' completed successfully"
  else
    echo -e "[$(get_date_time)] Command '$1' failed with exit code $exit_code and the following error:"
    exit $exit_code
  fi
}

## Function to apply YAML manifests to Kubernetes.
apply_yaml_manifests() {
  local yaml_files=("$@")

  for file in "${yaml_files[@]}"; do
    echo -e "${COLOR_DEBUG}[$(get_date_time)] Applying $file${COLOR_RESET}"
    run_command "kubectl apply -f $file"
  done
}

## Function to delete YAML manifests from Kubernetes.
delete_yaml_manifests() {
  local yaml_files=("$@")

  for file in "${yaml_files[@]}"; do
    echo -e "${COLOR_DEBUG}[$(get_date_time)] Deleting $file${COLOR_RESET}"
    run_command "kubectl delete --ignore-not-found=true -f $file"
  done
}

## Create kind cluster.
create_cluster() {
  echo -e "${COLOR_INFO}[$(get_date_time)] Creating Kind cluster...${COLOR_RESET}"
  run_command "kind create cluster --name podinfo-cluster"
  echo -e "${COLOR_INFO}[$(get_date_time)] Changing default context to the Kind cluster...${COLOR_RESET}"
  run_command "kubectl config use-context kind-podinfo-cluster"
  echo -e "${COLOR_INFO}[$(get_date_time)] Building operator container image...${COLOR_RESET}"
  run_command "docker build -t mohitsharma44/podinfo_operator . --platform=linux/amd64"
  echo -e "${COLOR_INFO}[$(get_date_time)] Pulling redis container image...${COLOR_RESET}"
  run_command "docker pull redis:latest"
  echo -e "${COLOR_INFO}[$(get_date_time)] Loading operator container image in the Kind cluster...${COLOR_RESET}"
  run_command "kind load docker-image docker.io/mohitsharma44/podinfo_operator:latest -n podinfo-cluster"
  run_command "kind load docker-image docker.io/redis:latest -n podinfo-cluster"
  echo -e "${COLOR_INFO}Cluster created.${COLOR_RESET}"
}

## Install podinfo operator.
install_operator() {
  echo -e "${COLOR_INFO}[$(get_date_time)] Installing operator in $(kubectl config current-context)${COLOR_RESET}"
  apply_yaml_manifests "deploy/crd.yaml" "deploy/rbac.yaml" "deploy/deployment.yaml"
  echo -e "${COLOR_INFO}Operator installation completed. You can now install MyAppResource. For example, refer deploy/cr.yaml${COLOR_RESET}"
}

## Run unit tests.
unit_test() {
  echo -e "${COLOR_INFO}[$(get_date_time)] Running unit tests...${COLOR_RESET}"
  echo -e "${COLOR_DEBUG}[$(get_date_time)] Testing kubeutils${COLOR_RESET}"
  run_command "cd podinfo_operator/tests && python test_kubeutils.py"
  echo
  echo -e "${COLOR_DEBUG}[$(get_date_time)] Testing podinfo_operator${COLOR_RESET}"
  run_command " python test_podinfo_operator.py"
  echo -e "${COLOR_INFO}Unit tests completed.${COLOR_RESET}"
}

## Run e2e tests.
e2e_test() {
  echo -e "${COLOR_INFO}[$(get_date_time)] Running e2e tests...${COLOR_RESET}"
  run_command "cd podinfo_operator/tests && python test_e2e.py"
  echo -e "${COLOR_INFO}E2E tests completed.${COLOR_RESET}"
}

## Uninstall podinfo operator.
uninstall_operator() {
  echo -e "${COLOR_INFO}[$(get_date_time)] Deleting operator from $(kubectl config current-context)${COLOR_RESET}"
  delete_yaml_manifests "deploy/deployment.yaml" "deploy/rbac.yaml" "deploy/crd.yaml"
  echo -e "${COLOR_INFO}Operator deletion completed.${COLOR_RESET}"
}

## Remove kind cluster.
cleanup() {
  uninstall_operator
  echo -e "${COLOR_INFO}[$(get_date_time)] Removing Kind cluster...${COLOR_RESET}"
  run_command "kind delete cluster --name podinfo-cluster"
  echo -e "${COLOR_INFO}Cluster deleted.${COLOR_RESET}"
}

## Show help information for the script.
show_help() {
  echo -e "${COLOR_INFO}Usage: script.sh [command]${COLOR_RESET}"
  echo ""
  echo -e "${COLOR_INFO}Commands:${COLOR_RESET}"
  echo -e "${COLOR_DEBUG}  create_cluster     ${COLOR_RESET}Spin up a Kind cluster."
  echo -e "${COLOR_DEBUG}  install_operator   ${COLOR_RESET}Install podinfo-operator on the active cluster."
  echo -e "${COLOR_DEBUG}  uninstall_operator ${COLOR_RESET}Install podinfo-operator on the active cluster."
  echo -e "${COLOR_DEBUG}  unit_test          ${COLOR_RESET}Run unit tests"
  echo -e "${COLOR_DEBUG}  e2e_test           ${COLOR_RESET}Run e2e test on the active cluster."
  echo -e "${COLOR_DEBUG}  cleanup            ${COLOR_RESET}Cleanup the operator and delete the Kind cluster"
}

if [ $# -eq 0 ]; then
  show_help
  exit 1
fi

case "$1" in
"help")
  show_help
  ;;
"create_cluster")
  create_cluster
  ;;
"install_operator")
  install_operator
  ;;
"uninstall_operator")
  uninstall_operator
  ;;
"unit_test")
  unit_test
  ;;
"e2e_test")
  e2e_test
  ;;
"cleanup")
  cleanup
  ;;
*)
  echo "Error: Unknown command '$1'"
  show_help
  exit 1
  ;;
esac
