# -*- coding: utf-8 -*-
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect
from django.core.files.temp import NamedTemporaryFile
from django.template.loader import render_to_string
from django.shortcuts import render, redirect
from django.db.models.query import Prefetch
from django.contrib import messages
from django.core.files import File
from django.conf import settings
from django.db.models import Q, Count
import datetime
import io
import os

from results import models
from results.views.views_common import user_edit_vars
from results.results_util import read_url

def group_required(*group_names):
	"""Requires user membership in at least one of the groups passed in."""
	def in_groups(user):
		if user.is_authenticated:
			if user.groups.filter(name__in=group_names).exists() | user.is_superuser:
				return True
		return False
	return user_passes_test(in_groups)

# Update field_name in model from value_old to value_new and update args_to_update
def update_fields(request, model, field_name, old_value, new_value, args_to_update):
	kwargs = {field_name: old_value}
	query = model.objects.filter(**kwargs)
	if old_value != new_value:
		user_is_admin = models.is_admin(request.user)
		for row in query:
			table_update = models.Table_update.objects.create(model_name=model.__name__, row_id=row.id,
				action_type=models.ACTION_UPDATE, user=request.user, is_verified=user_is_admin)
			for key, val in args_to_update.items():
				if getattr(row, key) != val:
					models.Field_update.objects.create(table_update=table_update, field_name=key, new_value=val)
	n_rows = query.update(**args_to_update)
	if n_rows > 0:
		messages.success(request, u'Пол{} {} в таблице {} исправлен{} у {} записей.'.format(
			u'я' if len(args_to_update) else u'е',
			", ".join([field_name] + [key for key, val in args_to_update.items()]),
			model._meta.db_table,
			u'ы' if len(args_to_update) else u'о',
			n_rows))

def update_city(request, city_old, city_new=None):
	if city_new is None:
		city_new = city_old
	args = {}
	if city_old != city_new:
		args['city'] = city_new
		update_fields(request, models.Series, 'city_finish', city_old, city_new, {'city_finish': city_new})
		update_fields(request, models.Event, 'city_finish', city_old, city_new, {'city_finish': city_new})
		update_fields(request, models.User_profile, 'city', city_old, city_new, args)
		update_fields(request, models.City_conversion, 'city', city_old, city_new, args)
		update_fields(request, models.Runner, 'city', city_old, city_new, args)
		# update_fields(request, models.Result, 'city', city_old, city_new, args) Not used yet
	args['country_raw'] = city_new.region.country.name
	args['region_raw'] = city_new.region.name if city_new.region.country.has_regions else ''
	args['city_raw'] = city_new.name_full()
	update_fields(request, models.Club, 'city', city_old, city_new, args)

	args['district_raw'] = city_new.region.district.name if (city_new.region.district is not None) else ''
	update_fields(request, models.Series, 'city', city_old, city_new, args)
	update_fields(request, models.Event, 'city', city_old, city_new, args)
	update_fields(request, models.Klb_person, 'city', city_old, city_new, args)

def update_distance(request, distance_old, distance_new=None):
	if distance_new is None:
		distance_new = distance_old
	args = {}
	if distance_old != distance_new:
		args['distance'] = distance_new
	args['distance_raw'] = distance_new.distance_raw
	args['race_type_raw'] = distance_new.race_type_raw
	update_fields(request, models.Race, 'distance', distance_old, distance_new, args)

def update_series(request, series_old, series_new):
	args = {'series': series_new}
	update_fields(request, models.Event, 'series', series_old, series_new, args)
	update_fields(request, models.Series_editor, 'series', series_old, series_new, args)
	update_fields(request, models.Document, 'series', series_old, series_new, args)
	models.Race.objects.filter(event__series=series_new).update(series_raw=series_new.id)
	models.Photo.objects.filter(event__series=series_new).update(series_raw=series_new.id)
	models.Review.objects.filter(event__series=series_new).update(series_raw=series_new.id)

def update_event(request, event_old, event_new):
	args = {'event': event_new}
	update_fields(request, models.Race, 'event', event_old, event_new, args)
	update_fields(request, models.News, 'event', event_old, event_new, args)
	update_fields(request, models.Document, 'event', event_old, event_new, args)
	if event_new != event_old:
		args['series_raw'] = event_new.series.id
	update_fields(request, models.Review, 'event', event_old, event_new, args)
	update_fields(request, models.Photo, 'event', event_old, event_new, args)

	update_fields(request, models.Klb_result, 'event_raw', event_old, event_new, {'event_raw': event_new})

def update_organizer(request, organizer_old, organizer_new):
	args = {'organizer': organizer_new}
	update_fields(request, models.Series, 'organizer', organizer_old, organizer_new, args)

def update_runner(request, creator, runner_old, runner_new):
	results = runner_old.result_set.select_related('race__event')
	for result in results:
		table_update = models.Table_update.objects.create(model_name='Event', row_id=result.race.event.id, child_id=result.id,
			action_type=models.ACTION_UPDATE, user=creator, is_verified=models.is_admin(creator))
		models.Field_update.objects.create(table_update=table_update, field_name='runner', new_value=runner_new.get_name_and_id())
	n_rows = results.update(runner=runner_new)
	if request and (n_rows > 0):
		messages.success(request, u'Поле runner в таблице dj_result исправлено у {} записей.'.format(n_rows))
	n_extra_names = runner_old.extra_name_set.update(runner=runner_new)
	if request and (n_extra_names > 0):
		messages.success(request, u'Перенесено дополнительных имён у старого бегуна к новому: {}'.format(n_extra_names))

def process_document_formset(request, formset): # Load files to disk if needed. Formset must already be checked as valid
	for form in formset:
		if form.cleaned_data.get('try_to_load', False) and form.cleaned_data['url_original'] and not form.cleaned_data.get('DELETE', False):
			url = form.cleaned_data['url_original']
			result, response, _ = read_url(url)
			if result == 0:
				messages.warning(request, u"Не получилось загрузить файл по адресу {}. Ошибка: {}".format(
					url, response))
			else:
				doc_temp = NamedTemporaryFile(delete=True)
				doc_temp.write(response.read())
				doc_temp.flush()
				doc_name = url.split('/')[-1]
				form.instance.upload.save(doc_name, File(doc_temp), save=False)
				form.instance.loaded_type = 1
				messages.success(request, u'Файл {} успешно загружен на сервер'.format(url))

def try_load_files(start_from=0):
	total_size = 0
	files_loaded = 0
	n_errors = 0
	last_protocol_id = 0
	protocols = models.Document.objects.filter(
		Q(url_original__iendswith='.xls') | Q(url_original__iendswith='.xlsx') | Q(url_original__iendswith='.doc')
		| Q(url_original__iendswith='.docx') | Q(url_original__iendswith='.pdf') | Q(url_original__iendswith='.jpg')
		| Q(url_original__iendswith='.jpeg'), upload='', series_id__gte=start_from).exclude(
		Q(url_original__startswith='http://www.probeg') | Q(url_original__startswith='http://probeg')).select_related(
		'series').order_by('series_id')
	for protocol in protocols:
		url = protocol.url_original
		last_protocol_id = protocol.id
		# print u'Series id: {}, {}, type: {}, URL: {}'.format(protocol.series.id, protocol.series.name, protocol.get_document_type_display(), url)
		result, response, file_size = read_url(url)
		if result == 0:
			print u'Series id: {}, {}, type: {}, URL: {}'.format(protocol.series.id, protocol.series.name, protocol.get_document_type_display(), url)
			print u"Не получилось загрузить файл по адресу {}. Ошибка: {}".format(url, response)
			n_errors += 1
		elif file_size == 0:
			print u'Series id: {}, {}, type: {}, URL: {}'.format(protocol.series.id, protocol.series.name, protocol.get_document_type_display(), url)
			print u"Файл имеет размер 0. Пропускаем"
			n_errors += 1
		else:
			doc_temp = NamedTemporaryFile(delete=True)
			doc_temp.write(response.read())
			doc_temp.flush()
			doc_name = url.split('/')[-1]
			protocol.upload.save(doc_name, File(doc_temp), save=False)
			protocol.loaded_type = 1
			protocol.save()
			# print u'Файл {} размером {} байт успешно загружен на сервер'.format(url, file_size)
			total_size += file_size
			files_loaded += 1
	print 'Finished! Files loaded: {}, total size: {}, errors: {}, last protocol id: {}'.format(
		files_loaded, total_size, n_errors, last_protocol_id)

def check_rights(request, event=None, series=None, club=None): # Returns context, has_rights, where-to-redirect-if-false
	if (series is None) and event:
		series = event.series
	context = user_edit_vars(request.user, series=series, club=club)
	if context['is_admin']:
		return context, True, None
	if series:
		if (event is None) and context['is_editor']:
			return context, True, None
		if event and context['is_editor'] and (context['is_extended_editor'] or (event.start_date is None) or event.can_be_edited()):
			return context, True, None
		messages.warning(request, u"У Вас нет прав на это действие.")
		if event and event.id:
			target = redirect(event)
		else:
			target = redirect(series)
		return context, False, target
	elif club:
		if context['is_editor']:
			return context, True, None
		if club.id:
			messages.warning(request, u"У Вас нет прав на это действие.")
			return context, False, redirect(club)
		else: # If we are creating new club
			if request.user.is_authenticated:
				return context, True, None
			else:
				messages.warning(request, u"У Вас нет прав на это действие.")
				return context, False, redirect('results:clubs')
	messages.warning(request, u"У Вас нет прав на это действие.")
	return context, False, redirect('results:home')

# For payments: is user paying for team or club? Does he have rights for that now?
def get_team_club_year_context_target(request, team_id, club_id):
	team = club = target = participants = None
	if team_id:
		team = get_object_or_404(models.Klb_team, pk=team_id)
		club = team.club
		year = team.year
		team_or_club = team
	else:
		club = get_object_or_404(models.Club, pk=club_id)
		year = models.CUR_KLB_YEAR
		team_or_club = club

	context, _, target = check_rights(request, club=club)
	if target is None:
		if team and not models.is_active_klb_year(year, context['is_admin']):
			messages.warning(request, u'Вы уже не можете оплачивать участие в матче за {} год'.format(year))
			target = redirect(team)
		else:
			if team:
				participants = team.klb_participant_set
			else:
				team_ids = set(club.klb_team_set.filter(year=year).values_list('pk', flat=True))
				participants = models.Klb_participant.objects.filter(team_id__in=team_ids)

	return team, club, team_or_club, year, context, target, participants

def is_good_symbol(s):
	return (ord(s) < 128) or (u'а' <= s <= u'я') or (u'А' <= s <= u'Я') or s in u'—«»'

def try_write_to_cp1251_file(s, fname):
	try:
		s_cp1251 = u''.join([i if is_good_symbol(i) else '' for i in s])
		with io.open(settings.MEDIA_ROOT + fname, 'w', encoding="cp1251") as output_file:
			output_file.write(s_cp1251 + '\n')
	except Exception as e:
		pass

def generate_html(source, context, target, dir='results/templates/generated/', to_old_probeg=False, debug=False):
	if debug:
		print u'generate_html: Trying to render source {} to target {}'.format(source, target)
	res = render_to_string(source, context)
	if debug:
		print u'generate_html: Done! Writing to file...'
	with io.open(os.path.join(settings.BASE_DIR, dir, target), 'w', encoding="utf8") as output_file:
		output_file.write(res)
	if debug:
		print u'generate_html: Done!'
	if to_old_probeg:
		try_write_to_cp1251_file(res, to_old_probeg)

def changes_history(request, context, obj, obj_link, obj_id=None):
	context['changes'] = models.Table_update.objects.filter(model_name=obj.__class__.__name__, row_id=obj.id).select_related(
		'user', 'verified_by').prefetch_related(Prefetch('field_update_set',
		queryset=models.Field_update.objects.order_by('field_name'))).annotate(n_messages=Count('message_from_site')).order_by('-added_time')
	context['obj_link'] = obj_link
	# When obj is User_profile, we need user id instead of User_profile id
	context['page_title'] = u'{} (id {}): история изменений'.format(obj, obj_id if obj_id else obj.id)
	return render(request, "editor/changes_history.html", context)
