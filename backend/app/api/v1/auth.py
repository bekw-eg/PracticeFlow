import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.pagination import PaginationParams, set_pagination_headers
from app.core.config import settings
from app.db.session import get_db
from app.dependencies.auth import RequestContext, get_current_context
from app.rate_limit.base import LoginRateLimiter
from app.rate_limit.dependencies import get_login_rate_limiter, get_mfa_rate_limiter
from app.repositories.user_repository import UserRepository
from app.schemas.access import CompleteAccessRequest, OrganizationChoice, SwitchOrganizationRequest
from app.schemas.auth import CurrentUserResponse, LoginRequest, ProductFeatures, TokenResponse
from app.schemas.mfa import (
    MfaBreakGlassStartRequest,
    MfaChallengeResponse,
    MfaCodeRequest,
    MfaEnrollmentCompleteResponse,
    MfaEnrollmentStartRequest,
    MfaEnrollmentStartResponse,
    MfaPeerRecoveryRequest,
    MfaPeerRecoveryStatus,
    MfaRecoveryRequest,
)
from app.services.access_link_service import AccessLinkService
from app.services.auth_service import AuthService
from app.services.mfa_service import MfaService
from app.observability.metrics import metrics

router = APIRouter(prefix="/auth", tags=["auth"])
_MFA_COOKIE_NAME = "practiceflow_mfa_challenge"

def _login_rate_key(request: Request, email: str) -> str:
    remote = request.client.host if request.client else "unknown"
    normalized = f"{remote}:{email.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _check_login_rate(limiter: LoginRateLimiter, key: str, reason: str = "login_rate") -> None:
    if limiter.is_blocked(key):
        metrics.observe_limit_block(reason)
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again in a few minutes.")


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path=f"{settings.API_V1_PREFIX}/auth",
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
    response.headers["Cache-Control"] = "no-store"


def _set_mfa_cookie(response: Response, value: str) -> None:
    response.set_cookie(
        key=_MFA_COOKIE_NAME,
        value=value,
        max_age=settings.MFA_CHALLENGE_EXPIRE_MINUTES * 60,
        path=f"{settings.API_V1_PREFIX}/auth/mfa",
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
    response.headers["Cache-Control"] = "no-store"


def _clear_mfa_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_MFA_COOKIE_NAME,
        path=f"{settings.API_V1_PREFIX}/auth/mfa",
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=f"{settings.API_V1_PREFIX}/auth",
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )


@router.post("/login", response_model=TokenResponse | MfaChallengeResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    limiter: LoginRateLimiter = Depends(get_login_rate_limiter),
) -> TokenResponse | MfaChallengeResponse:
    rate_key = _login_rate_key(request, payload.email)
    _check_login_rate(limiter, rate_key)
    try:
        result = AuthService(db).login(payload.email, payload.password, payload.organization_slug)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            limiter.record_failure(rate_key)
        raise
    limiter.reset(rate_key)
    if result.mfa_challenge:
        _set_mfa_cookie(response, result.mfa_challenge.cookie_value)
        response.status_code = status.HTTP_202_ACCEPTED
        return MfaChallengeResponse(
            status=result.mfa_challenge.status,
            challenge_id=result.mfa_challenge.challenge.id,
            expires_at=result.mfa_challenge.challenge.expires_at,
        )
    assert result.refresh_token is not None and result.access_token is not None
    _set_refresh_cookie(response, result.refresh_token)
    return TokenResponse(access_token=result.access_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    current = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not current:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh cookie is missing")
    access_token, refresh_token = AuthService(db).refresh(current)
    _set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    current = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if current:
        AuthService(db).logout(current)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=CurrentUserResponse)
def me(ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> CurrentUserResponse:
    user = UserRepository(db).get_by_id(ctx.user_id)
    return CurrentUserResponse(
        user_id=ctx.user_id,
        organization_id=ctx.organization_id,
        full_name=user.full_name,
        email=user.email,
        role=ctx.role,
        features=ProductFeatures(document_check_enabled=settings.DOCUMENT_CHECK_ENABLED, legacy_document_editor_enabled=settings.LEGACY_DOCUMENT_EDITOR_ENABLED),
    )


@router.get("/organizations", response_model=list[OrganizationChoice])
def organizations(response: Response, page: PaginationParams = Depends(), ctx: RequestContext = Depends(get_current_context), db: Session = Depends(get_db)) -> list[OrganizationChoice]:
    service = AuthService(db)
    memberships = service.list_organizations(ctx.user_id, page.offset, page.limit)
    set_pagination_headers(response, page, total=service.count_organizations(ctx.user_id), returned=len(memberships))
    return [OrganizationChoice(id=item.organization_id, name=item.organization.name, slug=item.organization.slug, role=item.role.name) for item in memberships]


@router.post("/switch-organization", response_model=TokenResponse | MfaChallengeResponse)
def switch_organization(
    payload: SwitchOrganizationRequest,
    response: Response,
    ctx: RequestContext = Depends(get_current_context),
    db: Session = Depends(get_db),
) -> TokenResponse | MfaChallengeResponse:
    result = AuthService(db).switch_organization(ctx.user_id, payload.organization_id)
    if result.mfa_challenge:
        _set_mfa_cookie(response, result.mfa_challenge.cookie_value)
        response.status_code = status.HTTP_202_ACCEPTED
        return MfaChallengeResponse(
            status=result.mfa_challenge.status,
            challenge_id=result.mfa_challenge.challenge.id,
            expires_at=result.mfa_challenge.challenge.expires_at,
        )
    assert result.refresh_token is not None and result.access_token is not None
    _set_refresh_cookie(response, result.refresh_token)
    return TokenResponse(access_token=result.access_token)


def _mfa_rate_key(request: Request, challenge_id: str) -> str:
    remote = request.client.host if request.client else "unknown"
    return hashlib.sha256(f"mfa:{remote}:{challenge_id}".encode()).hexdigest()


def _mfa_failure(limiter: LoginRateLimiter, rate_key: str, operation):
    _check_login_rate(limiter, rate_key, "mfa_rate")
    try:
        result = operation()
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            limiter.record_failure(rate_key)
        raise
    limiter.reset(rate_key)
    return result


@router.post("/mfa/enrollment/start", response_model=MfaEnrollmentStartResponse)
def mfa_enrollment_start(
    payload: MfaEnrollmentStartRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> MfaEnrollmentStartResponse:
    challenge, manual_key, qr_data_url = MfaService(db).start_enrollment(
        payload.challenge_id, request.cookies.get(_MFA_COOKIE_NAME)
    )
    return MfaEnrollmentStartResponse(
        challenge_id=challenge.id,
        expires_at=challenge.expires_at,
        manual_key=manual_key,
        qr_data_url=qr_data_url,
    )


@router.post("/mfa/enrollment/verify", response_model=MfaEnrollmentCompleteResponse)
def mfa_enrollment_verify(
    payload: MfaCodeRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    limiter: LoginRateLimiter = Depends(get_mfa_rate_limiter),
) -> MfaEnrollmentCompleteResponse:
    access, refresh, recovery_codes = _mfa_failure(
        limiter,
        _mfa_rate_key(request, str(payload.challenge_id)),
        lambda: MfaService(db).complete_enrollment(payload.challenge_id, request.cookies.get(_MFA_COOKIE_NAME), payload.code),
    )
    _set_refresh_cookie(response, refresh)
    _clear_mfa_cookie(response)
    return MfaEnrollmentCompleteResponse(access_token=access, recovery_codes=recovery_codes)


@router.post("/mfa/verify", response_model=TokenResponse)
def mfa_verify(
    payload: MfaCodeRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    limiter: LoginRateLimiter = Depends(get_mfa_rate_limiter),
) -> TokenResponse:
    access, refresh = _mfa_failure(
        limiter,
        _mfa_rate_key(request, str(payload.challenge_id)),
        lambda: MfaService(db).verify(payload.challenge_id, request.cookies.get(_MFA_COOKIE_NAME), payload.code),
    )
    _set_refresh_cookie(response, refresh)
    _clear_mfa_cookie(response)
    return TokenResponse(access_token=access)


@router.post("/mfa/recovery/verify", response_model=MfaChallengeResponse)
def mfa_recovery_verify(
    payload: MfaRecoveryRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    limiter: LoginRateLimiter = Depends(get_mfa_rate_limiter),
) -> MfaChallengeResponse:
    created = _mfa_failure(
        limiter,
        _mfa_rate_key(request, str(payload.challenge_id)),
        lambda: MfaService(db).use_recovery_code(payload.challenge_id, request.cookies.get(_MFA_COOKIE_NAME), payload.recovery_code),
    )
    _set_mfa_cookie(response, created.cookie_value)
    return MfaChallengeResponse(status=created.status, challenge_id=created.challenge.id, expires_at=created.challenge.expires_at)


@router.post("/mfa/recovery/peer-request", response_model=MfaPeerRecoveryStatus)
def mfa_peer_recovery_request(
    payload: MfaPeerRecoveryRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> MfaPeerRecoveryStatus:
    challenge = MfaService(db).request_peer_recovery(payload.challenge_id, request.cookies.get(_MFA_COOKIE_NAME))
    return MfaPeerRecoveryStatus(status="MFA_RECOVERY_PENDING", challenge_id=challenge.id, expires_at=challenge.expires_at, approved=False)


@router.get("/mfa/recovery/peer-status/{challenge_id}", response_model=MfaPeerRecoveryStatus)
def mfa_peer_recovery_status(challenge_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> MfaPeerRecoveryStatus:
    challenge = MfaService(db).peer_recovery_status(challenge_id, request.cookies.get(_MFA_COOKIE_NAME))
    return MfaPeerRecoveryStatus(
        status="MFA_ENROLLMENT_REQUIRED" if challenge.approved_at else "MFA_RECOVERY_PENDING",
        challenge_id=challenge.id,
        expires_at=challenge.expires_at,
        approved=challenge.approved_at is not None,
    )


@router.post("/mfa/recovery/complete-peer", response_model=MfaChallengeResponse)
def mfa_complete_peer_recovery(
    payload: MfaPeerRecoveryRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> MfaChallengeResponse:
    created = MfaService(db).complete_peer_recovery(payload.challenge_id, request.cookies.get(_MFA_COOKIE_NAME))
    _set_mfa_cookie(response, created.cookie_value)
    return MfaChallengeResponse(status=created.status, challenge_id=created.challenge.id, expires_at=created.challenge.expires_at)


@router.post("/mfa/break-glass/start", response_model=MfaChallengeResponse)
def mfa_break_glass_start(
    payload: MfaBreakGlassStartRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> MfaChallengeResponse:
    created = MfaService(db).start_break_glass(payload.challenge_id, payload.enrollment_code)
    _set_mfa_cookie(response, created.cookie_value)
    return MfaChallengeResponse(status=created.status, challenge_id=created.challenge.id, expires_at=created.challenge.expires_at)


@router.post("/complete-access", status_code=204)
def complete_access(payload: CompleteAccessRequest, db: Session = Depends(get_db)) -> None:
    AccessLinkService(db).complete(payload.token, payload.password)
