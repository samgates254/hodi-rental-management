"""Safaricom Daraja HTTP client.

This module speaks Daraja. It does not create HODI Payment or ledger rows.
Secrets, access tokens, and STK passwords must never be logged.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings

logger = logging.getLogger(__name__)

NAIROBI = ZoneInfo('Africa/Nairobi')
OAUTH_PATH = '/oauth/v1/generate'
STK_PATH = '/mpesa/stkpush/v1/processrequest'


class MpesaError(Exception):
    """Daraja provider error. Messages must never include secrets."""


class MpesaAuthError(MpesaError):
    """OAuth failed: invalid credentials or a malformed token response."""


class MpesaTimeoutError(MpesaError):
    """Daraja request timed out."""


class MpesaHTTPError(MpesaError):
    """Non-success HTTP from Daraja."""


class MpesaResponseError(MpesaError):
    """Daraja returned a body that could not be used."""


class MpesaConfigError(MpesaError):
    """Required Daraja settings are missing or invalid."""


def daraja_timestamp(moment: datetime | None = None) -> str:
    moment = moment or datetime.now(NAIROBI)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=NAIROBI)
    else:
        moment = moment.astimezone(NAIROBI)
    return moment.strftime('%Y%m%d%H%M%S')


def stk_password(shortcode: str, passkey: str, timestamp: str) -> str:
    raw = f'{shortcode}{passkey}{timestamp}'.encode('utf-8')
    return base64.b64encode(raw).decode('ascii')


def _request_path(request: urllib.request.Request) -> str:
    return urllib.parse.urlparse(request.full_url).path


@dataclass(frozen=True)
class StkPushResult:
    merchant_request_id: str
    checkout_request_id: str
    response_code: str
    response_description: str
    customer_message: str

    @property
    def accepted(self) -> bool:
        return self.response_code == '0'


class MpesaClient:
    def __init__(
        self,
        *,
        base_url: str,
        consumer_key: str,
        consumer_secret: str,
        shortcode: str,
        passkey: str,
        callback_url: str,
        timeout_seconds: int = 30,
        transaction_type: str = 'CustomerPayBillOnline',
        urlopen=None,
    ):
        self.base_url = (base_url or '').rstrip('/')
        self.consumer_key = consumer_key or ''
        self.consumer_secret = consumer_secret or ''
        self.shortcode = shortcode or ''
        self.passkey = passkey or ''
        self.callback_url = callback_url or ''
        self.timeout_seconds = timeout_seconds
        self.transaction_type = transaction_type or 'CustomerPayBillOnline'
        self._urlopen = urlopen or urllib.request.urlopen

    @classmethod
    def from_settings(cls, **overrides):
        kwargs = {
            'base_url': settings.MPESA_BASE_URL,
            'consumer_key': settings.MPESA_CONSUMER_KEY,
            'consumer_secret': settings.MPESA_CONSUMER_SECRET,
            'shortcode': settings.MPESA_SHORTCODE,
            'passkey': settings.MPESA_PASSKEY,
            'callback_url': settings.MPESA_CALLBACK_URL,
            'timeout_seconds': settings.MPESA_TIMEOUT_SECONDS,
            'transaction_type': settings.MPESA_TRANSACTION_TYPE,
        }
        kwargs.update(overrides)
        return cls(**kwargs)

    def require_configured(self):
        missing = []
        if not self.consumer_key:
            missing.append('MPESA_CONSUMER_KEY')
        if not self.consumer_secret:
            missing.append('MPESA_CONSUMER_SECRET')
        if not self.shortcode:
            missing.append('MPESA_SHORTCODE')
        if not self.passkey:
            missing.append('MPESA_PASSKEY')
        if not self.callback_url:
            missing.append('MPESA_CALLBACK_URL')
        if missing:
            logger.error('M-Pesa is not configured: missing %s', ', '.join(missing))
            raise MpesaConfigError('M-Pesa is not configured.')
        if not self.callback_url.lower().startswith('https://'):
            raise MpesaConfigError('MPESA_CALLBACK_URL must use HTTPS.')
        if not self.base_url.lower().startswith('https://'):
            raise MpesaConfigError('MPESA_BASE_URL must use HTTPS.')

    def get_access_token(self) -> str:
        self.require_configured()
        query = urllib.parse.urlencode({'grant_type': 'client_credentials'})
        url = f'{self.base_url}{OAUTH_PATH}?{query}'
        basic = base64.b64encode(
            f'{self.consumer_key}:{self.consumer_secret}'.encode('utf-8')
        ).decode('ascii')
        request = urllib.request.Request(
            url,
            method='GET',
            headers={
                'Authorization': f'Basic {basic}',
                'Accept': 'application/json',
            },
        )
        logger.info('Daraja OAuth request path=%s', OAUTH_PATH)
        payload = self._json_request(request)
        access_token = payload.get('access_token')
        if not isinstance(access_token, str) or not access_token.strip():
            raise MpesaResponseError('Daraja OAuth response did not include an access token.')
        return access_token.strip()

    def stk_push(
        self,
        *,
        phone_number: str,
        amount_kes: int,
        account_reference: str,
        transaction_desc: str,
        access_token: str | None = None,
        timestamp: str | None = None,
    ) -> StkPushResult:
        self.require_configured()
        if isinstance(amount_kes, bool) or not isinstance(amount_kes, int) or amount_kes <= 0:
            raise MpesaError('STK amount must be a positive whole number of Kenyan shillings.')
        stamp = timestamp or daraja_timestamp()
        password = stk_password(self.shortcode, self.passkey, stamp)
        token = access_token or self.get_access_token()
        body = {
            'BusinessShortCode': self.shortcode,
            'Password': password,
            'Timestamp': stamp,
            'TransactionType': self.transaction_type,
            'Amount': amount_kes,
            'PartyA': phone_number,
            'PartyB': self.shortcode,
            'PhoneNumber': phone_number,
            'CallBackURL': self.callback_url,
            'AccountReference': (account_reference or 'RENT')[:12],
            'TransactionDesc': (transaction_desc or 'Rent payment')[:13],
        }
        request = urllib.request.Request(
            f'{self.base_url}{STK_PATH}',
            data=json.dumps(body).encode('utf-8'),
            method='POST',
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
        )
        logger.info('Daraja STK Push request path=%s amount_kes=%s', STK_PATH, amount_kes)
        payload = self._json_request(request)
        response_code = str(payload.get('ResponseCode', '')).strip()
        if response_code == '':
            raise MpesaResponseError('Daraja STK response did not include ResponseCode.')
        return StkPushResult(
            merchant_request_id=str(payload.get('MerchantRequestID') or '').strip(),
            checkout_request_id=str(payload.get('CheckoutRequestID') or '').strip(),
            response_code=response_code,
            response_description=str(payload.get('ResponseDescription') or ''),
            customer_message=str(payload.get('CustomerMessage') or ''),
        )

    def _json_request(self, request: urllib.request.Request) -> dict:
        path = _request_path(request)
        try:
            with self._urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
                status = getattr(response, 'status', None) or response.getcode()
        except TimeoutError as error:
            logger.error('Daraja request timed out path=%s', path)
            raise MpesaTimeoutError('Daraja request timed out.') from error
        except urllib.error.HTTPError as error:
            logger.error('Daraja HTTP error path=%s status=%s', path, error.code)
            if error.code in (400, 401, 403) and path == OAUTH_PATH:
                raise MpesaAuthError('Daraja rejected the OAuth credentials.') from error
            raise MpesaHTTPError('Daraja request failed.') from error
        except urllib.error.URLError as error:
            reason = error.reason
            timed_out = isinstance(reason, TimeoutError) or 'timed out' in str(reason).lower()
            if timed_out:
                logger.error('Daraja request timed out path=%s', path)
                raise MpesaTimeoutError('Daraja request timed out.') from error
            logger.error('Daraja connection error path=%s', path)
            raise MpesaHTTPError('Daraja request failed.') from error

        if status and int(status) >= 400:
            logger.error('Daraja HTTP error path=%s status=%s', path, status)
            if int(status) in (400, 401, 403) and path == OAUTH_PATH:
                raise MpesaAuthError('Daraja rejected the OAuth credentials.')
            raise MpesaHTTPError('Daraja request failed.')

        try:
            payload = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as error:
            raise MpesaResponseError('Daraja returned a malformed JSON response.') from error
        if not isinstance(payload, dict):
            raise MpesaResponseError('Daraja returned a malformed JSON response.')
        if 'access_token' not in payload and (
            'errorCode' in payload or 'errorMessage' in payload
        ):
            if path == OAUTH_PATH:
                raise MpesaAuthError('Daraja rejected the OAuth credentials.')
            raise MpesaResponseError('Daraja returned an error response.')
        return payload
