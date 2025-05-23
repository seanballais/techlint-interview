from datetime import datetime, timedelta, timezone
from enum import Enum

import jwt
from sqlalchemy import Select
from sqlmodel import select, Session

from .config import settings
from .db import get_session
from .models import BlacklistedToken

SECRET_KEY: str = settings.jwt_token_secret
JWT_ALGORITHM: str = 'HS256'


class TokenType(Enum):
    ACCESS_TOKEN = 'access_token'
    REFRESH_TOKEN = 'refresh_token'


class InvalidAccessTokenError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


class InvalidTokenError(Exception):
    pass


def create_access_token(data: dict) -> str:
    return _create_auth_jwt_token(data,
                                  TokenType.ACCESS_TOKEN,
                                  settings.access_token_minutes_ttl)


def create_refresh_token(data: dict) -> str:
    return _create_auth_jwt_token(data,
                                  TokenType.REFRESH_TOKEN,
                                  settings.refresh_token_minutes_ttl)


def is_token_well_formed(token: str) -> bool:
    # Does not check if the token is still valid, however.
    try:
        # Just here to validate a token.
        jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        # No problem with this one. We won't need to blacklist the access
        # token then.
        pass
    except jwt.InvalidTokenError:
        return False

    return True


def validate_access_token(token: str, session: Session | None = None) -> dict:
    if session is None:
        session = next(get_session())

    try:
        payload: dict = validate_token(token, TokenType.ACCESS_TOKEN, session)
    except InvalidTokenError:
        raise InvalidAccessTokenError()

    return payload


def validate_refresh_token(token: str, session: Session | None = None) -> dict:
    if session is None:
        session = next(get_session())

    try:
        payload: dict = validate_token(token, TokenType.REFRESH_TOKEN, session)
    except InvalidTokenError:
        raise InvalidRefreshTokenError()

    return payload


def validate_token(token: str, token_type: TokenType,
                   session: Session | None = None) -> dict:
    if session is None:
        session = next(get_session())

    try:
        payload: dict = jwt.decode(token, SECRET_KEY,
                                   algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise InvalidTokenError()
    except jwt.InvalidTokenError:
        raise InvalidTokenError()

    if ('token_type' not in payload or 'data' not in payload
            or payload['token_type'] != token_type.value):
        raise InvalidTokenError()

    # Check if the token is not a blacklisted token.
    statement: Select = (
        select(BlacklistedToken).where(BlacklistedToken.token == token)
    )
    token_is_blacklisted: bool = bool(session.exec(statement).first())

    if token_is_blacklisted:
        raise InvalidTokenError()

    return payload


def create_jwt_token(data: dict,
                     token_type: TokenType | None = None,
                     expires_delta: timedelta | None = None) -> str:
    # Taken from:
    #   https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#handle-jwt-tokens
    payload: dict = {
        'data': data
    }

    if token_type:
        payload.update({'token_type': token_type.value})

    if expires_delta:
        expire: datetime = datetime.now(timezone.utc) + expires_delta
    else:
        expire: datetime = datetime.now(timezone.utc) + timedelta(minutes=15)

    payload.update({'exp': expire})

    encoded_jwt = jwt.encode(payload,
                             settings.jwt_token_secret,
                             algorithm=JWT_ALGORITHM)

    return encoded_jwt


def _create_auth_jwt_token(data: dict, token_type: TokenType, ttl: int) -> str:
    # TTL is in minutes.
    token_data: dict = data.copy()
    expires_delta: timedelta = timedelta(minutes=ttl)

    return create_jwt_token(token_data, token_type, expires_delta)
