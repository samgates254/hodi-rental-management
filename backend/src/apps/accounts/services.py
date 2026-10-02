from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.authtoken.models import Token

from .models import AccountProfile

VERIFICATION_SALT = 'accounts.email-verification'


def send_verification_email(user):
	token = signing.dumps(
		{'user_id': user.pk, 'email': user.email.casefold()},
		salt=VERIFICATION_SALT,
	)
	send_mail(
		'Verify your email address',
		(
			'Use this verification token to activate your account:\n\n'
			f'{token}\n\n'
			f'Submit it to {settings.ACCOUNT_EMAIL_VERIFICATION_PATH} '
			'as the token field in a JSON POST request.'
		),
		settings.DEFAULT_FROM_EMAIL,
		[user.email],
		fail_silently=False,
	)


@transaction.atomic
def verify_email_token(token):
	try:
		payload = signing.loads(
			token,
			salt=VERIFICATION_SALT,
			max_age=settings.EMAIL_VERIFICATION_TOKEN_MAX_AGE,
		)
		user = get_user_model().objects.get(pk=payload['user_id'])
		profile = AccountProfile.objects.get(user=user)
	except (signing.BadSignature, KeyError, TypeError, ValueError, get_user_model().DoesNotExist, AccountProfile.DoesNotExist) as error:
		return None

	if profile.email_verified_at is not None or user.email.casefold() != payload.get('email'):
		return None

	profile.email_verified_at = timezone.now()
	profile.save(update_fields=('email_verified_at', 'updated_at'))
	return user


def send_password_reset_email(user):
	uid = urlsafe_base64_encode(force_bytes(user.pk))
	token = default_token_generator.make_token(user)
	send_mail(
		'Reset your password',
		(
			'We received a request to reset the password for your account.\n\n'
			f'Submit these values to {settings.ACCOUNT_PASSWORD_RESET_CONFIRM_PATH}:\n'
			f'uid={uid}\n'
			f'token={token}\n\n'
			'If you did not request this, you can ignore this email.'
		),
		settings.DEFAULT_FROM_EMAIL,
		[user.email],
		fail_silently=False,
	)


@transaction.atomic
def reset_user_password(uid, token, password):
	user_model = get_user_model()
	try:
		user_id = force_str(urlsafe_base64_decode(uid))
		user = user_model.objects.select_for_update().get(pk=user_id)
	except (
		TypeError,
		ValueError,
		OverflowError,
		UnicodeDecodeError,
		user_model.DoesNotExist,
	):
		return False

	if not user.is_active or not default_token_generator.check_token(user, token):
		return False

	password_validation.validate_password(password, user)
	user.set_password(password)
	user.save(update_fields=('password',))
	Token.objects.filter(user=user).delete()
	return True