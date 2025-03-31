from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
import jwt
import requests
from requests import Response

from .schema import (RegistrationData, LoginData, LogoutData, UsersData,
                     AccessTokenValidationData, TokenRefreshData, AuditData)

router: APIRouter = APIRouter()

AUTH_SERVICE_URL: str = 'http://auth:8080'
IP_SERVICE_URL: str = 'http://ip:8080'


@router.put('/register')
async def register(data: RegistrationData) -> dict:
    url: str = f'{AUTH_SERVICE_URL}/register'

    request_data: dict = {
        'username': data.username,
        'password1': data.password1,
        'password2': data.password2
    }

    resp: Response = requests.put(url, json=request_data)

    return resp.json()
