"""Safaricom Daraja HTTP client.

This module speaks Daraja. It does not create HODI Payment or ledger rows.
Secrets, access tokens, and STK passwords must never be logged.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from common.rental_dates import RENTAL_BUSINESS_TIME_ZONE as NAIROBI

logger = logging.getLogger(__name__)

OAUTH_PATH = '/oauth/v1/generate'
STK_PATH = '/mpesa/stkpush/v1/processrequest'
STK_QUERY_PATH = '/mpesa/stkpushquery/v1/query'


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
        callback_auth_token: str = '',
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
        self.callback_auth_token = callback_auth_token or ''
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
            'callback_auth_token': settings.MPESA_CALLBACK_AUTH_TOKEN,
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
        if not self.callback_auth_token:
            missing.append('MPESA_CALLBACK_AUTH_TOKEN')
        if missing:
            logger.error('M-Pesa is not configured: missing %s', ', '.join(missing))
            raise MpesaConfigError('M-Pesa is not configured.')
        if str(self.shortcode).strip() != self.shortcode or not self.shortcode.isdigit():
            raise MpesaConfigError('M-Pesa shortcode configuration is invalid.')
        try:
            callback = urlsplit(self.callback_url)
        except ValueError as error:
            raise MpesaConfigError('MPESA_CALLBACK_URL must be a valid public HTTPS URL.') from error
        if (callback.scheme.lower() != 'https' or not callback.hostname or callback.username
                or callback.password or callback.query or callback.fragment):
            raise MpesaConfigError('MPESA_CALLBACK_URL must be a valid public HTTPS URL.')
        if self.callback_auth_token not in callback.path.split('/'):
            raise MpesaConfigError('MPESA_CALLBACK_URL must include the configured callback token path segment.')
        if not self.callback_url.lower().startswith('https://'):
            raise MpesaConfigError('MPESA_CALLBACK_URL must use HTTPS.')
        if not self.base_url.lower().startswith('https://'):
            raise MpesaConfigError('MPESA_BASE_URL must use HTTPS.')
        if self.transaction_type not in {'CustomerPayBillOnline', 'CustomerBuyGoodsOnline'}:
            raise MpesaConfigError('M-Pesa transaction type configuration is invalid.')
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, int) or self.timeout_seconds <= 0:
            raise MpesaConfigError('M-Pesa request timeout configuration is invalid.')

    def _oauth_cache_key(self):
        digest = hashlib.sha256(
            f'{self.base_url}\0{self.consumer_key}\0{self.consumer_secret}'.encode('utf-8')
        ).hexdigest()
        return f'daraja:oauth:{digest}'

    def _clear_cached_access_token(self):
        cache.delete(self._oauth_cache_key())

    def _authorized_json_request(self, build_request, access_token=None):
        token = access_token or self.get_access_token()
        try:
            return self._json_request(build_request(token))
        except MpesaAuthError:
            if access_token:
                raise
            # A definite HTTP 401/403 means the request was not authorized.
            # Refresh once; never retry ambiguous transport failures.
            self._clear_cached_access_token()
            refreshed_token = self.get_access_token()
            return self._json_request(build_request(refreshed_token))

    def get_access_token(self) -> str:
        self.require_configured()
        cache_key = self._oauth_cache_key()
        cached_token = cache.get(cache_key)
        if isinstance(cached_token, str) and cached_token:
            return cached_token
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
        try:
            expires_in = int(payload.get('expires_in'))
        except (TypeError, ValueError) as error:
            raise MpesaResponseError('Daraja OAuth response did not include a valid token expiry.') from error
        if expires_in <= 0:
            raise MpesaResponseError('Daraja OAuth response did not include a valid token expiry.')
        token = access_token.strip()
        # Daraja tokens are documented as one hour; leave a one-minute safety margin.
        cache.set(cache_key, token, timeout=max(1, expires_in - 60))
        return token

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
        def build_request(token):
            return urllib.request.Request(
                f'{self.base_url}{STK_PATH}',
                data=json.dumps(body).encode('utf-8'),
                method='POST',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
            )
        # Payment amounts are sensitive financial data. Keep request logs to a
        # fixed endpoint path; never include request payload fields.
        logger.info('Daraja STK Push request path=%s', STK_PATH)
        payload = self._authorized_json_request(build_request, access_token)
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

    def stk_query(self, *, checkout_request_id: str, access_token: str | None = None, timestamp: str | None = None) -> dict:
        """Ask Daraja for the provider-side outcome of an existing STK request."""
        self.require_configured()
        if not checkout_request_id:
            raise MpesaError('CheckoutRequestID is required.')
        stamp = timestamp or daraja_timestamp()
        body = {
            'BusinessShortCode': self.shortcode,
            'Password': stk_password(self.shortcode, self.passkey, stamp),
            'Timestamp': stamp,
            'CheckoutRequestID': checkout_request_id,
        }
        def build_request(token):
            return urllib.request.Request(
                f'{self.base_url}{STK_QUERY_PATH}', data=json.dumps(body).encode('utf-8'),
                method='POST', headers={
                    'Authorization': f'Bearer {token}', 'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
            )
        logger.info('Daraja STK query request path=%s', STK_QUERY_PATH)
        return self._authorized_json_request(build_request, access_token)

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
            if error.code in (401, 403):
                raise MpesaAuthError('Daraja rejected the access token.') from error
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
            if int(status) in (401, 403):
                raise MpesaAuthError('Daraja rejected the access token.')
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
