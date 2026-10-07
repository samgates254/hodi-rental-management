import base64
import io
import json
import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings

from infrastructure.payments.mpesa import (
    MpesaAuthError,
    MpesaClient,
    MpesaConfigError,
    MpesaHTTPError,
    MpesaResponseError,
    MpesaTimeoutError,
    daraja_timestamp,
    stk_password,
)

CALLBACK_URL = 'https://example.test/api/v1/billing/mpesa/callback/'
ACCESS_TOKEN = 'test-access-token-do-not-log'
CONSUMER_SECRET = 'test-consumer-secret-do-not-log'
PASSKEY = 'test-passkey-do-not-log'


class FakeResponse:
    def __init__(self, payload, status=200, raw=None):
        if raw is not None:
            self._body = raw
        elif isinstance(payload, (bytes, bytearray)):
            self._body = bytes(payload)
        else:
            self._body = json.dumps(payload).encode('utf-8')
        self.status = status

    def read(self):
        return self._body

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _client(urlopen, **overrides):
    kwargs = {
        'base_url': 'https://sandbox.safaricom.co.ke',
        'consumer_key': 'test-key',
        'consumer_secret': CONSUMER_SECRET,
        'shortcode': '123456',
        'passkey': PASSKEY,
        'callback_url': CALLBACK_URL,
        'timeout_seconds': 5,
        'urlopen': urlopen,
    }
    kwargs.update(overrides)
    return MpesaClient(**kwargs)


class DarajaCryptoTests(SimpleTestCase):
    def test_timestamp_uses_nairobi_daraja_format(self):
        moment = datetime(2026, 10, 7, 12, 0, 0, tzinfo=ZoneInfo('Africa/Nairobi'))
        self.assertEqual(daraja_timestamp(moment), '20261007120000')

    def test_timestamp_converts_from_utc(self):
        moment = datetime(2026, 10, 7, 9, 0, 0, tzinfo=ZoneInfo('UTC'))
        self.assertEqual(daraja_timestamp(moment), '20261007120000')

    def test_password_is_base64_of_shortcode_passkey_timestamp(self):
        stamp = '20261007120000'
        expected = base64.b64encode(f'123456{PASSKEY}{stamp}'.encode('utf-8')).decode('ascii')
        self.assertEqual(stk_password('123456', PASSKEY, stamp), expected)


class MpesaClientOAuthTests(SimpleTestCase):
    def test_successful_oauth_returns_access_token(self):
        def urlopen(request, timeout=None):
            self.assertEqual(timeout, 5)
            self.assertIn('grant_type=client_credentials', request.full_url)
            self.assertTrue(request.get_header('Authorization').startswith('Basic '))
            return FakeResponse({'access_token': ACCESS_TOKEN, 'expires_in': '3599'})

        token = _client(urlopen).get_access_token()
        self.assertEqual(token, ACCESS_TOKEN)

    def test_invalid_credentials_raise_auth_error(self):
        def urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                'Bad Request',
                hdrs=None,
                fp=io.BytesIO(b'{"errorMessage":"Invalid Credentials"}'),
            )

        with self.assertRaises(MpesaAuthError):
            _client(urlopen).get_access_token()

    def test_malformed_oauth_response_raises(self):
        def urlopen(request, timeout=None):
            return FakeResponse({'expires_in': '3599'})

        with self.assertRaises(MpesaResponseError):
            _client(urlopen).get_access_token()

    def test_non_json_oauth_response_raises(self):
        def urlopen(request, timeout=None):
            return FakeResponse(None, raw=b'not-json')

        with self.assertRaises(MpesaResponseError):
            _client(urlopen).get_access_token()

    def test_oauth_timeout_raises(self):
        def urlopen(request, timeout=None):
            raise TimeoutError('timed out')

        with self.assertRaises(MpesaTimeoutError):
            _client(urlopen).get_access_token()

    def test_oauth_http_error_raises(self):
        def urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url,
                500,
                'Server Error',
                hdrs=None,
                fp=io.BytesIO(b'oops'),
            )

        with self.assertRaises(MpesaHTTPError):
            _client(urlopen).get_access_token()

    def test_secret_and_token_are_not_logged(self):
        def urlopen(request, timeout=None):
            return FakeResponse({'access_token': ACCESS_TOKEN, 'expires_in': '3599'})

        with self.assertLogs('infrastructure.payments.mpesa', level='INFO') as captured:
            _client(urlopen).get_access_token()
        joined = '\n'.join(captured.output)
        self.assertNotIn(CONSUMER_SECRET, joined)
        self.assertNotIn(ACCESS_TOKEN, joined)
        self.assertNotIn(PASSKEY, joined)
        self.assertNotIn('Basic ', joined)


class MpesaClientStkTests(SimpleTestCase):
    def _stk_urlopen(self, stk_payload, captured=None, status=200):
        def urlopen(request, timeout=None):
            path = request.full_url
            if '/oauth/v1/generate' in path:
                return FakeResponse({'access_token': ACCESS_TOKEN, 'expires_in': '3599'})
            if captured is not None:
                captured['request'] = request
                captured['timeout'] = timeout
                captured['body'] = json.loads(request.data.decode('utf-8'))
            if isinstance(stk_payload, Exception):
                raise stk_payload
            return FakeResponse(stk_payload, status=status)

        return urlopen

    def test_successful_stk_request_parses_provider_ids(self):
        payload = {
            'MerchantRequestID': 'm-1',
            'CheckoutRequestID': 'c-1',
            'ResponseCode': '0',
            'ResponseDescription': 'Success. Request accepted for processing',
            'CustomerMessage': 'Success. Request accepted for processing',
        }
        result = _client(self._stk_urlopen(payload)).stk_push(
            phone_number='254700000010',
            amount_kes=1500,
            account_reference='42',
            transaction_desc='Rent payment',
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.merchant_request_id, 'm-1')
        self.assertEqual(result.checkout_request_id, 'c-1')
        self.assertEqual(result.response_code, '0')
        self.assertEqual(result.customer_message, payload['CustomerMessage'])

    def test_response_code_zero_is_accepted_not_settled(self):
        payload = {
            'MerchantRequestID': 'm-1',
            'CheckoutRequestID': 'c-1',
            'ResponseCode': '0',
            'ResponseDescription': 'Success. Request accepted for processing',
            'CustomerMessage': 'ok',
        }
        result = _client(self._stk_urlopen(payload)).stk_push(
            phone_number='254700000010',
            amount_kes=1,
            account_reference='RENT',
            transaction_desc='Rent payment',
        )
        self.assertEqual(result.response_code, '0')
        self.assertTrue(result.accepted)

    def test_nonzero_response_code_is_not_accepted(self):
        payload = {
            'MerchantRequestID': 'm-2',
            'CheckoutRequestID': 'c-2',
            'ResponseCode': '1',
            'ResponseDescription': 'The request is being processed',
            'CustomerMessage': 'Unable to process',
        }
        result = _client(self._stk_urlopen(payload)).stk_push(
            phone_number='254700000010',
            amount_kes=1,
            account_reference='RENT',
            transaction_desc='Rent payment',
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.response_code, '1')

    def test_stk_timeout_raises(self):
        urlopen = self._stk_urlopen(TimeoutError('timed out'))
        with self.assertRaises(MpesaTimeoutError):
            _client(urlopen).stk_push(
                phone_number='254700000010',
                amount_kes=1,
                account_reference='RENT',
                transaction_desc='Rent payment',
            )

    def test_malformed_stk_response_raises(self):
        def urlopen(request, timeout=None):
            if '/oauth/v1/generate' in request.full_url:
                return FakeResponse({'access_token': ACCESS_TOKEN, 'expires_in': '3599'})
            return FakeResponse(None, raw=b'<html>nope</html>')

        with self.assertRaises(MpesaResponseError):
            _client(urlopen).stk_push(
                phone_number='254700000010',
                amount_kes=1,
                account_reference='RENT',
                transaction_desc='Rent payment',
            )

    def test_amount_phone_timestamp_password_and_callback_are_sent(self):
        captured = {}
        payload = {
            'MerchantRequestID': 'm-1',
            'CheckoutRequestID': 'c-1',
            'ResponseCode': '0',
            'ResponseDescription': 'ok',
            'CustomerMessage': 'ok',
        }
        stamp = '20261007120000'
        _client(self._stk_urlopen(payload, captured=captured)).stk_push(
            phone_number='254711111111',
            amount_kes=2500,
            account_reference='INV9',
            transaction_desc='Rent payment',
            timestamp=stamp,
        )
        body = captured['body']
        self.assertEqual(body['Amount'], 2500)
        self.assertEqual(body['PartyA'], '254711111111')
        self.assertEqual(body['PhoneNumber'], '254711111111')
        self.assertEqual(body['BusinessShortCode'], '123456')
        self.assertEqual(body['PartyB'], '123456')
        self.assertEqual(body['Timestamp'], stamp)
        self.assertEqual(body['CallBackURL'], CALLBACK_URL)
        self.assertEqual(body['Password'], stk_password('123456', PASSKEY, stamp))
        self.assertEqual(body['AccountReference'], 'INV9')
        self.assertTrue(captured['request'].get_header('Authorization').startswith('Bearer '))

    def test_passkey_password_and_token_are_not_logged(self):
        payload = {
            'MerchantRequestID': 'm-1',
            'CheckoutRequestID': 'c-1',
            'ResponseCode': '0',
            'ResponseDescription': 'ok',
            'CustomerMessage': 'ok',
        }
        with self.assertLogs('infrastructure.payments.mpesa', level='INFO') as captured:
            _client(self._stk_urlopen(payload)).stk_push(
                phone_number='254700000010',
                amount_kes=10,
                account_reference='RENT',
                transaction_desc='Rent payment',
            )
        joined = '\n'.join(captured.output)
        self.assertNotIn(PASSKEY, joined)
        self.assertNotIn(ACCESS_TOKEN, joined)
        self.assertNotIn(CONSUMER_SECRET, joined)
        self.assertNotIn('Bearer ', joined)

    def test_http_callback_url_is_rejected(self):
        client = _client(lambda request, timeout=None: None, callback_url='http://localhost/callback')
        with self.assertRaises(MpesaConfigError):
            client.require_configured()

    @override_settings(
        MPESA_BASE_URL='https://sandbox.safaricom.co.ke',
        MPESA_CONSUMER_KEY='test-key',
        MPESA_CONSUMER_SECRET=CONSUMER_SECRET,
        MPESA_SHORTCODE='123456',
        MPESA_PASSKEY=PASSKEY,
        MPESA_CALLBACK_URL=CALLBACK_URL,
        MPESA_TIMEOUT_SECONDS=5,
        MPESA_TRANSACTION_TYPE='CustomerPayBillOnline',
    )
    def test_from_settings_uses_configured_callback(self):
        client = MpesaClient.from_settings()
        self.assertEqual(client.callback_url, CALLBACK_URL)
        self.assertEqual(client.base_url, 'https://sandbox.safaricom.co.ke')
