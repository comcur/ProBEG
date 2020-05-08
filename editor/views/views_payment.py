# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.models import User
from django.http import FileResponse
from django.contrib import messages
from django.db.models import Q, Sum, Count, Case, When, IntegerField
import datetime
import xlsxwriter

from results import models
from results.models_klb import get_participation_price
from views_common import group_required

def create_report(start_date=None, end_date=None):
	now = datetime.datetime.now()
	fname = models.XLSX_FILES_DIR + '/probeg_payment_report_{}.xlsx'.format(datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
	workbook = xlsxwriter.Workbook(fname)
	worksheet = workbook.add_worksheet()
	bold = workbook.add_format({'bold': True})
	number_format = workbook.add_format({'num_format': '0.00'})

	payments = models.Payment_moneta.objects.select_related('response', 'user__user_profile').order_by('-added_time')

	title = u'Все платежи на ПроБЕГе'
	if start_date:
		title += u' с {}'.format(start_date.strftime('%Y-%m-%d'))
		payments = payments.filter(added_time__gte=start_date)
	if end_date:
		title += u' по {}'.format(end_date.strftime('%Y-%m-%d'))
		payments = payments.filter(added_time__lt=end_date + datetime.timedelta(days=1))
	worksheet.write(0, 0, title)
	# worksheet.write(1, 0, unicode(payments.query))

	row = 2

	worksheet.write(row, 0, u'№', bold)
	worksheet.write(row, 1, u'ID', bold)
	worksheet.write(row, 2, u'Время создания', bold)
	worksheet.write(row, 3, u'Время оплаты', bold)
	worksheet.write(row, 4, u'Имя отправителя', bold)
	worksheet.write(row, 5, u'Страница пользователя', bold)
	worksheet.write(row, 6, u'Описание', bold)
	worksheet.write(row, 7, u'Поступило', bold)
	worksheet.write(row, 8, u'Получено', bold)
	worksheet.write(row, 9, u'Комиссия, %', bold)
	worksheet.write(row, 10, u'Оплачен?', bold)

	worksheet.set_column(0, 1, 3.29)
	worksheet.set_column(2, 3, 17.29)
	worksheet.set_column(4, 5, 31.86)
	worksheet.set_column(6, 6, 40)
	worksheet.set_column(7, 8, 10)
	worksheet.set_column(9, 9, 11.57)
	worksheet.set_column(10, 10, 9.29)

	# Iterate over the data and write it out row by row.
	for i, payment in enumerate(payments):
		row += 1
		worksheet.write(row, 0, i + 1)
		worksheet.write(row, 1, payment.id)
		worksheet.write(row, 2, payment.added_time.strftime('%d.%m.%Y %H:%M:%S'))
		if payment.response:
			worksheet.write(row, 3, payment.response.added_time.strftime('%d.%m.%Y %H:%M:%S'))
		worksheet.write(row, 4, payment.sender)
		if payment.user and hasattr(payment.user, 'user_profile'):
			worksheet.write(row, 5, models.SITE_URL + payment.user.user_profile.get_absolute_url())
		worksheet.write(row, 6, payment.description)
		worksheet.write(row, 7, payment.amount, number_format)
		worksheet.write(row, 8, payment.withdraw_amount, number_format)
		worksheet.write(row, 9, payment.get_fee_percent().replace('.', ','), number_format)
		worksheet.write(row, 10, u'да' if payment.is_paid else u'нет')

	row += 2
	good_payments = payments.filter(is_paid=True).aggregate(Sum('withdraw_amount'), Sum('amount'))

	worksheet.write(row, 5, u'Всего по оплаченным платежам:', bold)
	worksheet.write(row, 7, good_payments['amount__sum'], bold)
	worksheet.write(row, 8, good_payments['withdraw_amount__sum'], bold)

	workbook.close()
	return fname

@group_required('admins')
def all_payments(request, user_id=None):
	if 'btnCreateReport' in request.POST:
		start_date = None
		if request.POST.get('start_date'):
			start_date = datetime.datetime.strptime(request.POST.get('start_date'), '%Y-%m-%d').date()
		end_date = None
		if request.POST.get('end_date'):
			end_date = datetime.datetime.strptime(request.POST.get('end_date'), '%Y-%m-%d').date()

		fname = create_report(start_date=start_date, end_date=end_date)
		# messages.success(request, u'Файл {} создан'.format(fname.split('/')[-1]))
		response = FileResponse(open(fname, 'rb'), content_type='application/vnd.ms-excel')
		response['Content-Disposition'] = 'attachment; filename="{}"'.format(fname.split('/')[-1])
		return response

	context = {}
	user = None
	if user_id:
		user = get_object_or_404(User, pk=user_id)

	# context['payments'] = models.Payment_moneta.objects.filter(pk__gte=60).select_related('response', 'user').order_by('-added_time')
	price = get_participation_price(models.CUR_KLB_YEAR)
	context['payments'] = models.Payment_moneta.objects.select_related('response', 'user').annotate(
		Count('klb_participant'),
		n_participants_paid=price*Count(Case(When(klb_participant__paid_status=models.PAID_STATUS_FULL, then=1), output_field=IntegerField()))
    ).order_by('-added_time')

	context['show_unpaid_payments'] = ('show_unpaid_payments' in request.POST) or (user_id and (request.method == 'GET'))
	if not context['show_unpaid_payments']:
		context['payments'] = context['payments'].filter(is_paid=True, added_time__gte=datetime.date(2018, 12, 1))

	if user:
		context['page_title'] = u'Все платежи пользователя {}'.format(user.get_full_name())	
		context['cur_user'] = user
		context['payments'] = context['payments'].filter(user=user)
	else:
		context['page_title'] = u'Вообще все платежи'

	return render(request, "editor/payment/all_payments.html", context)

@group_required('admins')
def all_medal_payments(request):
	if 'btnCreateReport' in request.POST:
		start_date = None
		if request.POST.get('start_date'):
			start_date = datetime.datetime.strptime(request.POST.get('start_date'), '%Y-%m-%d').date()
		end_date = None
		if request.POST.get('end_date'):
			end_date = datetime.datetime.strptime(request.POST.get('end_date'), '%Y-%m-%d').date()

		fname = create_report(start_date=start_date, end_date=end_date)
		# messages.success(request, u'Файл {} создан'.format(fname.split('/')[-1]))
		response = FileResponse(open(fname, 'rb'), content_type='application/vnd.ms-excel')
		response['Content-Disposition'] = 'attachment; filename="{}"'.format(fname.split('/')[-1])
		return response

	context = {}

	# context['payments'] = models.Payment_moneta.objects.filter(pk__gte=60).select_related('response', 'user').order_by('-added_time')
	context['medal_orders'] = models.Medal_order.objects.select_related('payment__response', 'created_by').order_by('-created_time')

	# context['show_unpaid_medal_orders'] = ('show_unpaid_medal_orders' in request.POST) or (user_id and (request.method == 'GET'))
	# if not context['show_unpaid_medal_orders']:
	# 	context['medal_orders'] = context['medal_orders'].filter(is_paid=True, added_time__gte=datetime.date(2018, 12, 1))

	context['page_title'] = u'Все заказы медалей'
	return render(request, "editor/payment/all_medal_payments.html", context)

@group_required('admins')
def payment_add_participant(request, payment_id):
	if 'btnAddParticipant' in request.POST:
		payment = get_object_or_404(models.Payment_moneta, pk=payment_id)
		participant_id = models.int_safe(request.POST.get('select_participant'))
		participant = get_object_or_404(models.Klb_participant, pk=participant_id)
		person = participant.klb_person
		year = participant.match_year

		if not models.is_active_klb_year(year):
			messages.warning(request, u'Сейчас нельзя менять платежи за {} год'.format(year))
		elif participant.payment_id:
			messages.warning(request, u'Участник {} за {} год уже привязан к платежу с id {}'.format(person, year, participant.payment_id))
		elif not payment.is_paid:
			messages.warning(request, u'Платёж с id {} ещё не оплачен. Такие редактировать нельзя'.format(payment.id))
		elif participant.paid_status != models.PAID_STATUS_NO:
			messages.warning(request, u'Участник {} за {} год и так помечен как оплативший участие. Что-то не то'.format(person, year))
		else:
			participant.payment = payment
			participant.is_paid_through_site = False
			amount_str = request.POST.get('amount')
			if amount_str == '0':
				participant.paid_status = models.PAID_STATUS_FREE
				participant.save()
				models.log_obj_create(request.user, person, models.ACTION_KLB_PARTICIPANT_UPDATE, child_object=participant,
					field_list=['payment', 'is_paid_through_site', 'paid_status'], comment=u'Добавлен к платежу {}'.format(payment.id),
					verified_by=models.USER_ROBOT_CONNECTOR)
				messages.success(request, u'Участник {} за {} год добавлен к платежу как участвующий бесплатно'.format(person, year))
			else:
				amount = models.int_safe(amount_str)
				if amount == get_participation_price(year):
					participant.paid_status = models.PAID_STATUS_FULL
					participant.save()
					models.log_obj_create(request.user, person, models.ACTION_KLB_PARTICIPANT_UPDATE, child_object=participant,
						field_list=['payment', 'is_paid_through_site', 'paid_status'], comment=u'Добавлен к платежу {}'.format(payment.id),
						verified_by=models.USER_ROBOT_CONNECTOR)
					messages.success(request, u'Участник {} за {} год добавлен к платежу как участвующий за полную стоимость'.format(person, year))
				else:
					messages.warning(request, u'Участник {} за {} год не привязан к платежу: недопустимая цена участия {}'.format(person, year, amount))
	return redirect(payment)

@group_required('admins')
def payment_details(request, payment_id):
	payment = get_object_or_404(models.Payment_moneta, pk=payment_id)
	context = {}
	context['payment'] = payment
	context['page_title'] = u'Платёж № {}'.format(payment_id)
	context['participants'] = payment.klb_participant_set.select_related('klb_person', 'team').order_by('klb_person__lname', 'klb_person__fname')
	context['CUR_KLB_YEAR'] = models.CUR_KLB_YEAR
	context['price'] = get_participation_price(models.CUR_KLB_YEAR)
	context['participants_amount_sum'] = context['participants'].filter(paid_status=models.PAID_STATUS_FULL).count() * context['price']

	return render(request, "editor/payment/payment_details.html", context)

@group_required('admins')
def payment_delete_participant(request, payment_id, participant_id):
	if 'btnDeleteParticipant' in request.POST:
		payment = get_object_or_404(models.Payment_moneta, pk=payment_id)
		participant = get_object_or_404(models.Klb_participant, pk=participant_id)
		person = participant.klb_person
		year = participant.match_year

		if not models.is_active_klb_year(year):
			messages.warning(request, u'Сейчас нельзя менять платежи за {} год'.format(year))
		elif participant.payment_id is None:
			messages.warning(request, u'Участник {} за {} год пока не привязан ни к какому платежу'.format(person, year))
		elif participant.payment_id != payment.id:
			messages.warning(request, u'Участник {} за {} год привязан к другому платежу — с id {}'.format(person, year, participant.payment_id))
		elif participant.is_paid_through_site:
			messages.warning(request, u'Участник {} за {} год входил в этот платёж при оплате через сайт. Такого нельзя удалить'.format(person, year))
		elif not payment.is_paid:
			messages.warning(request, u'Платёж с id {} ещё не оплачен. Такие редактировать нельзя'.format(payment.id))
		elif participant.paid_status == models.PAID_STATUS_NO:
			messages.warning(request, u'Участник {} за {} год и так помечен как не оплачивавший участие. Что-то не то'.format(person, year))
		else:
			participant.paid_status = models.PAID_STATUS_NO
			participant.payment = None
			participant.save()
			models.log_obj_create(request.user, person, models.ACTION_KLB_PARTICIPANT_UPDATE, child_object=participant,
				field_list=['payment', 'paid_status'], comment=u'Удалён из платежа {}'.format(payment.id), verified_by=models.USER_ROBOT_CONNECTOR)
			messages.success(request, u'Участник {} за {} год удалён из этого платежа'.format(person, year))
	return redirect(payment)

@group_required('admins')
def payment_delete(request, payment_id):
	if 'btnDeletePayment' not in request.POST:
		return redirect(payment)
	payment = get_object_or_404(models.Payment_moneta, pk=payment_id)
	if not payment.is_dummy:
		messages.warning(request, u'Можно удалить только фиктивные платежи')
		return redirect(payment)
	if payment.klb_participant_set.exists():
		messages.warning(request, u'Нельзя удалить платёж, к которому привязаны участники КЛБМатча')
		return redirect(payment)
	messages.success(request, u'Платёж «{}» (id {}) успешно удалён'.format(payment.description, payment.id))
	payment.delete()
	return redirect('editor:all_payments')

@group_required('admins')
def payment_create(request):
	if 'btnCreatePayment' in request.POST:
		description = request.POST.get('description', '').strip()
		if len(description) < 5:
			messages.warning(request, u'Слишком короткое описание платежа: «{}». Ничего не создаём'.format(description))
		else:
			amount = models.int_safe(request.POST.get('amount'))
			payment = models.Payment_moneta.objects.create(
				amount=amount,
				withdraw_amount=amount,
				is_dummy=True,
				is_paid=True,
				user=request.user,
				description=description,
			)
			payment.transaction_id = models.PAYMENT_DUMMY_PREFIX + unicode(payment.id)
			payment.save()
			messages.success(request, u'Новый платёж успешно создан')
		return redirect(payment)
	return redirect('editor:all_payments')

def add_participants_to_payment():
	payment_id = 644
	team_id = 1001
	payment = models.Payment_moneta.objects.get(pk=payment_id)
	team = models.Klb_team.objects.get(pk=team_id)
	# n_slots = 40
	# for participant in team.klb_participant_set.filter(paid_status=models.PAID_STATUS_NO)[:n_slots]:
	# 	participant.payment = payment
	# 	participant.is_paid_through_site=False
	# 	participant.paid_status = models.PAID_STATUS_FULL
	# 	participant.save()
	n_updated = team.klb_participant_set.filter(paid_status=models.PAID_STATUS_NO).update(payment=payment,
		is_paid_through_site=False, paid_status=models.PAID_STATUS_FULL)
	print(n_updated)
	# team = models.Klb_team.objects.get(pk=874)
	# team.klb_participant_set.update(payment=payment, is_paid_through_site=False, paid_status=models.PAID_STATUS_FULL)
