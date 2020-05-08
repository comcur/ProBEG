# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.utils.timezone import localtime
from django.core.mail import send_mail
from django.http import HttpResponse
from django.contrib import messages
from django.utils import timezone


import hashlib
import urllib

from results import models, models_klb, results_util
from results.forms import PaymentForm, MedalOrderForm
from results.models_klb import get_participation_price
from views_common import user_edit_vars
from editor.views.views_common import get_team_club_year_context_target

MONETA_ACCOUNT_NUMBER = '69059003'
MONETA_SECRET = '575757'
MONETA_CURRENCY_CODE = 'RUB'
# CARDS_UNITID = '2705264'
MAX_DESCRIPTION_LENGTH = 100
DESCRIPTION_PREFIX = 'probeg_org_'

def get_test_symbol(payment_or_response):
	return '1' if payment_or_response.is_test_mode else '0'


# MNT_SIGNATURE = MD5(MNT_ID + MNT_TRANSACTION_ID + MNT_AMOUNT + MNT_CURRENCY_CODE + MNT_SUBSCRIBER_ID + ТЕСТОВЫЙ РЕЖИМ + КОД ПРОВЕРКИ ЦЕЛОСТНОСТИ ДАННЫХ)
def get_payment_md5(payment):
	s = (MONETA_ACCOUNT_NUMBER
		+ payment.transaction_id
		+ unicode(payment.amount)
		+ MONETA_CURRENCY_CODE
		+ (unicode(payment.user.id) if payment.user else '')
		+ get_test_symbol(payment)
		+ MONETA_SECRET)
	m = hashlib.md5(s)
	# models.write_log('MD5 key for {} is {}'.format(s, m.hexdigest()))
	# m.update(MONETA_ACCOUNT_NUMBER)
	# m.update(payment.transaction_id)
	# m.update(unicode(payment.amount))
	# m.update(MONETA_CURRENCY_CODE)
	# if payment.user:
	# 	m.update(unicode(payment.user.id))
	# m.update(get_test_symbol(payment))
	# m.update(MONETA_SECRET)
	return m.hexdigest()

# MNT_SIGNATURE = MD5(MNT_ID + MNT_TRANSACTION_ID + MNT_OPERATION_ID + MNT_AMOUNT + MNT_CURRENCY_CODE + MNT_SUBSCRIBER_ID + MNT_TEST_MODE
# + КОД ПРОВЕРКИ ЦЕЛОСТНОСТИ ДАННЫХ)
def get_response_md5(response):
	m = hashlib.md5()
	m.update(MONETA_ACCOUNT_NUMBER)
	m.update(response.transaction_id)
	m.update(response.moneta_operation_id)
	m.update(unicode(response.withdraw_amount))
	m.update(response.currency)
	m.update(response.moneta_subscriber_id)
	m.update(get_test_symbol(response))
	m.update(MONETA_SECRET)
	return m.hexdigest()

def get_redirect_url(payment):
	payment_description = (payment.description[:(MAX_DESCRIPTION_LENGTH - 3)] + u'...' if len(payment.description) > MAX_DESCRIPTION_LENGTH
			else payment.description)
	# payment_description = payment_description.encode('unicode-escape')
	payment_description = urllib.quote(payment_description.encode('utf8'))
	payment_desc_for_check = u'Покупка на сайте ПроБЕГ'.encode('unicode-escape')
	params = {
		'MNT_ID' : MONETA_ACCOUNT_NUMBER,
		'MNT_TRANSACTION_ID' : payment.transaction_id,
		'MNT_AMOUNT' : unicode(payment.amount),
		'MNT_CURRENCY_CODE' : MONETA_CURRENCY_CODE,
		'MNT_TEST_MODE' : get_test_symbol(payment),
		'MNT_DESCRIPTION' : payment_description,
		'MNT_SUBSCRIBER_ID' : payment.user.id if payment.user else '',
		'MNT_SIGNATURE' : payment.signature,
		'MNT_CUSTOM1' : '1',
		'MNT_CUSTOM2' : u'{{"customer":"{}","items": [{{"n":"{}","p":"{}","q":"{}","t":"{}"}}]}}'.format(
			payment.user.email if payment.user else '',
			# payment.description[:100],
			# urllib.quote(u'Оплата на сайте probeg.org'.encode('cp1251')), # Sends like %25%DD
			# urllib.quote(u'Оплата на сайте probeg.org'.encode('unicode-escape')),
			payment_desc_for_check,
			unicode(payment.amount),
			'1',
			'1105'
			),
		# 'paymentSystem.limitIds' : CARDS_UNITID,
	}
	return u'https://www.payanyway.ru/assistant.htm?' + urllib.urlencode(params, 'utf-8').replace('%5C', '\\').replace('%25', '%')

@login_required
def payment_form(request):
	context = {}
	context['page_title'] = u'Оплата услуг ПроБЕГу'
	user = request.user

	if 'btnPayment' in request.POST:
		form = PaymentForm(request.POST, user=request.user)
		if form.is_valid():
			payment = form.save()
			payment.transaction_id = DESCRIPTION_PREFIX + unicode(payment.id)
			payment.is_test_mode = False
			payment.user = user if user.is_authenticated() else None
			payment.save()
			payment.refresh_from_db()
			payment.signature = get_payment_md5(payment)
			payment.save()
			models.write_log('Redirecting to {}'.format(get_redirect_url(payment)))
			# messages.success(request, u'Адрес для переадресации: {}'.format(get_redirect_url(payment)))
			return redirect(get_redirect_url(payment))
		else:
			messages.warning(request, u"Пожалуйста, исправьте ошибки в форме.")
	else:
		form = PaymentForm(user=request.user)

	context['form'] = form
	return render(request, "payment/payment_form.html", context)

@login_required
def klb_make_individual_payment(request, year):
	context = user_edit_vars(request.user)
	year = models.int_safe(year)
	if not models.is_active_klb_year(year, context['is_admin']):
		messages.warning(request, u'Сейчас нельзя заявиться в КЛБМатч–{}'.format(year))
		return redirect(reverse('results:klb_match_summary', kwargs={'year': year}))
	participant = models.Klb_participant.objects.filter(klb_person__runner__user_id=request.user.id, match_year=year).first()
	if not participant:
		messages.warning(request, u'Вы ещё не заявлены в КЛБМатч–{}'.format(year))
		return redirect(reverse('results:klb_application', kwargs={'year': year}))
	person = participant.klb_person
	if participant.paid_status != models.PAID_STATUS_NO:
		messages.warning(request, u'Вы уже оплатили участие в КЛБМатче–{}'.format(year))
		return redirect(person)
	if participant.team and not participant.team.club.members_can_pay_themselves:
		messages.warning(request, u'Ваше участие в КЛБМатче может оплатить только капитан команды «{}»; Вам достаточно передать деньги ему.'.format(
			participant.team.name))
		return redirect(person)
	payment = models.Payment_moneta.objects.create(
		amount=models_klb.get_participation_price(year),
		description=u'Оплата за себя: {} {}'.format(person.fname, person.lname),
		user=request.user,
		sender=request.user.get_full_name(),
	)
	payment.refresh_from_db()
	payment.transaction_id = DESCRIPTION_PREFIX + unicode(payment.id)
	payment.signature = get_payment_md5(payment)
	payment.save()

	participant.payment = payment
	participant.save()
	models.write_log('klb_make_individual_payment: Redirecting to {}'.format(get_redirect_url(payment)))
	return redirect(get_redirect_url(payment))

@login_required
def klb_make_team_or_club_payment(request, team_id=None, club_id=None):
	team, club, team_or_club, year, context, target, participants = get_team_club_year_context_target(request, team_id, club_id)
	if target:
		return target

	if 'btnPayForTeam' not in request.POST:
		return redirect(team_or_club.get_payment_url())

	good_participant_ids = set(participants.filter(payment=None).values_list('pk', flat=True))
	bad_participant_ids = set(participants.exclude(payment=None).values_list('pk', flat=True))
	good_participants = []
	bad_participants = []

	total_amount = models.int_safe(request.POST.get('total_amount', 0))
	price = get_participation_price(year)
	sum_of_prices = 0

	user = request.user
	for key, val in request.POST.items():
		if key.startswith("amount_"):
			participant_id = models.int_safe(key[len("amount_"):])
			if participant_id in bad_participant_ids:
				bad_participants.append((participant_id, u'Участие уже оплачено'))
			elif participant_id not in good_participant_ids:
				bad_participants.append((participant_id, u'Участник не выступает за нужную команду'))
			else: # So participant_id is in good_participant_ids
				participant = models.Klb_participant.objects.get(pk=participant_id)
				person = participant.klb_person

				participant_price = models.int_safe(val)
				if participant_price not in (0, price):
					bad_participants.append((participant_id, u'Недопустимая цена участия: {}'.format(participant_price)))
				elif (participant_price == 0) and (not participant.is_senior) and (person.disability_group == 0):
					bad_participants.append((participant_id, u'Цена участия — 0, хотя участник молод и здоров'))
				else:
					good_participants.append((participant, participant_price == 0))
					sum_of_prices += participant_price

	problems_desc = ''
	if bad_participants:
		problems_desc = u'\n'.join(u'{}: {}'.format(participant_id, desc) for participant_id, desc in bad_participants)
	elif sum_of_prices != total_amount:
		problems_desc = u'Общая цена — {}, но сумма по отдельным участникам — {}'.format(total_amount, sum_of_prices)

	if problems_desc:
		models.send_panic_email(
			u'Problem when paying for club {} (id {}), team {} (id {})'.format(club.name, club.id,
				team.name if team else '-', team.id if team else '-'),
			u'User {} {}{} was trying to pay for this club. Correct participants: {}. Incorrect participants: {}. Problems:\n\n{}'.format(
				user.get_full_name(), models.SITE_URL, user.user_profile.get_absolute_url(), len(good_participants), len(bad_participants), problems_desc),
			to_all=True
		)
		messages.warning(request, (u'К сожалению, при создании заказа возникла проблема. Администраторы уже знают об этом. '
			+ u'Вы можете попробовать ещё раз или подождать письма от нас о том, что проблема исправлена.'))
		return redirect(team_or_club.get_payment_url())

	if len(good_participants) == 0:
		messages.warning(request, u'Похоже, вы пытались заплатить за 0 человек. Не стоит этого делать :)')
		return redirect(team_or_club)

	if total_amount == 0:
		payment = models.Payment_moneta.objects.create(
			amount=0,
			is_dummy=True,
			is_paid=True,
			user=user,
		)
		payment.transaction_id = models.PAYMENT_DUMMY_PREFIX + unicode(payment.id)
		payment.save()

		for participant, _ in good_participants:
			participant.payment = payment
			participant.paid_status = models.PAID_STATUS_FREE
			participant.save()
			models.log_obj_create(request.user, participant.klb_person, models.ACTION_KLB_PARTICIPANT_UPDATE, child_object=participant,
				field_list=['paid_status', 'payment'], comment=u'Платёж {}'.format(payment.id), verified_by=models.USER_ROBOT_CONNECTOR)
		messages.success(request, u'Вы оплатили участие {} человек на общую сумму 0 рублей. Ура!'.format(len(good_participants)))
		return redirect(team_or_club)

	payment = models.Payment_moneta.objects.create(
		amount=total_amount,
		description=u'Оплата за {} участник{} {} {} в КЛБМатче–{}'.format(
			len(good_participants), results_util.plural_ending_new(len(good_participants), 16), u'команды' if team else u'клуба',
			team_or_club.name, year),
		user=user,
		sender=user.get_full_name(),
	)
	payment.refresh_from_db()
	payment.transaction_id = DESCRIPTION_PREFIX + unicode(payment.id)
	payment.signature = get_payment_md5(payment)
	payment.save()

	for participant, wants_to_pay_zero in good_participants:
		participant.payment = payment
		participant.wants_to_pay_zero = wants_to_pay_zero
		participant.save()
		models.log_obj_create(request.user, participant.klb_person, models.ACTION_KLB_PARTICIPANT_UPDATE, child_object=participant,
			field_list=['wants_to_pay_zero', 'payment'], comment=u'Платёж {}'.format(payment.id), verified_by=models.USER_ROBOT_CONNECTOR)
	redirect_url = get_redirect_url(payment)
	return redirect(redirect_url)

# def klb_payment_form(request):
# 	context = {}
# 	context['page_title'] = u'Оплата участия в КЛБМатче'
# 	return render(request, "payment/klb_payment_form.html", context)

@login_required
def make_payment(request, payment_id):
	payment = get_object_or_404(models.Payment_moneta, pk=payment_id, is_active=True)
	context = user_edit_vars(request.user)
	if (payment.user_id != request.user.id) and not context['is_admin']:
		messages.warning(request, u'Заказ с номером {} — не Ваш. Оплатить его может только его создатель.'.format(payment.transaction_id))
		return redirect('results:my_payments')
	if payment.is_paid:
		messages.success(request, u'Заказ с номером {} на сумму {} ₽ уже оплачен'.format(payment.transaction_id, payment.amount))
		return redirect('results:my_payments')
	if payment.is_dummy:
		messages.success(request, u'Заказ с номером {} — ненастоящий. Не нужно его оплачивать.'.format(payment.transaction_id))
		return redirect('results:my_payments')
	return redirect(get_redirect_url(payment))

def make_medal_payment(request, medal_order):
	amount = medal_order.n_medals * models_klb.MEDAL_PRICE

	if medal_order.with_plate:
		amount += medal_order.n_medals * models_klb.PLATE_PRICE

	# if medal_order.lname == u'Пушкин': # For test purposes
	# 	amount = 15

	payment = models.Payment_moneta.objects.create(
		amount=amount,
		description=u'Оплата за {} медал{} участника КЛБМатча–{}'.format(
			medal_order.n_medals, results_util.plural_ending_new(medal_order.n_medals, 3), medal_order.year),
		user=medal_order.created_by,
		sender=medal_order.created_by.get_full_name() if medal_order.created_by else u'{} {}'.format(medal_order.fname, medal_order.lname),
	)
	payment.refresh_from_db()
	payment.transaction_id = DESCRIPTION_PREFIX + unicode(payment.id)
	payment.signature = get_payment_md5(payment)
	payment.save()

	medal_order.payment = payment
	medal_order.save()

	redirect_url = get_redirect_url(payment)
	# models.write_log('make_medal_payment: Redirecting to {}'.format(redirect_url))
	return redirect(redirect_url)

def medal_payment(request, year=models_klb.MEDAL_PAYMENT_YEAR):
	user = request.user
	context = user_edit_vars(user)
	context['page_title'] = u'Заказ памятных медалей участника КЛБМатча–{}'.format(models_klb.MEDAL_PAYMENT_YEAR)

	if 'btnPayment' in request.POST:
		form = MedalOrderForm(request.POST, user=user)
		if form.is_valid():
			if user.is_authenticated():
				form.instance.created_by = user
			form.save()
			return make_medal_payment(request, form.instance)
		else:
			messages.warning(request, u'Пожалуйста, исправьте ошибки в форме')
	else:
		form = MedalOrderForm(user=user)
	context['form'] = form
	context['year'] = year if (year == 2018) else models_klb.MEDAL_PAYMENT_YEAR
	context['MEDAL_PRICE'] = models_klb.MEDAL_PRICE
	context['PLATE_PRICE'] = models_klb.PLATE_PRICE
	context['initial_total'] = models_klb.MEDAL_PRICE # + models_klb..PLATE_PRICE
	context['user_is_authenticated'] = request.user.is_authenticated()
	return render(request, 'payment/medal_request_form_2018.html' if (year == 2018) else 'payment/medal_request_form_closed.html', context)

@login_required
def payment_delete(request, payment_id):
	payment = get_object_or_404(models.Payment_moneta, pk=payment_id, is_active=True)
	if payment.is_paid:
		messages.success(request, u'Заказ с номером {} на сумму {} ₽ уже оплачен'.format(payment.transaction_id, payment.amount))
		return redirect('results:my_payments')
	if payment.is_dummy:
		messages.success(request, u'Заказ с номером {} — ненастоящий. Его нельзя удалить.'.format(payment.transaction_id))
		return redirect('results:my_payments')
	if (not models.is_admin(request.user)) and (payment.user_id != request.user.id):
		user_club_ids = set(request.user.club_editor_set.values_list('club_id', flat=True))
		payment_participants_club_ids = set(payment.klb_participant_set.exclude(team=None).values_list('team__club_id', flat=True))
		if not (user_club_ids & payment_participants_club_ids):
			messages.warning(request, u'Заказ с номером {} — не Ваш. Оплатить его может только его создатель.'.format(payment.transaction_id))
			return redirect('results:my_payments')
	if 'btnDeletePayment' in request.POST:
		payment.is_active = False
		payment.save()
		payment.klb_participant_set.update(payment=None, wants_to_pay_zero=False)
		messages.success(request, u'Заказ с номером {} успешно удалён'.format(payment.transaction_id))
	return redirect('results:my_payments')

def send_success_mail(payment, response, participants_paid, participants_paid_before, medal_order):
	body = u' Добрый день!\n\nТолько что, {}, нам перевели {} рублей.'.format(localtime(response.added_time), response.withdraw_amount)

	body += u'\nЗачислено {} ₽. Комиссия: {} ₽ ({:.2f} %).'.format(response.get_amount(), -response.fee, 100 * (-response.fee) / response.withdraw_amount)

	if not payment.is_active:
		body += u'\n\nЧто-то странное: этот платёж неактивен. По идее такие нельзя оплатить!'

	if response.moneta_subscriber_id:
		user = User.objects.filter(pk=response.moneta_subscriber_id).first()
		profile = user.user_profile if (user and hasattr(user, 'user_profile')) else None
	else:
		user = None
		profile = None

	if profile:
		body += u'\n\nПользователь: {} {}{}'.format(user.get_full_name(), models.SITE_URL, profile.get_absolute_url())
	else:
		body += u'\n\nПользователь неизвестен (id {})'.format(response.moneta_subscriber_id)
		if payment and payment.sender:
			body += u'.\nПлательщик указал имя {}'.format(payment.sender)

	if payment:
		body += u'\n\nНазначение платежа: «{}»'.format(payment.description)
	else:
		body += u'\n\nНазначение платежа потерялось.'
		n_responses = models.Payment_moneta_response.objects.filter(transaction_id=response.transaction_id).count()
		if n_responses > 1:
			body += u'\nЭто уже поступление № {} с таким ID платежа на нашем сайте.'.format(n_responses)
		elif n_responses == 0:
			body += u'\nПока у нас просто не создавалось платежей с таким ID.'

	body += u'\n\nID платежа на нашем сайте: {}'.format(response.transaction_id)

	body += u'\n\nID операции у Монеты: {}'.format(response.moneta_operation_id)

	if response.is_signature_correct:
		body += u'\n\nПодпись операции подлинная.'
	else:
		body += u'\n\nПодпись операции неверная. Возможно, где-то рядом враги!'

	if participants_paid:
		if len(participants_paid) > 1:
			body += u'\n\nОплачено {} участников КЛБМатча:'.format(len(participants_paid))
		else: 
			body += u'\n\nОплачен один участник КЛБМатча:'
		for participant in participants_paid:
			team_name = participant.team.name if participant.team else u'индивидуальный участник'
			amount = models_klb.get_participation_price(participant.match_year) if (participant.paid_status == models.PAID_STATUS_FULL) else 0
			body += u'\n{} год, {} ₽, {}, {}, {}{}'.format(participant.match_year, amount, participant.klb_person.get_full_name_with_birthday(), team_name,
				models.SITE_URL, participant.klb_person.get_absolute_url())

	if participants_paid_before:
		body += u'\n\nПовторно заплатили за {} участников КЛБМатча, нужно разобраться:'.format(len(participants_paid_before))
		for participant in participants_paid_before:
			team_name = participant.team.name if participant.team else u'индивидуальный участник'
			body += u'\n{} год, {}, {}, {}{}'.format(participant.match_year, participant.klb_person.get_full_name_with_birthday(), team_name,
				models.SITE_URL, participant.klb_person.get_absolute_url())

	if medal_order:
		delivery_method = medal_order.delivery_method
		body += u'\n\nСпособ доставки: {}.'.format(medal_order.get_delivery_method_short())
		if delivery_method == 2:
			body += u'\nАдрес: {} {}.'.format(medal_order.zipcode, medal_order.address)
		if medal_order.email:
			body += u'\nE-mail: {}'.format(medal_order.email)
		if medal_order.phone_number:
			body += u'\nТелефон: {}'.format(medal_order.phone_number)
		if medal_order.comment:
			body += u'\nКомментарий: {}'.format(medal_order.comment)
		body += u'\n\nВсе платежи за медали: {}{}'.format(models.SITE_URL, reverse('editor:all_medal_payments'))

	if profile:
		body += u'\n\nВсе платежи этого пользователя ({}): {}{}'.format(user.payment_moneta_set.count(), models.SITE_URL, profile.get_all_payments_url())

	body += u'\n\nВообще все платежи: {}{}'.format(models.SITE_URL, reverse('editor:all_payments'))

	body += u'\n\nХорошего дня!\n\nВаш робот'
	message_from_site = models.Message_from_site.objects.create(
		sender_name=models.USER_ROBOT_CONNECTOR.get_full_name(),
		sender_email=models.ROBOT_MAIL_HEADER,
		target_email=models.TOP_MAIL,
		# target_email='alexey.chernov@gmail.com',
		title=u'ПроБЕГ: Проведена успешная оплата',
		body=body,
	)
	message_from_site.try_send(attach_file=False)

def send_sample_payment_email():
	payment = models.Payment_moneta.objects.get(pk=56)
	send_success_mail(payment, payment.response)

@csrf_exempt
def pay_url(request):
	to_return_ok = False
	try:
		params = request.POST if (request.method == 'POST') else request.GET

		models.write_log(u'At {} we received a response from Moneta. Method: {}. Params: {}'.format(timezone.now(), request.method, params))

		response = models.Payment_moneta_response.objects.create(
			account_number=params.get('MNT_ID', ''),
			transaction_id=params.get('MNT_TRANSACTION_ID', ''),
			moneta_operation_id=params.get('MNT_OPERATION_ID', ''),
			moneta_subscriber_id=params.get('MNT_SUBSCRIBER_ID', ''),
			moneta_user_account=params.get('MNT_USER', ''),
			moneta_user_corr_account=params.get('MNT_CORRACCOUNT', ''),
			payment_system=params.get('paymentSystem_unitId', ''),
			withdraw_amount=params.get('MNT_AMOUNT', 0),
			fee=params.get('MNT_FEE', 0),
			currency=params.get('MNT_CURRENCY_CODE', ''),
			is_test_mode=(params.get('MNT_TEST_MODE') == '1'),
			signature=params.get('MNT_SIGNATURE', ''),
			)
		response.refresh_from_db()
		response.is_signature_correct = (get_response_md5(response) == response.signature)
		response.save()

		payment = models.Payment_moneta.objects.filter(transaction_id=response.transaction_id).first()
		if payment is None:
			raise ValueError(u'Не найден платёж с id {}'.format(response.transaction_id))
		to_return_ok = True
		if payment.response:
			raise ValueError(u'Получено повторное сообщение об оплате платежа с id {}. Скорее всего, всё хорошо!'.format(response.transaction_id))

		payment.response = response
		payment.payment_time = timezone.now()
		payment.amount = response.withdraw_amount
		payment.withdraw_amount = response.withdraw_amount + response.fee
		payment.is_paid = True
		payment.save()

		participants_paid = []
		participants_paid_before = []
		medal_order = None

		for participant in payment.klb_participant_set.select_related('klb_person', 'team'):
			if participant.paid_status == models.PAID_STATUS_NO:
				participant.paid_status = models.PAID_STATUS_FREE if participant.wants_to_pay_zero else models.PAID_STATUS_FULL
				participant.wants_to_pay_zero = False
				participant.save()
				models.log_obj_create(payment.user, participant.klb_person, models.ACTION_KLB_PARTICIPANT_UPDATE, child_object=participant,
					field_list=['paid_status', 'wants_to_pay_zero'], comment=u'Платёж {}'.format(payment.id), verified_by=models.USER_ROBOT_CONNECTOR)
				participants_paid.append(participant)
			else:
				participants_paid_before.append(participant)

		if hasattr(payment, 'medal_order'):
			medal_order = payment.medal_order

		send_success_mail(payment, response, participants_paid, participants_paid_before, medal_order)
	except Exception as e:
		send_mail(
			'Problem with receiving a payment',
			u'At {} we received a response from Moneta.\n\nMethod:{}\nParams:{}\nException:{}\n\n Your robot'.format(
				timezone.now(), request.method, params, unicode(e.message if hasattr(e, 'message') else '')),
			models.ROBOT_MAIL_HEADER,
			# ['alexey.chernov@gmail.com'],
			['top@probeg.org'],
			fail_silently=True,
		)
	return HttpResponse(u'SUCCESS' if to_return_ok else u'FAIL', content_type='text/plain')

@csrf_exempt
def pay_url_tmp(request):
		params = request.POST if (request.method == 'POST') else request.GET

		models.write_log(u'At {} we received a response from Moneta. Method: {}. Params: {}'.format(timezone.now(), request.method, params))

		response = models.Payment_moneta_response.objects.create(
			account_number=params.get('MNT_ID', ''),
			transaction_id=params.get('MNT_TRANSACTION_ID', ''),
			moneta_operation_id=params.get('MNT_OPERATION_ID', ''),
			moneta_subscriber_id=params.get('MNT_SUBSCRIBER_ID', ''),
			moneta_user_account=params.get('MNT_USER', ''),
			moneta_user_corr_account=params.get('MNT_CORRACCOUNT', ''),
			payment_system=params.get('paymentSystem_unitId', ''),
			withdraw_amount=params.get('MNT_AMOUNT', 0),
			fee=params.get('MNT_FEE', 0),
			currency=params.get('MNT_CURRENCY_CODE', ''),
			is_test_mode=(params.get('MNT_TEST_MODE') == '1'),
			signature=params.get('MNT_SIGNATURE', ''),
			)
		response.refresh_from_db()
		response.is_signature_correct = (get_response_md5(response) == response.signature)
		response.save()

		payment = models.Payment_moneta.objects.filter(transaction_id=response.transaction_id).first()
		if payment is None:
			raise ValueError(u'Не найден платёж с id {}'.format(response.transaction_id))
		to_return_ok = True
		if payment.response:
			raise ValueError(u'Получено повторное сообщение об оплате платежа с id {}. Скорее всего, всё хорошо!'.format(response.transaction_id))

		payment.response = response
		payment.payment_time = timezone.now()
		payment.amount = response.withdraw_amount
		payment.withdraw_amount = response.withdraw_amount + response.fee
		payment.is_paid = True
		payment.save()

		participants_paid = []
		participants_paid_before = []
		medal_order = None

		for participant in payment.klb_participant_set.select_related('klb_person', 'team'):
			if participant.paid_status == models.PAID_STATUS_NO:
				participant.paid_status = models.PAID_STATUS_FREE if participant.wants_to_pay_zero else models.PAID_STATUS_FULL
				participant.wants_to_pay_zero = False
				participant.save()
				models.log_obj_create(payment.user, participant.klb_person, models.ACTION_KLB_PARTICIPANT_UPDATE, child_object=participant,
					field_list=['paid_status', 'wants_to_pay_zero'], comment=u'Платёж {}'.format(payment.id), verified_by=models.USER_ROBOT_CONNECTOR)
				participants_paid.append(participant)
			else:
				participants_paid_before.append(participant)

		if hasattr(payment, 'medal_order'):
			medal_order = payment.medal_order

		send_success_mail(payment, response, participants_paid, participants_paid_before, medal_order)
		return HttpResponse(u'SUCCESS' if to_return_ok else u'FAIL', content_type='text/plain')

def success(request):
	payment = None
	transaction_id = request.GET.get('MNT_TRANSACTION_ID')
	if transaction_id and transaction_id.startswith(DESCRIPTION_PREFIX):
		payment = models.Payment_moneta.objects.filter(transaction_id=transaction_id).first()
	message = u'Оплата Вашего заказа прошла, мы ждём подтверждения от процессингового центра. Спасибо!'
	if payment:
		n_participants = payment.klb_participant_set.count()
		if n_participants > 1:
			if payment.is_paid:
				message = u'Вы успешно оплатили участие в КЛБМатче за {} человек. Пора стартовать!'.format(n_participants)
			messages.success(request, message)
			return redirect(payment.klb_participant_set.first().team)
		if n_participants == 1:
			if payment.is_paid:
				message = u'Вы успешно оплатили участие в КЛБМатче. Пора стартовать!'
			messages.success(request, message)
			return redirect(payment.klb_participant_set.first().klb_person)
		if payment.is_paid:
			message = u'Ваш заказ успешно оплачен. Спасибо!'
	messages.success(request, message)
	return redirect('results:my_payments' if request.user.is_authenticated() else 'results:main_page')

@login_required
def fail(request):
	context = user_edit_vars(request.user)
	payment = None
	transaction_id = request.GET.get('MNT_TRANSACTION_ID')
	if transaction_id:
		context['payment'] = models.Payment_moneta.objects.filter(transaction_id=transaction_id, user=request.user).first()
	context['user_has_payments'] = request.user.payment_moneta_set.exists()
	context['page_title'] = u'Платёж не прошёл'
	return render(request, "payment/fail.html", context)

@login_required
def in_progress(request):
	messages.success(request, u'Мы ждём подтверждения оплаты заказа от процессингового центра. Спасибо!')
	return redirect('results:my_payments')

@login_required
def return_url(request):
	return redirect('results:my_payments')

@login_required
def my_payments(request):
	context = user_edit_vars(request.user)
	context['page_title'] = u'Все Ваши платежи'
	context['payments'] = request.user.payment_moneta_set.select_related('response').order_by('-added_time')
	if not context['is_admin']:
		context['payments'] = context['payments'].filter(is_active=True)
	return render(request, "payment/my_payments.html", context)
