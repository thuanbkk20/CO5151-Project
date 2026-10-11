"""Authorization — the ONLY place that decides whose record a tool call may read.

Rules
- Every call must carry a valid session token (UNAUTHENTICATED otherwise).
- The caller's role must be allowed by the tool's ToolSpec (FORBIDDEN otherwise).
- A student always reads their own record: the target comes from the token, never from arguments.
- An advisor may read only students listed in the token's `advisees` claim. The check runs before
  any lookup, so a denied call cannot reveal whether that MSSV exists.
"""

from co5151_contracts import ErrorCode, Role, SessionClaims, ToolError, ToolSpec

from .auth import AuthError, TokenSigner

DENY_OTHER = "Không có quyền truy cập hồ sơ sinh viên khác."


def authenticate(signer: TokenSigner, token: str | None) -> SessionClaims:
    if not token:
        raise ToolError(ErrorCode.UNAUTHENTICATED, "Chưa đăng nhập. Hãy đăng nhập để tra cứu hồ sơ cá nhân.")
    try:
        return signer.verify(token)
    except AuthError as e:
        raise ToolError(ErrorCode.UNAUTHENTICATED, f"Phiên đăng nhập không hợp lệ: {e}.") from None


def resolve_target(claims: SessionClaims, spec: ToolSpec, requested_student_id: str | None = None) -> str:
    """Return the MSSV this call is allowed to read, or raise FORBIDDEN."""
    if claims.role not in spec.roles:
        hint = " Tài khoản cố vấn hãy dùng get_advisee_summary." if claims.role is Role.ADVISOR else ""
        raise ToolError(ErrorCode.FORBIDDEN, f"Tài khoản không được dùng tool {spec.name}.{hint}")
    if claims.role is Role.STUDENT:
        if requested_student_id not in (None, claims.student_id):
            raise ToolError(ErrorCode.FORBIDDEN, DENY_OTHER)
        return claims.student_id
    if requested_student_id is None or requested_student_id not in claims.advisees:
        raise ToolError(ErrorCode.FORBIDDEN, DENY_OTHER)
    return requested_student_id
