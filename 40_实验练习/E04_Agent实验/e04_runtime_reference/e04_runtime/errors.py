class RuntimeReferenceError(Exception):
    code = "runtime_reference_error"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.code)


class InvalidContract(RuntimeReferenceError):
    code = "invalid_contract"


class UnknownTool(RuntimeReferenceError):
    code = "tool_not_allowed"


class PermissionDenied(RuntimeReferenceError):
    code = "permission_denied"


class UnsafeEgressTarget(PermissionDenied):
    code = "unsafe_egress_target"


class UnsafePathTarget(PermissionDenied):
    code = "unsafe_path_target"


class InvalidToolOutput(RuntimeReferenceError):
    code = "invalid_tool_output"


class ToolTimeout(RuntimeReferenceError):
    code = "tool_timeout"


class DeadlineExceeded(RuntimeReferenceError):
    code = "task_deadline_exceeded"


class MissingIdempotencyKey(RuntimeReferenceError):
    code = "missing_idempotency_key"


class IdempotencyConflict(RuntimeReferenceError):
    code = "idempotency_conflict"


class NotFound(RuntimeReferenceError):
    code = "not_found"


class VersionConflict(RuntimeReferenceError):
    code = "version_conflict"


class InvalidTransition(RuntimeReferenceError):
    code = "invalid_transition"


class TaskCancelled(RuntimeReferenceError):
    code = "task_cancelled"


class ApprovalTargetMismatch(RuntimeReferenceError):
    code = "approval_target_mismatch"


class ApprovalExpired(RuntimeReferenceError):
    code = "approval_expired"


class DuplicateDecision(RuntimeReferenceError):
    code = "approval_already_decided"


class StaleClaim(RuntimeReferenceError):
    code = "stale_claim"
