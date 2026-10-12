"""Redact M-Pesa credentials and callback data from application log records."""

import logging
import os
import re

from django.conf import settings


CALLBACK_PATH = re.compile(r'(/api/v1/billing/mpesa/callback/)[^/?\s]+', re.IGNORECASE)
CALLBACK_PAYLOAD = re.compile(
    r'CallbackMetadata|MpesaReceiptNumber|stkCallback|"?PhoneNumber"?', re.IGNORECASE,
)
KENYAN_PHONE = re.compile(r'(?<!\d)(?:\+?254|0)[17]\d{8}(?!\d)')


class MpesaSensitiveLogFilter(logging.Filter):
    """Sanitize accidental path, credential, and callback-content logging."""

    def filter(self, record):
        message = record.getMessage()
        sensitive = CALLBACK_PAYLOAD.search(message) is not None
        if sensitive:
            message = '[REDACTED M-Pesa callback payload]'
        else:
            callback_path_found = CALLBACK_PATH.search(message) is not None
            message = CALLBACK_PATH.sub(r'\1[REDACTED]/', message)
            sensitive_values = (
                getattr(settings, 'MPESA_CALLBACK_AUTH_TOKEN', ''),
                getattr(settings, 'MPESA_CONSUMER_KEY', ''),
                getattr(settings, 'MPESA_CONSUMER_SECRET', ''),
                getattr(settings, 'MPESA_PASSKEY', ''),
                os.environ.get('DATABASE_URL', ''),
                settings.DATABASES.get('default', {}).get('PASSWORD', ''),
            )
            for value in sensitive_values:
                if value:
                    sensitive = sensitive or str(value) in message
                    message = message.replace(str(value), '[REDACTED]')
            sensitive = sensitive or callback_path_found
            sensitive = KENYAN_PHONE.search(message) is not None or sensitive
            message = KENYAN_PHONE.sub('[REDACTED PHONE]', message)
        if record.exc_info and sensitive:
            # A traceback can repeat the original URL, payload, or secret in
            # an exception message, so suppress it for redacted records.
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        record.msg = message
        record.args = ()
        return True
