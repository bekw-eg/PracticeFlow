"""Small, dependency-free Prometheus registry with deliberately safe labels.

The application must expose useful operational signals without turning a
metrics backend into a second database of personal data. Labels are therefore
enumerated and low-cardinality: no identities, emails, filenames, object keys,
tokens, raw URLs, or exception messages are accepted here.
"""
from __future__ import annotations

from collections import defaultdict
from threading import Lock


_HTTP_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 1.5, 3.0, 5.0, 10.0)
_EXPORT_BUCKETS = (1.0, 3.0, 5.0, 10.0, 20.0, 45.0, 90.0, 180.0)
_SAFE_COMPONENTS = {
    "postgres",
    "redis_rate_limit",
    "redis_resource_guard",
    "redis_export_queue",
    "redis_worker_heartbeat",
    "redis_memory",
    "s3",
    "local_storage",
}
_SAFE_LIMIT_REASONS = {
    "login_rate",
    "mfa_rate",
    "upload_rate",
    "upload_quota",
    "export_rate",
    "export_concurrency",
}
_SAFE_MFA_ACTIONS = {"enrollment", "challenge", "recovery", "peer_recovery", "break_glass"}
_SAFE_EXPORT_STATUSES = {"queued", "running", "succeeded", "failed", "timed_out", "cancelled"}
_SAFE_EXPORT_RETRY_REASONS = {"concurrency", "stale_worker", "graceful_shutdown"}
_SAFE_STORAGE_OPERATIONS = {"upload", "download", "delete", "cleanup", "exists", "ping"}
_SAFE_STORAGE_BACKENDS = {"s3", "local"}


def _escape(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"


class ObservabilityMetrics:
    """Thread-safe counters and gauges rendered in Prometheus text format."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._http_requests: dict[tuple[str, str, int, str], int] = defaultdict(int)
        self._http_in_flight: dict[tuple[str, str], int] = defaultdict(int)
        self._http_duration_sum: dict[tuple[str, str], float] = defaultdict(float)
        self._http_duration_count: dict[tuple[str, str], int] = defaultdict(int)
        self._http_duration_buckets: dict[tuple[str, str, float], int] = defaultdict(int)
        self._dependency_checks: dict[tuple[str, str], int] = defaultdict(int)
        self._dependency_up: dict[str, int] = {}
        self._database_errors = 0
        self._database_pool: dict[str, int] = {"size": 0, "checked_out": 0, "overflow": 0, "capacity": 0}
        self._redis_memory: dict[str, int] = {"used": 0, "max": 0}
        self._storage_operations: dict[tuple[str, str, str], int] = defaultdict(int)
        self._storage_latency_sum: dict[tuple[str, str], float] = defaultdict(float)
        self._storage_latency_count: dict[tuple[str, str], int] = defaultdict(int)
        self._mfa_events: dict[tuple[str, str], int] = defaultdict(int)
        self._export_transitions: dict[tuple[str, str], int] = defaultdict(int)
        self._export_duration_sum: dict[tuple[str, str], float] = defaultdict(float)
        self._export_duration_count: dict[tuple[str, str], int] = defaultdict(int)
        self._export_duration_buckets: dict[tuple[str, str, float], int] = defaultdict(int)
        self._export_retries: dict[str, int] = defaultdict(int)
        self._export_stale_recoveries = 0
        self._export_queue_depth = 0
        self._export_jobs_by_status: dict[str, int] = {}
        self._worker_heartbeat_age_seconds = -1.0
        self._worker_heartbeat_count = 0
        self._limit_blocks: dict[str, int] = defaultdict(int)
        self._storage_usage_bytes = 0

    @staticmethod
    def _safe_component(component: str) -> str:
        return component if component in _SAFE_COMPONENTS else "unknown"

    @staticmethod
    def _safe_backend(backend: str) -> str:
        return backend if backend in _SAFE_STORAGE_BACKENDS else "unknown"

    @staticmethod
    def _safe_operation(operation: str) -> str:
        return operation if operation in _SAFE_STORAGE_OPERATIONS else "unknown"

    @staticmethod
    def _safe_result(result: str) -> str:
        return result if result in {"success", "failure"} else "failure"

    @staticmethod
    def _safe_format(export_format: str) -> str:
        return export_format if export_format in {"docx", "pdf"} else "unknown"

    def begin_http_request(self, method: str, route: str) -> None:
        with self._lock:
            self._http_in_flight[(method, route)] += 1

    def observe(self, method: str, route: str, status_code: int, duration_seconds: float) -> None:
        """Compatibility helper for direct callers that do not track in-flight."""
        self.observe_http_request(method, route, status_code, duration_seconds, decrement_in_flight=False)

    def observe_http_request(
        self,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
        *,
        decrement_in_flight: bool = True,
        in_flight_route: str | None = None,
    ) -> None:
        duration = max(0.0, duration_seconds)
        with self._lock:
            if decrement_in_flight:
                key = (method, in_flight_route or route)
                self._http_in_flight[key] = max(0, self._http_in_flight[key] - 1)
            self._http_requests[(method, route, status_code, _status_class(status_code))] += 1
            duration_key = (method, route)
            self._http_duration_sum[duration_key] += duration
            self._http_duration_count[duration_key] += 1
            for bucket in _HTTP_BUCKETS:
                if duration <= bucket:
                    self._http_duration_buckets[(method, route, bucket)] += 1

    def observe_dependency(self, component: str, result: str) -> None:
        component = self._safe_component(component)
        result = self._safe_result(result)
        with self._lock:
            self._dependency_checks[(component, result)] += 1
            self._dependency_up[component] = 1 if result == "success" else 0

    def set_dependency_up(self, component: str, available: bool) -> None:
        with self._lock:
            self._dependency_up[self._safe_component(component)] = 1 if available else 0

    def observe_database_error(self) -> None:
        with self._lock:
            self._database_errors += 1

    def set_database_pool(self, *, size: int, checked_out: int, overflow: int, capacity: int) -> None:
        with self._lock:
            self._database_pool = {
                "size": max(0, size),
                "checked_out": max(0, checked_out),
                "overflow": max(0, overflow),
                "capacity": max(0, capacity),
            }

    def set_redis_memory(self, *, used_bytes: int, max_bytes: int) -> None:
        with self._lock:
            self._redis_memory = {"used": max(0, used_bytes), "max": max(0, max_bytes)}

    def observe_storage_operation(self, backend: str, operation: str, result: str, duration_seconds: float) -> None:
        backend = self._safe_backend(backend)
        operation = self._safe_operation(operation)
        result = self._safe_result(result)
        with self._lock:
            self._storage_operations[(backend, operation, result)] += 1
            self._storage_latency_sum[(backend, operation)] += max(0.0, duration_seconds)
            self._storage_latency_count[(backend, operation)] += 1

    def observe_mfa(self, action: str, result: str) -> None:
        action = action if action in _SAFE_MFA_ACTIONS else "unknown"
        result = self._safe_result(result)
        with self._lock:
            self._mfa_events[(action, result)] += 1

    def observe_export_transition(self, export_format: str, job_status: str) -> None:
        job_status = job_status if job_status in _SAFE_EXPORT_STATUSES else "failed"
        with self._lock:
            self._export_transitions[(self._safe_format(export_format), job_status)] += 1

    def observe_export_duration(self, export_format: str, result: str, duration_seconds: float) -> None:
        export_format = self._safe_format(export_format)
        result = result if result in _SAFE_EXPORT_STATUSES else "failed"
        duration = max(0.0, duration_seconds)
        with self._lock:
            key = (export_format, result)
            self._export_duration_sum[key] += duration
            self._export_duration_count[key] += 1
            for bucket in _EXPORT_BUCKETS:
                if duration <= bucket:
                    self._export_duration_buckets[(export_format, result, bucket)] += 1

    def observe_export_retry(self, reason: str) -> None:
        with self._lock:
            self._export_retries[reason if reason in _SAFE_EXPORT_RETRY_REASONS else "unknown"] += 1

    def observe_export_stale_recovery(self) -> None:
        with self._lock:
            self._export_stale_recoveries += 1

    def set_export_queue_depth(self, value: int) -> None:
        with self._lock:
            self._export_queue_depth = max(0, value)

    def set_export_job_states(self, states: dict[str, int]) -> None:
        with self._lock:
            self._export_jobs_by_status = {state: max(0, int(value)) for state, value in states.items() if state in _SAFE_EXPORT_STATUSES}

    def set_worker_heartbeat(self, age_seconds: float | None, active_workers: int) -> None:
        with self._lock:
            self._worker_heartbeat_age_seconds = -1.0 if age_seconds is None else max(0.0, age_seconds)
            self._worker_heartbeat_count = max(0, active_workers)

    def observe_limit_block(self, reason: str) -> None:
        with self._lock:
            self._limit_blocks[reason if reason in _SAFE_LIMIT_REASONS else "unknown"] += 1

    def set_storage_usage_bytes(self, value: int) -> None:
        with self._lock:
            self._storage_usage_bytes = max(0, value)

    @staticmethod
    def _histogram_lines(name: str, help_text: str, buckets: tuple[float, ...], sums, counts, bucket_counts) -> list[str]:
        lines = [f"# HELP {name} {help_text}", f"# TYPE {name} histogram"]
        for label_key in sorted(set(sums) | set(counts)):
            pairs = (("method", label_key[0]), ("route", label_key[1])) if name.startswith("practiceflow_http") else (("format", label_key[0]), ("result", label_key[1]))
            rendered = ",".join(f'{key}="{_escape(value)}"' for key, value in pairs)
            for bucket in buckets:
                lines.append(f'{name}_bucket{{{rendered},le="{bucket:g}"}} {bucket_counts.get((*label_key, bucket), 0)}')
            lines.append(f'{name}_bucket{{{rendered},le="+Inf"}} {counts.get(label_key, 0)}')
            lines.append(f"{name}_sum{{{rendered}}} {sums.get(label_key, 0.0):.6f}")
            lines.append(f"{name}_count{{{rendered}}} {counts.get(label_key, 0)}")
        return lines

    def render_prometheus(self) -> str:
        with self._lock:
            lines = ["# HELP practiceflow_http_requests_total Total HTTP requests.", "# TYPE practiceflow_http_requests_total counter"]
            for (method, route, status_code, status_class), count in sorted(self._http_requests.items()):
                lines.append("practiceflow_http_requests_total" f'{{method="{_escape(method)}",route="{_escape(route)}",status="{status_code}",status_class="{status_class}"}} {count}')
            lines.extend(self._histogram_lines("practiceflow_http_request_duration_seconds", "HTTP request duration.", _HTTP_BUCKETS, self._http_duration_sum, self._http_duration_count, self._http_duration_buckets))
            lines.extend(["# HELP practiceflow_http_in_flight_requests Current in-flight HTTP requests.", "# TYPE practiceflow_http_in_flight_requests gauge"])
            for (method, route), value in sorted(self._http_in_flight.items()):
                lines.append(f'practiceflow_http_in_flight_requests{{method="{_escape(method)}",route="{_escape(route)}"}} {value}')
            lines.extend(["# HELP practiceflow_dependency_checks_total Dependency checks and operation failures.", "# TYPE practiceflow_dependency_checks_total counter"])
            for (component, result), value in sorted(self._dependency_checks.items()):
                lines.append(f'practiceflow_dependency_checks_total{{component="{component}",result="{result}"}} {value}')
            lines.extend(["# HELP practiceflow_dependency_up Dependency availability, 1 for up.", "# TYPE practiceflow_dependency_up gauge"])
            for component, value in sorted(self._dependency_up.items()):
                lines.append(f'practiceflow_dependency_up{{component="{component}"}} {value}')
            lines.extend(["# HELP practiceflow_database_errors_total SQLAlchemy database errors.", "# TYPE practiceflow_database_errors_total counter", f"practiceflow_database_errors_total {self._database_errors}"])
            lines.extend(["# HELP practiceflow_database_pool_connections SQLAlchemy pool state.", "# TYPE practiceflow_database_pool_connections gauge"])
            for pool_state, value in sorted(self._database_pool.items()):
                lines.append(f'practiceflow_database_pool_connections{{state="{pool_state}"}} {value}')
            lines.extend(["# HELP practiceflow_redis_memory_bytes Redis used and configured max memory.", "# TYPE practiceflow_redis_memory_bytes gauge"])
            for memory_state, value in sorted(self._redis_memory.items()):
                lines.append(f'practiceflow_redis_memory_bytes{{state="{memory_state}"}} {value}')
            lines.extend(["# HELP practiceflow_storage_operations_total Private storage operations.", "# TYPE practiceflow_storage_operations_total counter"])
            for (backend, operation, result), value in sorted(self._storage_operations.items()):
                lines.append(f'practiceflow_storage_operations_total{{backend="{backend}",operation="{operation}",result="{result}"}} {value}')
            lines.extend(["# HELP practiceflow_storage_operation_duration_seconds Storage operation duration.", "# TYPE practiceflow_storage_operation_duration_seconds summary"])
            for (backend, operation), latency_sum in sorted(self._storage_latency_sum.items()):
                label = f'backend="{backend}",operation="{operation}"'
                lines.append(f"practiceflow_storage_operation_duration_seconds_sum{{{label}}} {latency_sum:.6f}")
                lines.append(f"practiceflow_storage_operation_duration_seconds_count{{{label}}} {self._storage_latency_count[(backend, operation)]}")
            lines.extend(["# HELP practiceflow_mfa_events_total MFA lifecycle results.", "# TYPE practiceflow_mfa_events_total counter"])
            for (action, result), value in sorted(self._mfa_events.items()):
                lines.append(f'practiceflow_mfa_events_total{{action="{action}",result="{result}"}} {value}')
            lines.extend(["# HELP practiceflow_export_job_transitions_total Export job state transitions.", "# TYPE practiceflow_export_job_transitions_total counter"])
            for (export_format, job_status), value in sorted(self._export_transitions.items()):
                lines.append(f'practiceflow_export_job_transitions_total{{format="{export_format}",status="{job_status}"}} {value}')
            lines.extend(self._histogram_lines("practiceflow_export_job_duration_seconds", "Completed export job duration.", _EXPORT_BUCKETS, self._export_duration_sum, self._export_duration_count, self._export_duration_buckets))
            lines.extend(["# HELP practiceflow_export_jobs Current export jobs by status.", "# TYPE practiceflow_export_jobs gauge"])
            for job_status, value in sorted(self._export_jobs_by_status.items()):
                lines.append(f'practiceflow_export_jobs{{status="{job_status}"}} {value}')
            lines.extend(["# HELP practiceflow_export_queue_depth Current export queue depth.", "# TYPE practiceflow_export_queue_depth gauge", f"practiceflow_export_queue_depth {self._export_queue_depth}", "# HELP practiceflow_export_retries_total Export requeues/retries.", "# TYPE practiceflow_export_retries_total counter"])
            for reason, value in sorted(self._export_retries.items()):
                lines.append(f'practiceflow_export_retries_total{{reason="{reason}"}} {value}')
            lines.extend(["# HELP practiceflow_export_stale_worker_recoveries_total Exports recovered from stale workers.", "# TYPE practiceflow_export_stale_worker_recoveries_total counter", f"practiceflow_export_stale_worker_recoveries_total {self._export_stale_recoveries}"])
            lines.extend(["# HELP practiceflow_export_worker_heartbeat_age_seconds Age of newest export-worker heartbeat; -1 means no heartbeat.", "# TYPE practiceflow_export_worker_heartbeat_age_seconds gauge", f"practiceflow_export_worker_heartbeat_age_seconds {self._worker_heartbeat_age_seconds:.6f}", "# HELP practiceflow_export_worker_active Active workers seen within heartbeat TTL.", "# TYPE practiceflow_export_worker_active gauge", f"practiceflow_export_worker_active {self._worker_heartbeat_count}", "# HELP practiceflow_limit_blocks_total Rate, quota, and concurrency blocks.", "# TYPE practiceflow_limit_blocks_total counter"])
            for reason, value in sorted(self._limit_blocks.items()):
                lines.append(f'practiceflow_limit_blocks_total{{reason="{reason}"}} {value}')
            lines.extend(["# HELP practiceflow_storage_usage_bytes Aggregate tracked private-file storage usage.", "# TYPE practiceflow_storage_usage_bytes gauge", f'practiceflow_storage_usage_bytes{{scope="all_organizations"}} {self._storage_usage_bytes}'])
        return "\n".join(lines) + "\n"


# Keep the former public name for small integrations and tests.
HttpMetrics = ObservabilityMetrics
metrics = ObservabilityMetrics()
http_metrics = metrics
