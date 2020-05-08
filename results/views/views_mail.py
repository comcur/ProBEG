# -*- coding: utf-8 -*-
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.core.mail import EmailMessage, send_mail
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.http import HttpResponse
import json

from results import models, forms, results_util
from .views_common import get_first_form_error
from editor.views.views_user_actions import log_form_change
from editor.views.views_common import group_required
from editor.views.views_stat import update_events_count, generate_last_added_reviews
from editor.views.views_parkrun import create_future_parkruns, PARKRUN_DISTANCE

def get_send_to_info_page(request):
	context = {}
	context['form'] = forms.MessageToInfoForm(request)
	return render(request, "results/modal_letter_to_info.html", context)

@group_required('admins')
def get_send_from_info_page(request, table_update_id=None, event_id=None,
		event_participants_id=None, event_wo_protocols_id=None, user_id=None, wrong_club=None):
	context = {}
	table_update = get_object_or_404(models.Table_update, pk=table_update_id) if table_update_id else None
	event = get_object_or_404(models.Event, pk=event_id) if event_id else None
	to_participants = False
	wo_protocols = False
	wrong_club = (wrong_club is not None)
	if event_participants_id:
		event = get_object_or_404(models.Event, pk=event_participants_id)
		to_participants = True
	elif event_wo_protocols_id:
		event = get_object_or_404(models.Event, pk=event_wo_protocols_id)
		wo_protocols = True
	user = get_object_or_404(User, pk=user_id) if user_id else None
	context['form'] = forms.MessageFromInfoForm(request=request, table_update=table_update, event=event, user=user,
		to_participants=to_participants, wo_protocols=wo_protocols, wrong_club=wrong_club)
	if table_update_id:
		context['table_update_id'] = table_update_id
	return render(request, "results/modal_letter_from_info.html", context)

@login_required
def get_add_event_page(request, series_id):
	context = {}
	context['series'] = get_object_or_404(models.Series, pk=series_id)
	context['frmEvent'] = forms.UnofficialEventForm
	return render(request, "results/modal_add_event.html", context)

@login_required
def get_add_series_page(request):
	context = {}
	context['frmSeries'] = forms.UnofficialSeriesForm
	return render(request, "results/modal_add_series.html", context)

@login_required
def get_add_review_page(request, event_id, photo=0):
	context = {}
	context['event'] = get_object_or_404(models.Event, pk=event_id)
	initial = {'event_id': int(event_id), 'author': request.user.get_full_name()}
	initial['doc_type'] = models.DOC_TYPE_PHOTOS if photo else models.DOC_TYPE_IMPRESSIONS
	context['form'] = forms.AddReviewForm(initial=initial)
	return render(request, "results/modal_add_review.html", context)

def create_distances_from_raw(user, event):
	for distance_raw in event.distances_raw.split(','):
		_, distance = models.Distance.try_parse_distance(distance_raw.strip(u' ."«»').lower())
		if distance and not event.race_set.filter(distance=distance).exists():
			race = models.Race(
				event=event,
				created_by=user,
				distance=distance,
			)
			race.clean()
			race.save()
			models.log_obj_create(user, event, models.ACTION_RACE_CREATE, child_object=race)

@login_required
def add_unofficial_event(request, series_id):
	series = get_object_or_404(models.Series, pk=series_id)
	context = {}
	message_text = ''
	res = {}
	res['success'] = 0
	if request.method == 'POST':
		user = request.user
		form = forms.UnofficialEventForm(request.POST, instance=models.Event(series=series, created_by=user))
		if form.is_valid():
			event = form.save()
			event.clean()
			event.save()
			update_events_count()
			log_form_change(user, form, action=models.ACTION_CREATE)
			res['success'] = 1
			create_distances_from_raw(user, event)
			message_from_site = models.Message_from_site.objects.create(
				sender_name=user.first_name + ' ' + user.last_name,
				sender_email=models.ROBOT_MAIL_HEADER,
				target_email=models.INFO_MAIL, #  'alexey.chernov@gmail.com',
				title=u'Создан новый забег: {} ({})'.format(event.name, event.date(with_nobr=False)),
				attachment=request.FILES.get('attachment', None),
			)
			body = (u'Только что пользователь {} ({}{}, {}) создал новый забег.\n\n'
				+ u'Название: {}\nСтраница забега: {}{}\n'
				+ u'Серия: {} ({}{})\nДата проведения: {}\nСайт забега: {}\n'
				+ u'Дистанции: {}\nКомментарий (виден только администраторам): «{}»\n\n').format(
				user.get_full_name(), models.SITE_URL, user.user_profile.get_absolute_url(), user.email,
				event.name, models.SITE_URL, event.get_absolute_url(), event.series.name, models.SITE_URL, event.series.get_absolute_url(),
				event.date(with_nobr=False), event.url_site, event.distances_raw, event.comment_private,
				)
			if event.race_set.exists():
				body += u'Были распознаны и автоматически добавлены следующие дистанции: {}. \n\n'.format(
					', '.join(race.distance.name for race in event.race_set.order_by('distance__distance_type', '-distance__length')))
			if message_from_site.attachment:
				body += u'Также пользователь приложил файл {}/{} размером {} байт. \n\n'.format(
					models.SITE_URL_OLD, message_from_site.attachment.name, message_from_site.attachment.size)
			body += u'Теперь нужно:\n1. На странице {}{} одобрить добавленный пробег;\n'.format(
				models.SITE_URL, reverse('editor:action_history'))
			if message_from_site.attachment:
				body +=  (u'2. На странице редактирования забега {}{} '
					+ u'добавить недостающие дистанции и приложить документы.\n\n').format(models.SITE_URL, event.get_editor_url())
			else:
				body +=  (u'2. На странице редактирования забега {}{} '
					+ u'добавить недостающие дистанции.\n\n').format(models.SITE_URL, event.get_editor_url())
			body += u'Удачных стартов!\nВаш робот'
			message_from_site.body = body
			message_from_site.save()
			message_from_site.try_send(attach_file=False)
		else:
			res['error'] = get_first_form_error(form)
	else:
		res['error'] = u'Запрос не получен.'
	return HttpResponse(json.dumps(res), content_type='application/json')

@login_required
def add_unofficial_series(request):
	context = {}
	message_text = ''
	res = {}
	res['success'] = 0
	if request.method == 'POST':
		user = request.user
		user_is_editor = user.groups.filter(name="editors").exists()
		form = forms.UnofficialSeriesForm(request.POST, instance=models.Event(series=models.Series(), created_by=user))
		if form.is_valid():
			event = form.save()
			event.city = None
			event.surface_type = models.SURFACE_DEFAULT
			event.source = u'Через форму «Добавить серию» на сайте'
			event.clean()
			event.save()

			series = event.series
			update_events_count()
			log_form_change(user, form, action=models.ACTION_CREATE)
			res['success'] = 1
			create_distances_from_raw(user, event)

			if series.is_russian_parkrun() and user_is_editor and event.race_set.count() == 1 and event.race_set.all()[0] == PARKRUN_DISTANCE:
				n_created_parkruns = create_future_parkruns(series, models.USER_ROBOT_CONNECTOR)

			res['link'] = models.SITE_URL + series.get_absolute_url()
			message_from_site = models.Message_from_site.objects.create(
				sender_name=user.first_name + ' ' + user.last_name,
				sender_email=models.ROBOT_MAIL_HEADER,
				target_email=models.INFO_MAIL,
				# target_email='alexey.chernov@gmail.com',
				title=u'Созданы новая серия и новый забег: {} ({})'.format(event.name, event.date(with_nobr=False)),
				attachment=request.FILES.get('attachment', None),
			)
			body = (u'Только что пользователь {} ({}{}) создал новую серию и забег в ней.\n\n'
				+ u'Название: {}\nГород: {}\nСтраница серии: {}{}\n'
				+ u'Дата проведения: {}\nСайт забега: {}\n'
				+ u'Дистанции: {}\nКомментарий (виден только администраторам): «{}»\n\n').format(
				user.get_full_name(), models.SITE_URL, user.user_profile.get_absolute_url(), 
				event.name, event.strCityCountry(with_nbsp=False), models.SITE_URL, series.get_absolute_url(),
				event.date(with_nobr=False), event.url_site, event.distances_raw, event.comment_private,
				)
			if event.race_set.exists():
				body += u'Были распознаны и автоматически добавлены следующие дистанции: {}.\n\n'.format(
					', '.join(race.distance.name for race in event.race_set.order_by('distance__distance_type', '-distance__length')))
			if message_from_site.attachment:
				body += u'Также пользователь приложил файл {}/{} размером {} байт.\n\n'.format(
					models.SITE_URL_OLD, message_from_site.attachment.name, message_from_site.attachment.size)
			if form.cleaned_data.get('i_am_organizer'):
				body += u'Пользователь указал, что является организатором забега. Ему выданы права на редактирование забега.\n\n'.format()
			body += u'Теперь нужно:\n1. На странице {}{} одобрить добавленные пробег и серию;\n'.format(
				models.SITE_URL, reverse('editor:action_history'))
			if message_from_site.attachment:
				body += u'2. На странице редактирования забега {}{} добавить недостающие дистанции и приложить документы.\n\n'.format(
					models.SITE_URL, event.get_editor_url())
			else:
				body += u'2. На странице редактирования забега {}{} добавить недостающие дистанции.\n\n'.format(models.SITE_URL, event.get_editor_url())
			body += u'Удачных стартов!\nВаш робот'
			message_from_site.body = body
			message_from_site.save()
			message_from_site.try_send(attach_file=False)
		else:
			res['error'] = get_first_form_error(form)
	else:
		res['error'] = u'Запрос не получен.'
	return HttpResponse(json.dumps(res), content_type='application/json')

def send_message(request):
	context = {}
	result = {}
	result['success'] = 0
	if request.method == 'POST':
		form = forms.MessageToInfoForm(request, request.POST, request.FILES)
		if form.is_valid():
			message_from_site = form.save()
			result = message_from_site.try_send()
		else:
			result['error'] = get_first_form_error(form)
	else:
		result['error'] = u'Запрос не получен.'
	return HttpResponse(json.dumps(result), content_type='application/json')

@group_required('admins')
def send_message_admin(request):
	context = {}
	result = {}
	result['success'] = 0
	if request.method == 'POST':
		form = forms.MessageFromInfoForm(request.POST, request.FILES, request=request)
		if form.is_valid():
			message_from_site = form.save()
			result = message_from_site.try_send()
			result['targets'] = message_from_site.target_email
		else:
			result['error'] = get_first_form_error(form)
	else:
		result['error'] = u'Запрос не получен.'
	return HttpResponse(json.dumps(result), content_type='application/json')

@login_required
def add_review(request):
	context = {}
	message_text = ''
	res = {}
	res['success'] = 0
	if request.method == 'POST':
		user = request.user
		form = forms.AddReviewForm(request.POST, request.FILES)
		if form.is_valid():
			event = get_object_or_404(models.Event, pk=form.cleaned_data['event_id'])
			attachment = request.FILES.get('attachment', None)
			doc_type = results_util.int_safe(form.cleaned_data['doc_type'])
			doc_type_name = u'отчёт' if doc_type == models.DOC_TYPE_IMPRESSIONS else u'фотоальбом'
			doc = models.Document.objects.create(
				event=event,
				document_type=doc_type,
				loaded_type=models.LOAD_TYPE_LOADED if attachment else models.LOAD_TYPE_NOT_LOADED,
				upload=attachment,
				url_original=form.cleaned_data['url'],
				author=form.cleaned_data['author'],
				created_by=user
			)
			models.log_obj_create(user, event, models.ACTION_DOCUMENT_CREATE, child_object=doc)
			doc.process_review_or_photo()
			generate_last_added_reviews()
			res['success'] = 1
			res['link'] = models.SITE_URL + event.get_absolute_url()

			if not models.is_admin(user):
				message_from_site = models.Message_from_site.objects.create(
					sender_name=user.first_name + ' ' + user.last_name,
					sender_email=models.ROBOT_MAIL_HEADER,
					target_email=models.INFO_MAIL,
					# target_email='alexey.chernov@gmail.com',
					title=u'Добавлен новый {} к забегу {} ({})'.format(doc_type_name, event.name, event.date(with_nobr=False)),
					attachment=attachment,
				)
				if attachment:
					body = u'Только что пользователь {} ({}{}) добавил на сайт отчёт к забегу «{}»:\n\n {}/{}\n\n'.format(
						user.get_full_name(), models.SITE_URL, user.user_profile.get_absolute_url(), unicode(event),
						models.SITE_URL_OLD, message_from_site.attachment.name)
				else:
					body = u'Только что пользователь {} ({}{}) добавил на сайт ссылку на {} к забегу «{}»:\n{}\n\n'.format(
						user.get_full_name(), models.SITE_URL, user.user_profile.get_absolute_url(),
						doc_type_name, unicode(event), form.cleaned_data['url'])
				body += u'Все документы забега: {}{}\n\n'.format(models.SITE_URL, event.get_absolute_url())
				body += u'Успешных стартов!\nВаш робот'
				message_from_site.body = body
				message_from_site.save()
				message_from_site.try_send(attach_file=False)
		else:
			res['error'] = get_first_form_error(form)
	else:
		res['error'] = u'Запрос не получен.'
	return HttpResponse(json.dumps(res), content_type='application/json')