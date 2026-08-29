#!/usr/bin/env python3
"""Validate reviewed Compose capacity and recovery invariants without secrets."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def load(relative_path: str) -> dict:
    with (ROOT / relative_path).open(encoding="utf-8") as stream:
        return yaml.safe_load(stream) or {}


def assert_resources(errors: list[str], source: str, service_name: str, service: dict) -> None:
    resources = service.get("deploy", {}).get("resources", {})
    for tier in ("limits", "reservations"):
        values = resources.get(tier, {})
        if not values.get("cpus") or not values.get("memory"):
            fail(errors, f"{source}:{service_name} must define {tier}.cpus and {tier}.memory")


def assert_healthcheck(errors: list[str], source: str, service_name: str, service: dict) -> None:
    if not service.get("healthcheck"):
        fail(errors, f"{source}:{service_name} must define a healthcheck")


def main() -> int:
    errors: list[str] = []
    production_source = "docker-compose.prod.yml"
    production = load(production_source)
    prod_services = production.get("services", {})
    for service_name in ("postgres", "redis", "backend", "export-worker", "frontend"):
        service = prod_services.get(service_name)
        if not service:
            fail(errors, f"{production_source}:{service_name} is required")
            continue
        assert_resources(errors, production_source, service_name, service)
        assert_healthcheck(errors, production_source, service_name, service)
        if service.get("restart") != "unless-stopped":
            fail(errors, f"{production_source}:{service_name} must use restart: unless-stopped")
        if service.get("container_name"):
            fail(errors, f"{production_source}:{service_name} must not set container_name; it breaks isolated project names")

    postgres_command = " ".join(str(part) for part in prod_services.get("postgres", {}).get("command", []))
    if "max_connections=" not in postgres_command:
        fail(errors, f"{production_source}:postgres must set max_connections")
    redis_command = " ".join(str(part) for part in prod_services.get("redis", {}).get("command", []))
    if "--maxmemory" not in redis_command or "--maxmemory-policy noeviction" not in redis_command:
        fail(errors, f"{production_source}:redis must use bounded noeviction memory policy")
    worker_dependencies = prod_services.get("export-worker", {}).get("depends_on", {})
    for dependency in ("backend", "postgres", "redis"):
        if worker_dependencies.get(dependency, {}).get("condition") != "service_healthy":
            fail(errors, f"{production_source}:export-worker must wait for healthy {dependency}")
    for variable in (
        "DATABASE_POOL_SIZE",
        "DATABASE_MAX_OVERFLOW",
        "DATABASE_POOL_TIMEOUT_SECONDS",
        "DATABASE_POOL_RECYCLE_SECONDS",
        "WORKER_DATABASE_POOL_SIZE",
        "WORKER_DATABASE_MAX_OVERFLOW",
        "WORKER_DATABASE_POOL_TIMEOUT_SECONDS",
        "WORKER_DATABASE_POOL_RECYCLE_SECONDS",
    ):
        for service_name in ("backend", "export-worker"):
            if variable not in prod_services.get(service_name, {}).get("environment", {}):
                fail(errors, f"{production_source}:{service_name} must pass {variable}")

    caddy_source = "deployment/caddy/docker-compose.caddy.yml"
    caddy = load(caddy_source).get("services", {}).get("caddy", {})
    assert_resources(errors, caddy_source, "caddy", caddy)
    assert_healthcheck(errors, caddy_source, "caddy", caddy)
    if caddy.get("restart") != "unless-stopped":
        fail(errors, f"{caddy_source}:caddy must use restart: unless-stopped")

    e2e_source = "docker-compose.e2e.yml"
    e2e_services = load(e2e_source).get("services", {})
    for service_name in ("postgres", "redis", "minio", "minio-init", "backend", "export-worker", "frontend"):
        service = e2e_services.get(service_name)
        if not service:
            fail(errors, f"{e2e_source}:{service_name} is required")
            continue
        assert_resources(errors, e2e_source, service_name, service)
        if service_name != "minio-init":
            assert_healthcheck(errors, e2e_source, service_name, service)
        if service.get("container_name"):
            fail(errors, f"{e2e_source}:{service_name} must not set container_name; it breaks isolated project names")
    e2e_redis_command = " ".join(str(part) for part in e2e_services.get("redis", {}).get("command", []))
    if "--maxmemory-policy noeviction" not in e2e_redis_command:
        fail(errors, f"{e2e_source}:redis must use noeviction")

    test_source = "docker-compose.test.yml"
    test_services = load(test_source).get("services", {})
    for service_name in ("test-db", "migration-db", "backend-test"):
        service = test_services.get(service_name)
        if not service:
            fail(errors, f"{test_source}:{service_name} is required")
            continue
        assert_resources(errors, test_source, service_name, service)
        if service.get("container_name"):
            fail(errors, f"{test_source}:{service_name} must not set container_name; it breaks isolated project names")

    alert_source = "deployment/observability/prometheus-alerts.yml"
    alert_rules = load(alert_source).get("groups", [{}])[0].get("rules", [])
    alert_names = {rule.get("alert") for rule in alert_rules}
    for alert_name in (
        "PracticeFlowDatabasePoolNearExhaustion",
        "PracticeFlowRedisMemoryNearLimit",
        "PracticeFlowExportQueueBacklog",
        "PracticeFlowStorageErrorRate",
        "PracticeFlowContainerMemoryPressure",
        "PracticeFlowContainerCpuPressure",
    ):
        if alert_name not in alert_names:
            fail(errors, f"{alert_source} must define {alert_name}")

    if errors:
        print("Capacity configuration policy failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print("Capacity configuration policy passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
