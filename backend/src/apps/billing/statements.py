"""Tenant statement built from posted ledger rows. Amounts stay integer cents."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta

from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.leases.models import Lease, RentSchedule
from apps.tenants.models import Tenant

from .models import Charge, DocumentStatus, Payment

MAX_PERIOD_DAYS = 731
PERIODS = ('current_month', 'previous_month', 'lease')
LIVE_PAYMENT_STATUSES = (Payment.Status.ALLOCATED, Payment.Status.PENDING)


def tenant_for_statement(user):
	if not user or not getattr(user, 'is_authenticated', False):
		return None
	return (
		Tenant.objects.filter(
			user=user,
			is_active=True,
			organization__is_active=True,
		)
		.select_related('organization')
		.first()
	)


def _parse_date(value, field):
	try:
		return datetime.strptime(value, '%Y-%m-%d').date()
	except (TypeError, ValueError) as error:
		raise ValidationError({field: 'Use YYYY-MM-DD.'}) from error


def _month_bounds(day):
	start = day.replace(day=1)
	end = date(day.year, day.month, monthrange(day.year, day.month)[1])
	return start, end


def _previous_month_bounds(day):
	first, _end = _month_bounds(day)
	last_of_previous = first - timedelta(days=1)
	return _month_bounds(last_of_previous)


def resolve_period(params, lease, today):
	raw_from = (params.get('from') or '').strip()
	raw_to = (params.get('to') or '').strip()
	period = (params.get('period') or '').strip().lower()
	note = ''
	if raw_from or raw_to:
		if not raw_from or not raw_to:
			raise ValidationError({'from': 'Provide both from and to, as YYYY-MM-DD.'})
		start = _parse_date(raw_from, 'from')
		end = _parse_date(raw_to, 'to')
		label = 'custom'
	elif period in ('', 'current_month'):
		start, end = _month_bounds(today)
		label = 'current_month'
	elif period == 'previous_month':
		start, end = _previous_month_bounds(today)
		label = 'previous_month'
	elif period == 'lease':
		if lease is None:
			start, end = _month_bounds(today)
			label = 'current_month'
			note = 'No lease is on file, so this statement uses the current month.'
		else:
			start = lease.start_date
			end = lease.end_date if lease.end_date and lease.end_date < today else today
			if end < start:
				end = start
			label = 'lease'
	else:
		raise ValidationError({'period': 'Use current_month, previous_month, or lease.'})
	if end < start:
		raise ValidationError({'to': 'The end date must be on or after the start date.'})
	if (end - start).days > MAX_PERIOD_DAYS:
		raise ValidationError({'to': 'Choose a period of 24 months or less.'})
	return {'start': start, 'end': end, 'label': label, 'note': note}


def _lease_for(tenant):
	leases = list(
		Lease.objects.filter(tenant=tenant)
		.select_related('unit__building__property')
		.order_by('-start_date', '-id')
	)
	for lease in leases:
		if lease.status == Lease.Status.ACTIVE:
			return lease
	return leases[0] if leases else None


def _sum(queryset, field):
	value = queryset.aggregate(total=Sum(field))['total']
	return int(value or 0)


def build_statement(user, params):
	tenant = tenant_for_statement(user)
	if tenant is None:
		raise NotFound('No tenant record is linked to this account.')
	today = timezone.localdate()
	lease = _lease_for(tenant)
	period = resolve_period(params, lease, today)
	start = period['start']
	end = period['end']

	charges = list(
		Charge.objects.filter(
			tenant=tenant,
			lifecycle=DocumentStatus.POSTED,
			due_date__gte=start,
			due_date__lte=end,
		).order_by('due_date', 'created_at')
	)
	payments = list(
		Payment.objects.filter(
			tenant=tenant,
			status__in=LIVE_PAYMENT_STATUSES,
			received_date__gte=start,
			received_date__lte=end,
		).order_by('received_date', 'created_at')
	)
	posted = Charge.objects.filter(tenant=tenant, lifecycle=DocumentStatus.POSTED)
	outstanding = _sum(posted, 'balance_cents')
	overdue = _sum(posted.filter(due_date__lt=today, balance_cents__gt=0), 'balance_cents')
	credit = _sum(
		Payment.objects.filter(tenant=tenant, status__in=LIVE_PAYMENT_STATUSES),
		'overpayment_cents',
	)
	schedules = []
	if lease is not None:
		schedules = list(
			RentSchedule.objects.filter(lease=lease)
			.filter(effective_from__lte=end)
			.filter(models_effective_to(start))
			.order_by('effective_from')
		)

	lines = []
	for charge in charges:
		description = charge.description.strip() or charge.charge_type.replace('_', ' ').title()
		lines.append({
			'date': charge.due_date.isoformat(),
			'kind': 'charge',
			'description': description,
			'debit_cents': int(charge.amount_cents),
			'credit_cents': 0,
			'status': charge.lifecycle,
		})
	for payment in payments:
		label = payment.get_method_display()
		if payment.reference:
			label = f'{label} {payment.reference}'
		lines.append({
			'date': payment.received_date.isoformat(),
			'kind': 'payment',
			'description': label,
			'debit_cents': 0,
			'credit_cents': int(payment.amount_cents),
			'status': payment.status,
		})
	lines.sort(key=lambda row: (row['date'], 0 if row['kind'] == 'charge' else 1, row['description']))

	property_record = None
	unit = None
	if lease is not None:
		unit = lease.unit
		property_record = unit.building.property

	return {
		'tenant': {
			'name': tenant.full_name,
			'email': tenant.email,
			'phone_number': tenant.phone_number,
		},
		'property': None if property_record is None else {
			'name': property_record.name,
			'city': property_record.city,
		},
		'unit': None if unit is None else {'name': unit.name},
		'lease': None if lease is None else {
			'reference': lease.reference,
			'status': lease.status,
			'start_date': lease.start_date.isoformat(),
			'end_date': lease.end_date.isoformat() if lease.end_date else None,
			'monthly_rent_minor': int(lease.monthly_rent_minor),
		},
		'rent_schedule': [
			{
				'effective_from': item.effective_from.isoformat(),
				'effective_to': item.effective_to.isoformat() if item.effective_to else None,
				'amount_minor': int(item.amount_minor),
				'frequency': item.frequency,
			}
			for item in schedules
		],
		'period': {
			'start': start.isoformat(),
			'end': end.isoformat(),
			'label': period['label'],
			'note': period['note'],
		},
		'currency': 'KES',
		'lines': lines,
		'period_charges_cents': sum(row['debit_cents'] for row in lines),
		'period_payments_cents': sum(row['credit_cents'] for row in lines),
		'outstanding_cents': outstanding,
		'overdue_cents': overdue,
		'credit_cents': credit,
		'current_balance_cents': outstanding - credit,
		'generated_at': timezone.now().isoformat(),
	}


def models_effective_to(start):
	from django.db.models import Q
	return Q(effective_to__isnull=True) | Q(effective_to__gte=start)


def format_kes(cents):
	value = int(cents)
	sign = '-' if value < 0 else ''
	whole, fraction = divmod(abs(value), 100)
	body = f'{whole:,}'
	if fraction:
		return f'{sign}KES {body}.{fraction:02d}'
	return f'{sign}KES {body}'


def _pdf_text(value):
	cleaned = ''.join(ch if 32 <= ord(ch) <= 126 else ' ' for ch in str(value))
	return cleaned.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def statement_pdf(statement):
	tenant = statement['tenant']
	prop = statement['property'] or {}
	unit = statement['unit'] or {}
	lease = statement['lease'] or {}
	period = statement['period']
	lines = [
		'HODI',
		'Tenant statement',
		'',
		f"Tenant: {tenant['name']}",
		f"Email: {tenant['email'] or '-'}",
		f"Phone: {tenant['phone_number'] or '-'}",
		f"Property: {prop.get('name') or '-'}",
		f"City: {prop.get('city') or '-'}",
		f"Unit: {unit.get('name') or '-'}",
		f"Lease: {lease.get('reference') or '-'}",
		f"Lease status: {lease.get('status') or '-'}",
		f"Lease start: {lease.get('start_date') or '-'}",
		f"Lease end: {lease.get('end_date') or 'Open'}",
		f"Monthly rent: {format_kes(lease['monthly_rent_minor'])}" if lease else 'Monthly rent: -',
		f"Statement period: {period['start']} to {period['end']}",
	]
	if period.get('note'):
		lines.append(period['note'])
	lines.extend([
		'',
		'Date        Description                          Debit           Credit',
		'----------------------------------------------------------------',
	])
	if not statement['lines']:
		lines.append('No posted charges or recorded payments in this period.')
	for row in statement['lines']:
		debit = format_kes(row['debit_cents']) if row['debit_cents'] else ''
		credit = format_kes(row['credit_cents']) if row['credit_cents'] else ''
		description = row['description'][:36]
		lines.append(f"{row['date']}  {description:<36} {debit:>14} {credit:>14}")
	lines.extend([
		'----------------------------------------------------------------',
		f"Period charges: {format_kes(statement['period_charges_cents'])}",
		f"Period payments: {format_kes(statement['period_payments_cents'])}",
		f"Outstanding balance: {format_kes(statement['outstanding_cents'])}",
		f"Overdue balance: {format_kes(statement['overdue_cents'])}",
		f"Unapplied credit: {format_kes(statement['credit_cents'])}",
		f"Current balance: {format_kes(statement['current_balance_cents'])}",
		'',
		'Amounts are Kenyan shillings from posted charges and recorded payments.',
		'A negative current balance is credit. This is not a tax invoice.',
		'Generating this file does not record a payment.',
		f"Generated: {statement['generated_at']}",
	])
	for item in statement['rent_schedule']:
		lines.append(
			f"Rent schedule {item['frequency']} {format_kes(item['amount_minor'])} from {item['effective_from']}"
		)
	return _render_pdf(lines)


def _render_pdf(text_lines):
	page_size = 46
	pages = [text_lines[index:index + page_size] for index in range(0, len(text_lines), page_size)] or [[]]
	streams = []
	for page in pages:
		commands = ['BT', '/F1 10 Tf', '40 800 Td', '14 TL']
		for line in page:
			commands.append(f'({_pdf_text(line)}) Tj T*')
		commands.append('ET')
		streams.append('\n'.join(commands).encode('ascii'))

	objects = {}
	font_id = 3 + len(streams) * 2
	page_ids = []
	next_id = 3
	for stream in streams:
		page_id = next_id
		content_id = next_id + 1
		page_ids.append(page_id)
		objects[content_id] = b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'\nendstream'
		objects[page_id] = (
			f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] '
			f'/Contents {content_id} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>'
		).encode('ascii')
		next_id += 2
	kids = ' '.join(f'{page_id} 0 R' for page_id in page_ids)
	objects[1] = b'<< /Type /Catalog /Pages 2 0 R >>'
	objects[2] = f'<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>'.encode('ascii')
	objects[font_id] = b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'

	body = bytearray(b'%PDF-1.4\n')
	offsets = {0: 0}
	for number in sorted(objects):
		offsets[number] = len(body)
		body.extend(f'{number} 0 obj\n'.encode('ascii'))
		body.extend(objects[number])
		body.extend(b'\nendobj\n')
	xref_at = len(body)
	count = max(objects) + 1
	body.extend(f'xref\n0 {count}\n'.encode('ascii'))
	body.extend(b'0000000000 65535 f \n')
	for number in range(1, count):
		body.extend(f'{offsets.get(number, 0):010d} 00000 n \n'.encode('ascii'))
	body.extend(
		f'trailer << /Size {count} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF'.encode('ascii')
	)
	return bytes(body)
