# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404, render, redirect
from django.forms import modelformset_factory
from django.core.urlresolvers import reverse
from django.db.models.query import Prefetch
from django.db.models import Count, Q
from django.contrib import messages
from django.db import transaction

import datetime
from calendar import monthrange
from collections import Counter
import logging

from results import models, models_klb
from results import results_util
from editor import forms
from .views_user_actions import log_form_change, log_document_formset
from .views_common import update_series, group_required, process_document_formset, check_rights, changes_history

from tools.flock_mutex import Flock_mutex
from starrating.constants import LOCK_FILE_FOR_RATED_TREE_MODIFICATIONS
from starrating.aggr.rated_tree_modifications import transfer_children_before_node_deletion
from starrating.exceptions import UpdatedRecordExistsError

def get_year_constants():
	context = {}
	context['cur_year'] = models.CUR_KLB_YEAR
	context['NADYA_CALENDAR_YEAR_START'] = models.NADYA_CALENDAR_YEAR_START
	context['NADYA_CALENDAR_YEAR_END'] = models.NADYA_CALENDAR_YEAR_END
	return context

@group_required('admins')
def seria(request, country_id=None, region_id=None, city_id=None, series_name=None, detailed=False):
	context = {}
	context['page_title'] = u'Серии пробегов'
	context.update(get_year_constants())

	list_title = u'Серии пробегов '
	conditions = []

	seria = models.Series.objects.select_related('city__region__country')
	form = None

	country = None
	region = None
	city = None
	with_events = False
	kwargs = {}
	initial = {}
	context['short_link_city'] = False
	context['short_link_region'] = False
	context['short_link_country'] = False

	if city_id:
		city = get_object_or_404(models.City, pk=city_id)
		initial['city'] = city
		if city.region.active:
			initial['region'] = city.region
		else:
			initial['country'] = city.region.country
		context['city'] = city
		context['short_link_city'] = True
	elif region_id:
		region = get_object_or_404(models.Region, pk=region_id)
		initial['region'] = region
		context['short_link_region'] = True
	elif country_id:
		country = get_object_or_404(models.Country, pk=country_id)
		initial['country'] = country
		context['short_link_country'] = True
	elif series_name:
		initial['series_name'] = series_name
		context['short_link_name'] = True
		context['series_name'] = series_name
	elif (request.method == 'GET') and request.GET.get('frmSearchSeries_submit', False):
		form = forms.SeriesSearchForm(request.GET)
		if form.is_valid():
			country = form.cleaned_data['country']
			region = form.cleaned_data['region']
			city = form.cleaned_data['city']
			with_events = form.cleaned_data['with_events']
			series_name = form.cleaned_data['series_name']

			if form.cleaned_data['date_from']:
				kwargs['start_date__gte'] = form.cleaned_data['date_from']
			if form.cleaned_data['date_to']:
				kwargs['start_date__lte'] = form.cleaned_data['date_to']
			if (not with_events) and (not series_name):
				if city:
					context['short_link_city'] = True
				elif region:
					context['short_link_region'] = True
				elif country:
					context['short_link_country'] = True
	else:
		context['msgInsteadSeria'] = u'Укажите хоть какой-нибудь параметр для поиска.'
	if form is None:
		form = forms.SeriesSearchForm(initial=initial)

	if country:
		seria = seria.filter(Q(city__region__country=country) | (Q(city=None) & Q(country=country)))
		conditions.append(u"в стране " + country.name)
	if region:
		seria = seria.filter(city__region=region)
		conditions.append(u"в регионе " + region.name)
	if city:
		seria = seria.filter(city=city)
		conditions.append(u"в городе " + city.name)
	if series_name:
		seria = seria.filter(name__icontains=series_name)
		conditions.append(u"с «{}» в названии".format(series_name))

	if with_events:
		seria = seria.prefetch_related(
			Prefetch('event_set', queryset=models.Event.objects.filter(**kwargs).order_by('-start_date')))

	context['seria'] = seria.order_by('city__region__country__name', 'city__name', 'name')
	context['frmSearchSeries'] = form
	context['country'] = country
	context['region'] = region
	context['city'] = city
	context['with_events'] = with_events
	context['list_title'] = list_title + ", ".join(conditions)
	return render(request, "editor/seria.html", context)

def getDocumentFormSet(series, data=None, files=None):
	DocumentFormSet = modelformset_factory(models.Document, form=forms.DocumentForm, can_delete=True)
	return DocumentFormSet(
		data=data,
		files=files,
		queryset=series.document_set.order_by('document_type', 'comment'),
		initial=[{'series':series}]
	)

@group_required('editors', 'admins')
def series_details(request, series_id=None, series=None, frmDocuments=None, cloned_series_id=None,
		frmSeries=None, frmForSeries=forms.ForSeriesForm(auto_id='frmForSeries_%s'), create_new=False):
	if not series: # False if we are creating new series
		series = get_object_or_404(models.Series, pk=series_id)
	context, has_rights, target = check_rights(request, series=series)
	if not has_rights:
		return target
	if series and not frmSeries:
		initial = {}
		if series.city:
			initial['city'] = series.city
			initial['region'] = series.city.region
			initial['country'] = series.city.region.country
		elif series.country:
			initial['country'] = series.country
		frmSeries = forms.SeriesForm(instance=series, initial=initial)
		# frmSeries.country = series.region.country

	context['series'] = series
	context['frmSeries'] = frmSeries
	context['frmForSeries'] = frmForSeries
	context['create_new'] = create_new
	context['cloned_series_id'] = cloned_series_id

	if cloned_series_id:
		context['page_title'] = u'Клонирование серии'
	elif create_new:
		context['page_title'] = u'Создание новой серии'
	else:
		context['page_title'] = u'{} (id {})'.format(series, series.id)
		context['n_documents'] = series.document_set.count()
		context['n_events'] = series.event_set.count()
		context['events'] = models.Event.objects.filter(series=series).annotate(n_races=Count('race')).order_by('-start_date')
		if not frmDocuments:
			frmDocuments = getDocumentFormSet(series)
		context['frmDocuments'] = frmDocuments

	return render(request, "editor/series_details.html", context)

@group_required('editors', 'admins')
def series_changes_history(request, series_id):
	series = get_object_or_404(models.Series, pk=series_id)
	context, has_rights, target = check_rights(request, series=series)
	if not has_rights:
		return target
	return changes_history(request, context, series, series.get_absolute_url())

@group_required('editors', 'admins')
def series_update(request, series_id):
	series = get_object_or_404(models.Series, pk=series_id)
	context, has_rights, target = check_rights(request, series=series)
	if not has_rights:
		return target
	if 'frmSeries_submit' in request.POST:
		form = forms.SeriesForm(request.POST, instance=series)
		if form.is_valid():
			form.save()
			log_form_change(request.user, form, action=models.ACTION_UPDATE, exclude=['country', 'region'])
			messages.success(request, u'Серия «{}» успешно обновлена. Проверьте, всё ли правильно.'.format(series))
			return redirect(series.get_editor_url())
		else:
			messages.warning(request, u"Серия не обновлена. Пожалуйста, исправьте ошибки в форме.")
	else:
		form = forms.SeriesForm(instance=series)
	return series_details(request, series_id=series_id, series=series, frmSeries=form)

@group_required('editors', 'admins')
def series_documents_update(request, series_id):
	series = get_object_or_404(models.Series, pk=series_id)
	context, has_rights, target = check_rights(request, series=series)
	if not has_rights:
		return target
	if 'frmDocuments_submit' in request.POST:
		formset = getDocumentFormSet(series, data=request.POST, files=request.FILES)
		if formset.is_valid():
			process_document_formset(request, formset)
			instances = formset.save()
			log_document_formset(request.user, series, formset)
			messages.success(request, (u'Документы серии «{}» успешно обновлены: {} документов добавлено, {} обновлено, '
				+ u'{} удалено. Проверьте, всё ли правильно.').format(
				series, len(formset.new_objects), len(formset.changed_objects), len(formset.deleted_objects)))
			return redirect(series.get_editor_url())
		else:
			messages.warning(request, u"Документы серии «{}» не обновлены. Пожалуйста, исправьте ошибки в форме.".format(series))
			# messages.warning(request, unicode(formset.errors))
	else:
		formset = None
	return series_details(request, series_id=series_id, series=series, frmDocuments=formset)

@group_required('admins')
def series_create(request, country_id=None, region_id=None, city_id=None, series_id=None):
	if series_id: # Clone series with this id
		series = get_object_or_404(models.Series, pk=series_id)
		series.id = None
		series.name = ''
		series.created_by = request.user
	else:
		series = models.Series(created_by=request.user)
	if 'frmSeries_submit' in request.POST:
		form = forms.SeriesForm(request.POST, instance=series)
		if form.is_valid():
			series = form.save()
			series.card_raw = unicode(series.id)
			series.save()
			log_form_change(request.user, form, action=models.ACTION_CREATE, exclude=['country', 'region'])
			messages.success(request, u'Серия «{}» успешно создана. Проверьте, всё ли правильно.'.format(series))
			return redirect(series.get_editor_url())
		else:
			messages.warning(request, u"Серия не создана. Пожалуйста, исправьте ошибки в форме.")
	else:
		initial = {}
		if country_id:
			initial['country'] = get_object_or_404(models.Country, pk=country_id)
		if region_id:
			initial['region'] = get_object_or_404(models.Region, pk=region_id)
			initial['country'] = initial['region'].country
		if city_id:
			city = get_object_or_404(models.City, pk=city_id)
			series.city = city
			initial['city'] = city
			if city.region.active:
				initial['region'] = city.region
			else:
				initial['country'] = city.region.country
		form = forms.SeriesForm(instance=series, initial=initial)

	return series_details(request, series=series, frmSeries=form, create_new=True, cloned_series_id=series_id)

@group_required('editors', 'admins')
def series_delete(request, series_id):
	series = get_object_or_404(models.Series, pk=series_id)
	context, has_rights, target = check_rights(request, series=series)
	if not has_rights:
		return target
	has_dependent_objects = series.has_dependent_objects()
	ok_to_delete = False

	if (request.method == 'POST') and request.POST.get('frmForSeries_submit', False):
		form = forms.ForSeriesForm(request.POST, auto_id='frmForSeries_%s')
		if form.is_valid():
			if has_dependent_objects:
				new_series_id = models.int_safe(request.POST.get('new_series_id', 0))
				if new_series_id:
					if new_series_id != series.id:
						new_series = models.Series.objects.filter(pk=new_series_id).first()
						if new_series:
							ok_to_delete = True
						else:
							messages.warning(request, u'Серия, на которую нужно заменить текущую, не найдена.')
					else:
						messages.warning(request, u'Нельзя заменить серию на неё же.')
				else:
					messages.warning(request, u'Серия, на которую нужно заменить текущую, не указана.')
			else: # There are no events in the series, so we just delete it
				ok_to_delete = True
		else:
			messages.warning(request, u"Серия не удалена. Пожалуйста, исправьте ошибки: {}".format(form.errors))
	else:
		form = forms.ForSeriesForm(auto_id='frmForSeries_%s')
		messages.warning(request, u"Вы не указали серию для удаления.")

	if ok_to_delete:
		if not has_dependent_objects:
			new_series_id = 0
			new_series = None
		log = logging.getLogger('structure_modification')
		log_prefix = 'series_delete: series {}->{}, by user {}.'.format(series_id, new_series_id, request.user.id)
		log_exc_info = False
		log.debug('{} before flock'.format(log_prefix))
		with Flock_mutex(LOCK_FILE_FOR_RATED_TREE_MODIFICATIONS):
			try:
				with transaction.atomic():
					if has_dependent_objects:
						update_series(request, series, new_series)
					transfer_children_before_node_deletion(series, new_series)
					models.log_obj_delete(request.user, series)
					series.delete()
				log.debug('{} trnsctn end'.format(log_prefix))
			except (UpdatedRecordExistsError, AssertionError) as e:
				error_msg = repr(e)
				if isinstance(e, AssertionError):
					log_exc_info = True
			except Exception as e:
				log.error('{} Unexpected error: {}'.format(log_prefix, repr(e)), exc_info=True)
				raise
			else:
				error_msg = None
		if error_msg is None:
			log.info('{} OK'.format(log_prefix))
			messages.success(request, u'Серия «{}» успешно удалена.'.format(series))
		else:
			log.error('{} {}'.format(log_prefix, error_msg), exc_info=log_exc_info)
			messages.warning(
				request, u'Не удалось удалить серию «{}» ({}).'.format(series, error_msg)
			)

		if has_dependent_objects:
			return redirect(new_series)
		else:
			return redirect('results:races')

	return series_details(request, series_id=series_id, series=series, frmForSeries=form)

@group_required('admins')
def events_wo_protocol(request, year):
	year = models.int_safe(year)
	context = {}
	context['year'] = year
	context.update(get_year_constants())

	context['list_title'] = context['page_title'] = u"Завершившиеся пробеги {} года без протоколов".format(year)
	context['frmSearchSeries'] = forms.SeriesSearchForm()
	today = datetime.date.today()
	cur_year_events = models.Event.objects.filter(start_date__year=year, start_date__lt=today, cancelled=False).select_related('series')
	event_wo_protocol_ids = set()
	series_wo_protocol_ids = set()
	for event in cur_year_events:
		if not event.document_set.filter(document_type__in=models.DOC_PROTOCOL_TYPES).exists():
			event_wo_protocol_ids.add(event.id)
			series_wo_protocol_ids.add(event.series.id)
	context['seria'] = models.Series.objects.filter(id__in=series_wo_protocol_ids).prefetch_related(
		Prefetch('event_set', queryset=models.Event.objects.filter(id__in=event_wo_protocol_ids).order_by('-start_date'))
	)
	context['with_events'] = True
	return render(request, "editor/seria.html", context)

@group_required('admins')
def series_wo_new_event(request):
	context = get_year_constants()
	today = datetime.date.today()
	year_ago = today - datetime.timedelta(days=365)
	ten_months_ago = today - datetime.timedelta(days=304)
	month_ago = today - datetime.timedelta(days=31)
	three_months_forward = today + datetime.timedelta(days=92)

	context['list_title'] = context['page_title'] = \
		u"Серии в России/Украине/Беларуси/Казахстане, в которых были забеги с {} по {}, а с {} по {} забегов нет".format(
			year_ago, ten_months_ago, month_ago, three_months_forward)
	context['frmSearchSeries'] = forms.SeriesSearchForm()

	year_ago_series_ids = set(models.Event.objects.filter(
		Q(series__country_id__in=('RU', 'UA', 'BY', 'KZ')) | Q(country_id__in=('RU', 'UA', 'BY', 'KZ')),
		start_date__range=(year_ago, ten_months_ago)).values_list('series_id', flat=True))
	this_year_series_ids = set(models.Event.objects.filter(start_date__range=(month_ago, three_months_forward)).values_list('series_id', flat=True))

	context['seria'] = models.Series.objects.filter(id__in=year_ago_series_ids - this_year_series_ids).exclude(
		id=results_util.OLD_PARKRUN_SERIES_ID).prefetch_related(
		Prefetch('event_set', queryset=models.Event.objects.filter(start_date__gte=today - datetime.timedelta(days=3*365)).order_by('-start_date'))
	)
	context['with_events'] = True
	return render(request, "editor/seria.html", context)

@group_required('admins')
def events_wo_protocol_for_klb(request, year):
	year = models.int_safe(year)
	context = {}
	context['year'] = year
	context.update(get_year_constants())

	context['list_title'] = context['page_title'] = u"Завершившиеся пробеги {} года для КЛБМатча в России без протоколов".format(year)
	context['frmSearchSeries'] = forms.SeriesSearchForm()
	event_for_klb_ids = set(models.Race.objects.filter(
		Q(event__city__region__country_id='RU') | Q(event__city=None, event__series__city__region__country_id='RU'),
		Q(distance__distance_type=models.TYPE_METERS, distance__length__gte=models_klb.get_min_distance_for_score(year))
			| Q(distance__distance_type=models.TYPE_MINUTES),
		event__start_date__year=year, event__cancelled=False
	).values_list('event_id', flat=True))
	cur_year_events = models.Event.objects.filter(pk__in=event_for_klb_ids).select_related('series')
	event_wo_protocol_ids = set()
	series_wo_protocol_ids = set()
	for event in cur_year_events:
		if not event.document_set.filter(document_type__in=models.DOC_PROTOCOL_TYPES).exists():
			event_wo_protocol_ids.add(event.id)
			series_wo_protocol_ids.add(event.series.id)
	context['seria'] = models.Series.objects.filter(id__in=series_wo_protocol_ids).prefetch_related(
		Prefetch('event_set', queryset=models.Event.objects.filter(id__in=event_wo_protocol_ids).order_by('-start_date'))
	)
	context['with_events'] = True
	return render(request, "editor/seria.html", context)

@group_required('admins')
def events_not_in_next_year(request, year):
	year = models.int_safe(year)
	context = {}
	context['year'] = year
	context.update(get_year_constants())
	context['list_title'] = context['page_title'] = u"Серии в России, Украине, Беларуси с пробегами в {} и без пробегов в {}".format(
		year - 1, year)
	context['frmSearchSeries'] = forms.SeriesSearchForm()
	countries = ('RU', 'UA', 'BY')
	events = models.Event.objects.filter(Q(city__region__country_id__in=countries)
		| Q(city=None, series__city__region__country_id__in=countries))
	series_ids = set(events.filter(start_date__year=year - 1, cancelled=False).values_list('series__id', flat=True)) \
		- set(events.filter(start_date__year=year).values_list('series__id', flat=True))
	context['seria'] = models.Series.objects.filter(id__in=series_ids).prefetch_related(
		Prefetch('event_set', queryset=models.Event.objects.filter(start_date__year__gte=year - 1).order_by('-start_date'))
	)
	context['with_events'] = True
	return render(request, "editor/seria.html", context)

@group_required('admins')
def events_wo_statistics(request, year):
	context = {}
	context['year'] = year
	context.update(get_year_constants())
	context['list_title'] = context['page_title'] = u"Забеги в {} году с протоколом, но без статистики по финишировавшим".format(year)
	context['frmSearchSeries'] = forms.SeriesSearchForm()
	event_ids = set(models.Document.objects.filter(event__start_date__year=year,
		document_type__in=models.DOC_PROTOCOL_TYPES).values_list('event__id', flat=True)) \
		& set(models.Race.objects.filter(event__start_date__year=year, n_participants_finished=None).values_list('event__id', flat=True))
	series_ids = set(models.Event.objects.filter(id__in=event_ids).values_list('series__id', flat=True))
	context['seria'] = models.Series.objects.filter(id__in=series_ids).prefetch_related(
		Prefetch('event_set', queryset=models.Event.objects.filter(id__in=event_ids).order_by('-start_date'))
	)
	context['with_events'] = True
	return render(request, "editor/seria.html", context)

@group_required('admins')
def events_with_xls_protocol(request):
	context = {}
	context.update(get_year_constants())

	context['list_title'] = context['page_title'] = u"Все забеги с необработанными протоколами XLS/XLSX"
	context['frmSearchSeries'] = forms.SeriesSearchForm()
	protocols = models.Document.objects.filter(models.Q_IS_XLS_FILE | Q(upload__iendswith='.zip'),
		document_type__in=models.DOC_PROTOCOL_TYPES,
		is_processed=False,
	)
	event_with_protocol_ids = set(protocols.values_list('event__id', flat=True))
	races_wo_results = models.Race.objects.filter(
		loaded=models.RESULTS_NOT_LOADED,
		has_no_results=False,
	)
	event_with_not_loaded_races_ids = set(races_wo_results.values_list('event__id', flat=True))
	event_ids = event_with_protocol_ids & event_with_not_loaded_races_ids
	series_ids = set(models.Event.objects.filter(id__in=event_ids).values_list(
		'series__id', flat=True))
	context['seria'] = models.Series.objects.filter(id__in=series_ids).prefetch_related(
		Prefetch('event_set', queryset=models.Event.objects.filter(id__in=event_ids).order_by('-start_date'))
	)
	context['n_events'] = len(event_ids)
	context['with_events'] = True
	return render(request, "editor/seria.html", context)

@group_required('admins')
def all_events_by_year(request, regions=1): # Not for Russia! It is too heavy
	context = {}
	context.update(get_year_constants())
	context['years'] = range(models.NADYA_CALENDAR_YEAR_START, models.NADYA_CALENDAR_YEAR_END + 1)

	regions = models.int_safe(regions)
	context['page_title'] = u"Все пробеги {}-{} годов ".format(models.NADYA_CALENDAR_YEAR_START, models.NADYA_CALENDAR_YEAR_END)
	series_ids = set(models.Event.objects.filter(start_date__year__gte=models.NADYA_CALENDAR_YEAR_START).values_list('series_id', flat=True))
	all_series = models.Series.objects.filter(pk__in=series_ids).select_related('city__region')
	# if regions == 0:
	# 	all_series = all_series.filter(city__region__country_id='RU')
	# 	context['page_title'] += u'в России'
	if regions == 1:
		all_series = all_series.filter(city__region__country_id__in=('UA', 'BY'))
		context['page_title'] += u'в Украине и Беларуси'
	elif regions == 2:
		all_series = all_series.exclude(city__region__country_id__in=('RU', 'UA', 'BY'))
		context['page_title'] += u'вне России, Украины, Беларуси'
	else:
		all_series = all_series.filter(city=None)
		context['page_title'] += u'без указания страны'
	seria = []
	for series in all_series.exclude(url_site__startswith='http://www.parkrun').exclude(url_site__startswith='https://www.parkrun').order_by(
		'city__region__country__name', 'city__region__name', 'city__name', 'name'):
		d = {
			'region': series.city.region.name_full if series.city else 'Регион не указан',
			'series': series,
		}
		# for year in range(models.NADYA_CALENDAR_YEAR_START, models.NADYA_CALENDAR_YEAR_END + 1):
		# 	d['events_{}'.format(year)] = series.event_set.filter(start_date__year=year).order_by('start_date')
		events = []
		for year in range(models.NADYA_CALENDAR_YEAR_START, models.NADYA_CALENDAR_YEAR_END + 1):
			events.append(series.event_set.filter(start_date__year=year).select_related('series__city__region__country',
				'city__region__country', 'series__country').order_by('start_date'))
		d['events'] = events
		seria.append(d)
	context['seria'] = seria
	return render(request, "editor/all_events_by_year.html", context)

@group_required('admins')
def events_in_seria_by_year(request):
	context = {}
	context['page_title'] = u"Все забеги {}-{} годов в России".format(models.NADYA_CALENDAR_YEAR_START, models.NADYA_CALENDAR_YEAR_END)
	return render(request, "editor/events_in_seria_by_year.html", context)

def reset_series_by_letter():
	models.Letter_of_series.objects.all().delete()
	letters = Counter()
	for name in models.Series.objects.values_list('name', flat=True):
		letters[name[0].upper()] += 1
	for letter, count in letters.items():
		models.Letter_of_series.objects.create(letter=letter, n_series=count)
	print 'Done! Letters created:', len(letters)

@group_required('admins')
def series_by_letter(request, letter=None):
	context = {}
	if request.method == 'POST':
		saved_series = 0
		for key, val in request.POST.items():
			if key.startswith('series_'):
				series_id = models.int_safe(key[len('series_'):])
				series = models.Series.objects.filter(pk=series_id).first()
				if series:
					new_val = models.int_safe(val)
					if series.surface_type != new_val:
						series.surface_type = new_val
						series.save()
						models.log_obj_create(request.user, series, models.ACTION_UPDATE, field_list=['surface_type'],
							comment=u'Массовое проставление типа забега')
						saved_series += 1
		messages.success(request, u'Сохранено значений для серий: {}. Спасибо!'.format(saved_series))
		# models.Letter_of_series.objects.filter(letter=letter).update(is_checked=True)
		return redirect(reverse('editor:series_by_letter', kwargs={'letter': letter}))

	context['letters'] = models.Letter_of_series.objects.all().order_by('letter')
	context['surface_types'] = models.SURFACE_TYPES
	if letter:
		context['page_title'] = u"Все серии на символ {}".format(letter)
		context['seria'] = models.Series.objects.filter(name__istartswith=letter, series_type=models.SERIES_TYPE_RUN,
			surface_type__in=(models.SURFACE_DEFAULT, models.SURFACE_HARD)).order_by('name')
		# context['q'] = models.Series.objects.filter(name__istartswith=letter).order_by('name').query
	else:
		context['page_title'] = u"Заполняем тип забегов у серий. Выберите любую букву"
	return render(request, "editor/series_by_letter.html", context)

@group_required('admins')
def events_in_klb(request):
	context = {}
	year = models.CUR_KLB_YEAR
	context['list_title'] = context['page_title'] = u'Забеги в {} году с хотя бы одним учтённым результатом в КЛБМатче'.format(year)
	race_ids = set(models.Klb_result.objects.filter(race__event__start_date__year=year).values_list('race_id', flat=True))
	races = models.Race.objects.filter(pk__in=race_ids)
	context['races_in_klb'] = races.select_related('event__series__city__region__country',
		'event__city__region__country', 'event__series__country').order_by(
		'-event__start_date', 'event__name', 'event_id', 'distance__distance_type', '-distance__length', 'precise_name')
	context['n_events'] = len(set(races.values_list('event_id', flat=True)))

	return render(request, "editor/events_in_klb.html", context)

@group_required('admins')
def loaded_protocols_by_month(request):
	context = {}
	month_ago = datetime.date.today() - datetime.timedelta(days=28)
	month = month_ago.month
	year = month_ago.year
	if request.method == 'POST':
		form = forms.MonthYearForm(request.POST)
		if form.is_valid():
			month = models.int_safe(form.cleaned_data['month'])
			year = models.int_safe(form.cleaned_data['year'])
	else:
		form = forms.MonthYearForm(initial={'month': month, 'year': year})

	date_from = datetime.date(year, month, 1)
	date_to = datetime.date(year, month, monthrange(year, month)[1])
	table_updates = models.Table_update.objects.filter(action_type=models.ACTION_RESULTS_LOAD, added_time__gte=date_from, 
		added_time__lte=date_to)
	race_ids = set(table_updates.values_list('child_id', flat=True))

	race_by_id = {}
	for race in models.Race.objects.filter(pk__in=race_ids).annotate(Count('result')).select_related(
			'event__series__city__region__country', 'event__city__region__country'):
		race_by_id[race.id] = race

	context['races'] = []
	events_used = set()
	races_used = set()
	context['n_results'] = 0
	for update in table_updates.order_by('-added_time'):
		# We take only still existing racec, and we take only the latest results loading for each race in current month
		if (update.child_id in race_by_id) and (update.child_id not in races_used):
			race = race_by_id[update.child_id]
			context['races'].append((race, update))
			races_used.add(update.child_id)
			events_used.add(race.event_id)
			context['n_results'] += race.result__count

	context['page_title'] = u'Все обработанные протоколы за {} {}'.format(forms.MONTHS[month - 1][1], year)
	context['site_url'] = models.SITE_URL
	context['form'] = form

	context['n_events'] = len(events_used)
	context['n_races'] = len(races_used)
	return render(request, "editor/loaded_protocols_by_month.html", context)

@group_required('admins')
def all_events_with_social_links(request): # For Eugene
	context = {}
	country_ids = ('RU', 'UA', 'BY')
	context['events'] = models.Event.get_visible_events().filter(
			Q(city__region__country_id__in=country_ids) | ( Q(city=None) & Q(series__city__region__country_id__in=country_ids) ),
			start_date__year__gte=2019,
			).exclude(url_vk='', url_facebook='', series__url_vk='', series__url_facebook='', series__url_instagram='').exclude(
			series__is_parkrun=True).select_related(
			'city__region__country', 'series__city__region__country', 'series__country',
			'city_finish__region__country', 'series__city_finish__region__country',
			).order_by('start_date', 'name')
	context['page_title'] = u'Все забеги с 2019 года с хоть какой-нибудь ссылкой на соцсеть'
	return render(request, "editor/events_with_social_links.html", context)
