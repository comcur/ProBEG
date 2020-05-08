# -*- coding: utf-8 -*-
from __future__ import division
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q, F, Sum, Count
from django.core.urlresolvers import reverse
from django.db.models.query import Prefetch
from django.contrib import messages
from django.http import Http404
import datetime
from collections import OrderedDict, Counter

from results import models, forms
from results.templatetags.results_extras import add_prefix
from results import results_util
from views_common import user_edit_vars, paginate_and_render, get_page_num, get_results_with_splits_ids
from editor.views import views_stat, views_klb
from starrating.utils.show_rating import get_sr_overall_data

def filterRacesByCity(races, conditions, city):
	races = races.filter(
		Q(event__city=city)
		| Q(event__city_finish=city)
		| (Q(event__city=None) & Q(event__series__city=city))
		| (Q(event__city=None) & Q(event__series__city_finish=city))
	)
	conditions.append(u"в городе {}".format(city.name))
	return races
def filterRacesByRegion(races, conditions, region):
	races = races.filter(
		Q(event__city__region=region)
		| Q(event__city_finish__region=region)
		| (Q(event__city=None) & Q(event__series__city__region=region))
		| (Q(event__city=None) & Q(event__series__city_finish__region=region))
	)
	conditions.append(u"в регионе {}".format(region.name_full))
	return races
def filterRacesByRegionGroup(races, conditions, regions):
	races = races.filter(
		Q(event__city__region__in=regions)
		| Q(event__city_finish__region__in=regions)
		| (Q(event__city=None) & Q(event__series__city__region__in=regions))
		| (Q(event__city=None) & Q(event__series__city_finish__region__in=regions))
	)
	conditions.append(u"в регионах {}".format(u', '.join(region.name_full for region in regions)))
	return races
def filterRacesByCountry(races, conditions, country):
	races = races.filter(
		Q(event__city__region__country=country)
		| Q(event__city_finish__region__country=country)
		| (Q(event__city=None) & Q(event__series__city__region__country=country))
		| (Q(event__city=None) & Q(event__series__city_finish__region__country=country))
		| (Q(event__city=None) & Q(event__series__city=None) & Q(event__series__country=country))
	)
	conditions.append(u"в стране {}".format(country.name))
	return races
def filterRacesByDateFrom(races, conditions, date_from):
	conditions.append(u"не раньше {}".format(date_from.strftime('%d.%m.%Y')))
	return races.filter(Q(event__start_date__gte=date_from) | Q(event__finish_date__gte=date_from))
def filterRacesByDateTo(races, conditions, date_to):
	conditions.append(u"не позже {}".format(date_to.strftime('%d.%m.%Y')))
	return races.filter(event__start_date__lte=date_to)
def filterRacesByName(races, conditions, name):
	conditions.append(u"с «{}» в названии".format(name))
	return races.filter(Q(event__series__name__icontains=name) | Q(event__series__name_eng__icontains=name) | Q(event__name__icontains=name))
def filterRacesByDateRegion(races, date_region, today):
	list_title = u"Забеги"
	if date_region == forms.DATE_REGION_FUTURE:
		races = races.filter(event__start_date__gte=today)
		list_title = u"Предстоящие забеги"
	elif date_region == forms.DATE_REGION_PAST:
		races = races.filter(Q(event__finish_date__lte=today)
			| (Q(event__finish_date=None) & Q(event__start_date__lte=today)))
		list_title = u"Завершившиеся забеги"
	elif date_region == forms.DATE_REGION_NEXT_WEEK:
		races = races.filter(event__start_date__gte=today, event__start_date__lte=today + datetime.timedelta(days=7))
		list_title = u"Забеги в ближайшую неделю ({})".format(models.dates2str(today, today + datetime.timedelta(days=7)))
	elif date_region == forms.DATE_REGION_NEXT_MONTH:
		races = races.filter(event__start_date__gte=today, event__start_date__lte=today + datetime.timedelta(days=31))
		list_title = u"Забеги в ближайший месяц ({})".format(models.dates2str(today, today + datetime.timedelta(days=31)))
	return races, list_title
def filterRacesByDistance(races, conditions, distance):
	conditions.append(u"на дистанцию {}".format(distance))
	return races.filter(distance=distance)
def filterRacesByDistanceFrom(races, conditions, distance_from):
	distance_from = int(distance_from * 1000)
	conditions.append(u"не короче {} м".format(distance_from))
	return races.filter(distance__distance_type=models.TYPE_METERS, distance__length__gte=distance_from)
def filterRacesByDistanceTo(races, conditions, distance_to):
	distance_to = int(distance_to * 1000)
	conditions.append(u"не длиннее {} м".format(distance_to))
	return races.filter(distance__distance_type=models.TYPE_METERS, distance__length__lte=distance_to)
def excludeParkrunEvents(races, conditions):
	conditions.append(u"без забегов parkrun")
	return races.exclude(event__series__is_parkrun=True)
def filterRacesWithLoadedResults(races, conditions):
	conditions.append(u"с загруженными результатами")
	return races.filter(loaded__in=(models.RESULTS_LOADED, models.RESULTS_SOME_OFFICIAL))

def add_related_to_events(events):
	return events.select_related('series__city__region__country',
		'city__region__country', 'series__country').prefetch_related(
		Prefetch('race_set',
			queryset=models.Race.objects.select_related('distance').order_by('distance__distance_type', '-distance__length', 'precise_name')),
		Prefetch('review_set', queryset=models.Document.objects.filter(document_type=models.DOC_TYPE_IMPRESSIONS)),
		Prefetch('photo_set', queryset=models.Document.objects.filter(document_type=models.DOC_TYPE_PHOTOS)),
		Prefetch('news_set', queryset=models.News.objects.order_by('-date_posted')),
		Prefetch('document_set',
			queryset=models.Document.objects.exclude(document_type__in=[9, 13]).order_by('document_type', 'comment')),
	).annotate(sum_finishers=Sum('race__n_participants_finished')).order_by('start_date', 'name')

def races_default(request):
	context = user_edit_vars(request.user)
	context['page_title'] = u'Календарь забегов в России, Украине, Беларуси на ближайший месяц'

	initial = {}
	user = request.user
	if user.is_authenticated() and hasattr(user, 'user_profile') and user.user_profile.hide_parkruns_in_calendar:
		initial['hide_parkruns'] = True
	context['form'] = forms.EventForm(initial=initial)
	return render(request, 'results/races_default.html', context)

def races(request, city_id=None, region_id=None, country_id=None, distance_id=None, date_region=None, race_name=None, region_group=None, view=0):
	if (request.method == "GET") and (len(request.GET) == 0) and (city_id is None) and (region_id is None) and (country_id is None) \
			and (distance_id is None) and (date_region is None) and (race_name is None) and (region_group is None):
		return races_default(request)
	user = request.user
	context = user_edit_vars(user)
	list_title = u"Все забеги"
	today = datetime.date.today()
	conditions = []
	form_params = {}
	initial = {}
	form = None
	use_default_date_region = True
	form_was_submitted = ('btnSearchSubmit' in request.GET) or ('page' in request.GET)

	if region_group:
		form_params['regions'] = set()
		for s in region_group.split(','):
			form_params['regions'].add(get_object_or_404(models.Region, pk=s))
		if form_params['regions']:
			initial['region'] = list(form_params['regions'])[0]
	if city_id:
		form_params['city'] = get_object_or_404(models.City, pk=city_id)
		context['city_wiki'] = form_params['city'].url_wiki
		context['city'] = form_params['city']
		if form_params['city'].region.active:
			initial['region'] = form_params['city'].region
		else:
			initial['country'] = form_params['city'].region.country
		use_default_date_region = False
		form_params['date_region'] = forms.DATE_REGION_FUTURE
		initial['date_region'] = forms.DATE_REGION_FUTURE
	if region_id:
		form_params['region'] = get_object_or_404(models.Region, pk=region_id)
		initial['region'] = form_params['region']
	if country_id:
		form_params['country'] = get_object_or_404(models.Country, pk=country_id)
		initial['country'] = form_params['country']
	if distance_id:
		form_params['distance'] = get_object_or_404(models.Distance, pk=distance_id)
		initial['distance_from'] = form_params['distance'].length / 1000.
		initial['distance_to'] = form_params['distance'].length / 1000.
	if date_region:
		form_params['date_region'] = results_util.int_safe(date_region)
		initial['date_region'] = form_params['date_region']
	if race_name:
		use_default_date_region = False
		form_params['race_name'] = race_name.strip()
		initial['race_name'] = form_params['race_name']
		form_params['date_region'] = forms.DATE_REGION_ALL
		initial['date_region'] = forms.DATE_REGION_ALL
	if ('hide_parkruns' in request.GET):
		form_params['hide_parkruns'] = True
		initial['hide_parkruns'] = True
	elif (not form_was_submitted) and user.is_authenticated() and hasattr(user, 'user_profile') and user.user_profile.hide_parkruns_in_calendar:
		form_params['hide_parkruns'] = True
		initial['hide_parkruns'] = True
	if form_was_submitted:
		use_default_date_region = False
		form = forms.EventForm(request.GET)
		if form.is_valid():
			form_params = {key: val for (key, val) in form.cleaned_data.items() if val}
			context['hide_parkruns'] = form_params.get('hide_parkruns')
	if use_default_date_region:
		form_params['date_region'] = forms.DATE_REGION_DEFAULT
		initial['date_region'] = forms.DATE_REGION_DEFAULT

	races = models.Race.objects.exclude(event__series__id=results_util.OLD_PARKRUN_SERIES_ID)
	if not context['is_admin']:
		races = races.filter(event__invisible=False, event__cancelled=False)

	if 'city' in form_params:
		context['city'] = form_params['city']
		races = filterRacesByCity(races, conditions, form_params['city'])
	elif 'regions' in form_params:
		races = filterRacesByRegionGroup(races, conditions, form_params['regions'])
	elif 'region' in form_params:
		races = filterRacesByRegion(races, conditions, form_params['region'])
	elif 'country' in form_params:
		races = filterRacesByCountry(races, conditions, form_params['country'])
	if 'date_region' in form_params:
		races, list_title = filterRacesByDateRegion(races, results_util.int_safe(form_params['date_region']), today)
	if 'race_name' in form_params:
		races = filterRacesByName(races, conditions, form_params['race_name'])
	if 'date_from' in form_params:
		races = filterRacesByDateFrom(races, conditions, form_params['date_from'])
	if 'date_to' in form_params:
		races = filterRacesByDateTo(races, conditions, form_params['date_to'])
	if 'distance' in form_params:
		races = filterRacesByDistance(races, conditions, form_params['distance'])
	if 'distance_from' in form_params:
		races = filterRacesByDistanceFrom(races, conditions, form_params['distance_from'])
	if 'distance_to' in form_params:
		races = filterRacesByDistanceTo(races, conditions, form_params['distance_to'])
	if 'hide_parkruns' in form_params:
		races = excludeParkrunEvents(races, conditions)
	if 'only_with_results' in form_params:
		races = filterRacesWithLoadedResults(races, conditions)

	event_ids = set(races.values_list('event__id', flat=True))
	events = models.Event.objects.filter(id__in=event_ids)
	
	events = events.select_related('series__city__region__country',
		'city__region__country', 'series__country').prefetch_related(
		Prefetch('race_set',
			queryset=models.Race.objects.select_related('distance').order_by(
				'distance__distance_type', '-distance__length', 'precise_name')),
		Prefetch('review_set', queryset=models.Document.objects.filter(document_type=models.DOC_TYPE_IMPRESSIONS)),
		Prefetch('photo_set', queryset=models.Document.objects.filter(document_type=models.DOC_TYPE_PHOTOS)),
		Prefetch('news_set', queryset=models.News.objects.order_by('-date_posted')),
		Prefetch('document_set',
			queryset=models.Document.objects.exclude(document_type__in=[9, 13]).order_by('document_type', 'comment')),
	).annotate(sum_finishers=Sum('race__n_participants_finished'))

	if ( results_util.int_safe(form_params.get('date_region', forms.DATE_REGION_DEFAULT))
			in [forms.DATE_REGION_FUTURE, forms.DATE_REGION_NEXT_WEEK, forms.DATE_REGION_NEXT_MONTH] ) \
			or ( ('date_from' in form_params) and (form_params['date_from'] >= today)):
		events = events.order_by('start_date', 'name')
		context['show_n_finished'] = False
	else:
		events = events.order_by('-start_date', 'name')
		context['show_n_finished'] = True

	if form is None:
		form = forms.EventForm(initial=initial)
	context['list_title'] = list_title + " " + ", ".join(conditions)
	context['form'] = form
	context['page_title'] = context['list_title']
	return paginate_and_render(request, 'results/races2.html' if view else 'results/races.html', context, events)

def add_races_annotations(races):
	return races.select_related('distance', 'distance_real').order_by('distance__distance_type', '-distance__length', 'precise_name')

def event_races_for_context(event):
	return add_races_annotations(event.race_set)

def filter_results_by_name(race, results, name):
	if race.distance.distance_type != models.TYPE_MINUTES:
		result = models.string2centiseconds(name)
		if result > 0:
			return results.filter(result__gte=result)
	return results.filter(Q(fname__icontains=name) | Q(lname__icontains=name) | Q(club_name__icontains=name))

def claim_results(request, race, klb_status):
	user = request.user
	results_claimed = 0
	results_claimed_for_klb = 0
	runners_for_user = user.user_profile.get_runners_to_add_results(race, race_is_for_klb = (klb_status == models.KLB_STATUS_OK))
	runners_touched = set()
	race_date = race.start_date if race.start_date else race.event.start_date
	for key, val in request.POST.items():
		val = results_util.int_safe(val)
		if key.startswith("for_result_") and val:
			result_id = results_util.int_safe(key[len("for_result_"):])
			result = race.result_set.filter(pk=result_id).first()
			if result is None:
				messages.warning(request, u'Результат с id {} не найден. Пропускаем'.format(result_id))
				continue
			if result.runner:
				runner = result.runner
				messages.warning(request, u'Результат {} уже привязан к участнику забегов {}. Пропускаем'.format(
					result, runner.get_name_and_id()))
				continue

			runner = models.Runner.objects.filter(pk=val).first()
			if runner is None:
				messages.warning(request, u'Участник забегов с id {} не найден. Пропускаем'.format(val))
				continue

			if runner not in runners_for_user:
				messages.warning(request, u'У Вас нет прав на добавление результата участнику {}'.format(runner.get_name_and_id()))
				continue

			if runner in runners_touched:
				messages.warning(request, u'Мы только что уже привязали один результат бегуну {}. Пропускаем '.format(runner.get_name_and_id()))
				continue

			if runners_for_user[runner]['is_already_in_race']:
				messages.warning(request, u'У бегуна {} уже есть результат на этой дистанции забега. Пропускаем '.format(
					runner.get_name_and_id()))
				continue

			is_for_klb = ('for_klb_{}'.format(result_id) in request.POST)
			participant = None
			if is_for_klb:
				if klb_status != models.KLB_STATUS_OK:
					messages.warning(request, u'Эта дистанция не может быть засчитана в КЛБМатч: {}'.format(
						models.KLB_STATUSES[klb_status][1]))
					is_for_klb = False
				elif not result.is_ok_for_klb():
					messages.warning(request, u'Результат {} слишком мал для КЛБМатча'.format(result))
					is_for_klb = False
				elif not hasattr(runner, 'klb_person'):
					messages.warning(request, u'{} не участвует в КЛБМатче. На модерацию в матч результат не отправляем'.format(
						runner.get_name_and_id()))
					is_for_klb = False
				elif not runners_for_user[runner]['is_in_klb']:
					messages.warning(request, u'У Вас нет прав на добавление результата бегуну {} в КЛБМатч'.format(runner.get_name_and_id()))
					is_for_klb = False
				else:
					participant = runner.klb_person.klb_participant_set.filter(match_year=race_date.year).first()
					if participant is None:
						messages.warning(request, u'{} не участвует в КЛБМатче. На модерацию в матч результат не отправляем'.format(
							runner.get_name_and_id()))
						is_for_klb = False
					elif participant.date_registered and (participant.date_registered > race_date):
						messages.warning(request, u'Участник {} был включён в команду только {}. Его результат не будет учтён в КЛБМатче'.format(
							runner.name(), participant.date_registered.strftime('%d.%m.%Y')))
						is_for_klb = False
					elif participant.date_removed and (participant.date_removed < race_date):
						messages.warning(request, u'Участник {} был исключён из команды уже {}. Его результат не будет учтён в КЛБМатче'.format(
							runner.name(), participant.date_removed.strftime('%d.%m.%Y')))
						is_for_klb = False
			res, message = result.claim_for_runner(user, runner, comment=u'Массовая привязка на странице забега',
				is_for_klb=is_for_klb and not models.is_admin(user))
			if res:
				results_claimed += 1
				if is_for_klb:
					results_claimed_for_klb += 1
					if models.is_admin(user):
						views_klb.create_klb_result(result, runner.klb_person, user, comment=u'Массовая привязка на странице забега',
							participant=participant)
				runners_touched.add(runner)
			else:
				messages.warning(request, u'Результат {} участнику {} {} не засчитан. Причина: {}'.format(
					unicode(result), person.fname, person.lname, message))
	for runner in runners_touched:
		views_stat.update_runner_stat(runner=runner)
		if runner.user:
			views_stat.update_runner_stat(user=runner.user, update_club_members=False)
	if results_claimed:
		messages.success(request, u'Засчитано результатов: {}'.format(results_claimed))
		if results_claimed_for_klb:
			messages.success(request, u'Из них будут посчитаны в КЛБМатч после одобрения администраторами: {}'.format(results_claimed_for_klb))
		race.fill_winners_info()

def constants_for_event_context(user, event):
	context = {}
	context['series'] = event.series
	context['event'] = event
	context['races'] = event_races_for_context(event)
	context['has_races_with_and_wo_results'] = event.race_set.filter(loaded=models.RESULTS_LOADED).exists() \
		and event.race_set.filter(loaded=models.RESULTS_NOT_LOADED).exists()
	context['can_add_results_to_others'] = user.is_authenticated() and user.user_profile.can_add_results_to_others()
	context['n_races'] = event.race_set.count()
	return context

TAB_DEFAULT = 0
TAB_EDITOR = 1
TAB_UNOFFICIAL = 2
TAB_ADD_TO_CLUB = 3
TAB_KLB = 4
def constants_for_race_context(user, event):
	context = constants_for_event_context(user, event)
	context['TAB_DEFAULT'] = TAB_DEFAULT
	context['TAB_EDITOR'] = TAB_EDITOR
	context['TAB_UNOFFICIAL'] = TAB_UNOFFICIAL
	context['TAB_ADD_TO_CLUB'] = TAB_ADD_TO_CLUB
	context['TAB_KLB'] = TAB_KLB
	context['RESULTS_SOME_OR_ALL_OFFICIAL'] = models.RESULTS_SOME_OR_ALL_OFFICIAL
	return context

def race_details(request, race_id=None, tab_editor=False, tab_unofficial=False, tab_add_to_club=False):
	race = get_object_or_404(models.Race, pk=race_id)
	event = race.event
	series = event.series
	user = request.user

	context = user_edit_vars(user, series=series)
	if event.invisible and not (context['is_admin'] or context['is_editor']):
		raise Http404()

	request_params = request.POST if request.method == 'POST' else request.GET
	context.update(constants_for_race_context(user, event))
	context['race'] = race

	tab = TAB_DEFAULT
	if tab_editor and (context['is_admin'] or context['is_editor']):
		tab = TAB_EDITOR
	elif tab_unofficial and (context['is_admin'] or context['is_editor']):
		tab = TAB_UNOFFICIAL
	elif tab_add_to_club and context['can_add_results_to_others']:
		tab = TAB_ADD_TO_CLUB

	klb_status = race.get_klb_status()
	context['race_is_ok_for_klb'] = (klb_status == models.KLB_STATUS_OK)

	context['page_title'] = u'{}: результаты забега'.format(event)

	page = None
	if (race.loaded in models.RESULTS_SOME_OR_ALL_OFFICIAL) and context['can_add_results_to_others'] \
			and ( ('frmResults_claim' in request_params) or ('frmResults_claim_nextpage' in request_params) ):
		claim_results(request, race, klb_status)
		if 'frmResults_claim_nextpage' in request_params:
			page = get_page_num(request) + 1

	results = race.get_official_results()
	context['race_has_results'] = results.exists() # When filters show 0 results, we need to show filters anyway!
	context['event_has_protocol'] = event.document_set.filter(document_type__in=models.DOC_PROTOCOL_TYPES).exists()
	context['tab'] = tab
	filtered_results = results.select_related('runner', 'user__user_profile', 'klb_result__klb_person', 'result_on_strava')
	if context['race_has_results'] and (tab != TAB_UNOFFICIAL):
		initial = {}
		if request_params.get('gender'):
			initial['gender'] = request_params['gender']
			filtered_results = filtered_results.filter(gender=request_params['gender'])
		if request_params.get('category'):
			initial['category'] = results_util.int_safe(request_params['category'])
			filtered_results = filtered_results.filter(category_size_id=initial['category'])
		if request_params.get('name'):
			name = request_params['name'].strip()
			initial['name'] = name
			filtered_results = filter_results_by_name(race, filtered_results, name)
		context['resultFilterForm'] = forms.ResultFilterForm(race, initial=initial)
		context['can_claim_result'] = user.is_authenticated() and not results.filter(user=user).exists()
	else:
		context['unofficial_results'] = race.get_unofficial_results()
		context['unoff_results_with_splits'] = get_results_with_splits_ids(context['unofficial_results'])

		context['year'] = event.start_date.year
		context['can_add_result'] = user.is_authenticated() and not context['unofficial_results'].filter(user=user).exists()
		if context['is_admin']:
			context['frmClubAndNumber'] = forms.ClubAndNumberForm()
		elif user.is_authenticated():
			context['club_set'] = user.user_profile.get_club_set_to_add_results()
	if tab == TAB_ADD_TO_CLUB:
		context['runners'] = user.user_profile.get_runners_to_add_results(race, race_is_for_klb = (klb_status == models.KLB_STATUS_OK))
		context['user_is_female'] = user.user_profile.is_female()
	if klb_status == models.KLB_STATUS_OK:
		context['klb_pending_result_ids'] = set(models.Table_update.objects.filter(
			action_type__in=(models.ACTION_UNOFF_RESULT_CREATE, models.ACTION_RESULT_UPDATE),
			is_verified=False, is_for_klb=True, row_id=event.id).values_list('child_id', flat=True))
		context['was_not_checked_for_klb'] = (tab == TAB_DEFAULT) and context['race_has_results'] and not race.was_checked_for_klb
	context['klb_results_exist'] = race.result_set.exclude(klb_result=None).exists() or context.get('klb_pending_result_ids')

	if context['is_admin'] and event.is_in_past() and series.is_russian_parkrun():
		context['show_update_parkrun_results_button'] = True
		context['show_delete_skipped_parkrun_button'] = not event.document_set.filter(document_type=models.DOC_TYPE_PROTOCOL).exists()

	return paginate_and_render(request, 'results/race_details.html', context, filtered_results, page=page, add_results_with_splits=True)

def event_klb_results(request, event_id=None):
	event = get_object_or_404(models.Event, pk=event_id)
	series = event.series
	user = request.user
	context = user_edit_vars(user, series=series)
	if event.invisible and not (context['is_admin'] or context['is_editor']):
		raise Http404()
	context.update(constants_for_race_context(user, event))
	context['tab'] = TAB_KLB
	context['klb_results'] = event.klb_result_set.select_related('result', 'race__distance', 'klb_person',
		'klb_participant__team__club__city__region__country').order_by(
		'race__distance__distance_type', '-race__distance__length', 'race__precise_name', '-klb_score')
	context['page_title'] = u'{}: результаты забега, учтённые в КЛБМатче'.format(event)
	return render(request, 'results/race_details.html', context)

def calendar_content(event, races):
	context = {}
	context['n_plans'] = 0
	context['plans_by_distance'] = []
	if races.count() > 1:
		for race in races:
			items = race.calendar_set.select_related('user__user_profile').filter(user__is_active=True)
			items_count = items.count()
			if items_count:
				context['plans_by_distance'].append((race.distance_with_details(details_level=0), items, items_count))
				context['n_plans'] += items_count
		items = event.calendar_set.select_related('user__user_profile').filter(race=None, user__is_active=True)
		items_count = items.count()
		if items_count:
			context['plans_by_distance'].append((u'не указали дистанцию', items, items_count))
			context['n_plans'] += items_count
	else:
		items = event.calendar_set.select_related('user__user_profile').filter(user__is_active=True)
		items_count = items.count()
		if items_count:
			context['plans_by_distance'].append((u'', items, items_count))
			context['n_plans'] += items_count
	return context

def event_details(request, event_id=None, beta=0):
	event = get_object_or_404(models.Event, pk=event_id)
	series = event.series
	user = request.user
	context = user_edit_vars(user, series=series)
	if event.invisible and not (context['is_admin'] or context['is_editor']):
		raise Http404()

	context.update(constants_for_event_context(user, event))
	context.update(calendar_content(event, context['races']))

	context['page_title'] = u'{}, {}'.format(event, event.dateFull())
	if user.is_authenticated():
		context['calendar'] = user.calendar_set.filter(event=event).first()
		# context['is_participant'] = user.result_set.filter(race__event=event).exists()
		context['is_authenticated'] = True

	context['reviews'] = models.Document.objects.filter(event=event, document_type=models.DOC_TYPE_IMPRESSIONS).order_by('author')
	context['photos'] = models.Document.objects.filter(event=event, document_type=models.DOC_TYPE_PHOTOS).order_by('author')
	context['news_set'] = event.news_set.order_by('-date_posted')
	if context['is_admin'] or (context['is_editor'] and event.can_be_edited):
		context['news_set'] = context['news_set'].prefetch_related('social_post_set')
		districts = set([None])
		for city in [event.city, event.city_finish, series.city, series.city_finish]:
			if city and city.region.district:
				districts.add(city.region.district)
		context['social_pages'] = models.Social_page.objects.filter(Q(district__in=districts) | Q(district__isnull=True))
	else:
		context['news_set'] = context['news_set'].filter(is_for_social=False)

	if context['is_admin'] and event.race_set.filter(loaded=models.RESULTS_LOADED).exists() and \
			event.race_set.filter(loaded=models.RESULTS_NOT_LOADED).exists():
		context['show_remove_races_link'] = True

	# For Sportmaster campaign (2017-04)
	# if user.is_authenticated() and hasattr(user, 'user_profile') and user.user_profile.gender == models.GENDER_FEMALE:
	# 	context['user_is_female'] = True

	context['sr_event'] = get_sr_overall_data(event, context['to_show_rating'])

	if beta:
		return render(request, 'results/event_details_goprotect.html', context)
	else:
		return render(request, 'results/event_details.html', context)

@login_required
def add_event_to_calendar(request, event_id):
	event = get_object_or_404(models.Event, pk=event_id)
	race_id = request.GET.get('race_id', False)
	if race_id:
		race = get_object_or_404(models.Race, pk=race_id)
	else: # If there is only one race in the event, we use it
		races = event.race_set.all()
		if races.count() == 1:
			race = races.first()
		else:
			race = None

	res, message = event.add_to_calendar(race, request.user)
	if res:
		messages.success(request, u'Забег «{}» успешно добавлен в Ваш календарь.'.format(unicode(race.name_with_event() if race else event)))
	else:
		messages.warning(request, u'Забег «{}» не добавлен в Ваш календарь. Причина: {}'.format(unicode(event), message))
	return redirect(event)

@login_required
def remove_event_from_calendar(request, event_id):
	event = get_object_or_404(models.Event, pk=event_id)
	res, message = event.remove_from_calendar(request.user)
	if res:
		messages.success(request, u'Забег «{}» успешно удалён из Вашего календаря.'.format(unicode(event)))
	else:
		messages.warning(request, u'Забег «{}» не удалён из Вашего календаря. Причина: {}'.format(unicode(event), message))
	return redirect(event)

def get_prefetch_race_set():
	return Prefetch('race_set',
				queryset=add_races_annotations(models.Race.objects).select_related(
					'winner_male_user__user_profile', 'winner_male_runner', 'winner_female_user__user_profile',
					'winner_female_runner', 'distance_real')
			)

def series_details(request, series_id, tab=None):
	series = get_object_or_404(models.Series, pk=series_id)
	user = request.user
	context = user_edit_vars(user, series=series)
	context['series'] = series

	# Otherwise there's no need to show cities of events
	context['city_needed'] = (series.city is None) or series.event_set.exclude(city=None).exclude(city=series.city).exists()

	events = series.event_set
	if not (context['is_admin'] or context['is_editor']):
		events = events.filter(invisible=False)

	today = datetime.date.today()
	events_in_past = events.filter(start_date__lte=today, cancelled=False, invisible=False)
	context['n_events_in_past'] = events_in_past.count()
	context['reviews_exist'] = series.has_news_reviews_photos()
	context['events_exist'] = events.exists()

	if tab == 'all_events':
		context['active_tab'] = "all_events"
		events = events.prefetch_related(
			get_prefetch_race_set(),
			Prefetch('document_set',
				queryset=models.Document.objects.exclude(document_type__in=models.DOC_TYPES_NOT_FOR_RIGHT_COLUMN).order_by(
					'document_type', 'comment')
			)
		)
		if not (context['is_admin'] or context['is_editor']):
			events = events.filter(invisible=False)

		events = events.order_by('-start_date', '-start_time')

		if len(events) > 20:   # Temporary hack. Todo.
			events_list = [(event, None) for event in events]
		else:
			events_list = [(event, get_sr_overall_data(event, context['to_show_rating'])) for event in events]

		context['events_list'] = events_list

	elif tab == 'races_by_event':
		context['active_tab'] = "races_by_event"
		events = events.annotate(
			n_participants_finished=Sum('race__n_participants_finished'),
			n_participants_finished_men=Sum('race__n_participants_finished_men'),
			n_races=Count('race'),
		).prefetch_related(get_prefetch_race_set())
		if not (context['is_admin'] or context['is_editor']):
			events = events.filter(invisible=False)
		context['events'] = events.order_by('-start_date', '-start_time')
	elif tab == 'races_by_distance':
		context['active_tab'] = "races_by_distance"
		events_in_past_ids = set(events.filter(start_date__lte=today, cancelled=False, invisible=False).values_list('id', flat=True))
		context['races'] = [{'distance': unicode(race.distance), 'race': race}
			for race in models.Race.objects.filter(event_id__in=events_in_past_ids).select_related(
				'winner_male_user__user_profile', 'winner_male_runner', 'winner_female_user__user_profile', 'winner_female_runner',
				'event__city__region__country', 'event__series__city__region__country', 'distance', 'distance_real').order_by(
				'distance__distance_type', '-distance__length', '-event__start_date')
		]
	elif tab == 'reviews' and context['reviews_exist']:
		context['active_tab'] = "reviews"
		links_dict = {}
		for doc_type, doc_type_name in ((models.DOC_TYPE_IMPRESSIONS, 'reviews'), (models.DOC_TYPE_PHOTOS, 'photos')):
			for doc in models.Document.objects.filter(event__series_id=series.id, document_type=doc_type).select_related('event'):
				if doc.event not in links_dict:
					links_dict[doc.event] = {'reviews': [], 'photos': [], 'news': []}
				links_dict[doc.event][doc_type_name].append(doc)
		for news in models.News.objects.filter(event__series_id=series.id).select_related('event').order_by('-date_posted'):
			if news.event not in links_dict:
				links_dict[news.event] = {'reviews': [], 'photos': [], 'news': []}
			links_dict[news.event]['news'].append(news)
		context['events_links'] = sorted(links_dict.items(), key=lambda x:x[0].start_date, reverse=True)
	else:
		context['active_tab'] = 'default'

		future_events = events.filter(start_date__gt=today, cancelled=False, invisible=False)
		context['event_next'] = future_events.order_by('start_date').first()
		if context['event_next']:
			context['n_future_events'] = future_events.count() - 1 # Excluding event_next
			context['event_next_race_set'] = event_races_for_context(context['event_next'])
			if user.is_authenticated():
				context['calendar'] = user.calendar_set.filter(event=context['event_next']).first()
				context['user_is_authenticated'] = True

		event_prev = events_in_past.order_by('-start_date').first()
		if event_prev:
			context['event_prev'] = event_prev
			context['event_prev_race_set'] = event_races_for_context(event_prev)
			context['user_has_no_results_on_event_prev'] = user.is_authenticated() \
				and not user.result_set.filter(race__event=event_prev).exists()

			sums = event_prev.race_set.aggregate(Sum('n_participants_finished'), Sum('n_participants_finished_men'))
			context['event_prev_n_finishers'] = sums['n_participants_finished__sum']
			context['event_prev_n_finishers_men'] = sums['n_participants_finished_men__sum']
			context['event_prev_has_results'] = context['event_prev_n_finishers'] > 0
			context['event_prev_has_partially_loaded_races'] = event_prev.race_set.filter(loaded=models.RESULTS_SOME_OFFICIAL).exists()

		if context['n_events_in_past'] > 1:
			context['event_first'] = events_in_past.order_by('start_date').first()
			races_by_distance = {}
			event_sizes_by_distance = {}
			events_size = {}
			male_records = {}
			female_records = {}
			for race in models.Race.objects.filter(event_id__in=events_in_past.values_list('id', flat=True)).select_related(
					'event', 'distance', 'distance_real'):
				distance = race.distance

				if distance not in races_by_distance:
					races_by_distance[distance] = []
				races_by_distance[distance].append(race)

				if race.is_male_course_record:
					male_records[distance] = race
				if race.is_female_course_record:
					female_records[distance] = race

				if race.n_participants_finished > 0:
					events_size[race.event] = events_size.get(race.event, 0) + race.n_participants_finished
					if distance not in event_sizes_by_distance:
						event_sizes_by_distance[distance] = Counter()
					event_sizes_by_distance[distance][race.event] += race.n_participants_finished

			context['n_prev_events_with_results'] = len(events_size)
			context['prev_distances'] = []
			for distance, races in sorted(races_by_distance.items(), key=lambda x: (x[0].distance_type, -x[0].length)):
				data = {}
				data['distance'] = distance
				data['n_starts'] = len(set(race.event_id for race in races))
				dates = sorted([(race.event.start_date, race) for race in races])
				data['first_race'] = min(dates)
				data['last_race'] = max(dates)
				if distance in event_sizes_by_distance:
					data['n_starts_with_results'] = len(event_sizes_by_distance[distance])
					data['max_event'], data['max_size'] = event_sizes_by_distance[distance].most_common(1)[0]
					data['mean_size'] = sum(event_sizes_by_distance[distance].values()) / data['n_starts_with_results']
				else:
					data['n_starts_with_results'] = 0
				data['race_with_male_record'] = male_records.get(distance)
				data['race_with_female_record'] = female_records.get(distance)
				context['prev_distances'].append(data)

			if events_size:
				context['max_event_size'] = max(events_size.values())
				context['mean_event_size'] = sum(events_size.values()) / len(events_size)
				for event, size in events_size.items():
					if size == context['max_event_size']:
						context['max_event'] = event
						break

	context['page_title'] = u'{}: все забеги серии'.format(series.name)

	context['sr_series'] = get_sr_overall_data(series, context['to_show_rating'])

	return render(request, 'series/{}.html'.format(context['active_tab']), context)

def protocols_wanted(request, events_type=forms.PROTOCOL_ABSENT):
	context = user_edit_vars(request.user)
	form = None
	events_type = results_util.int_safe(events_type)
	year = models.CUR_KLB_YEAR - 1 # TODO
	region = models.Region.objects.filter(pk=forms.DEFAULT_REGION_ID).first()
	if request.method == 'POST':
		form = forms.ProtocolHelpForm(request.POST)
		if form.is_valid():
			events_type = results_util.int_safe(form.cleaned_data['events_type'])
			year = results_util.int_safe(form.cleaned_data['year'])
			region = form.cleaned_data['region']
		else:
			form = None
	if form is None:
		form = forms.ProtocolHelpForm()
	context['form'] = form

	races_wo_results = models.Race.objects.filter(loaded=0, has_no_results=False)
	if year:
		races_wo_results = races_wo_results.filter(event__start_date__year=year)
	events_wo_results_ids = set(races_wo_results.values_list('event_id', flat=True))

	events_with_protocol = models.Document.objects.filter(document_type__in=models.DOC_PROTOCOL_TYPES)
	if year:
		events_with_protocol = events_with_protocol.filter(event__start_date__year=year)
	events_with_protocol_ids = set(events_with_protocol.values_list('event_id', flat=True))

	events = models.Event.objects.filter(
		Q(city__region=region) | Q(series__city__region=region),
		start_date__lte=datetime.date.today() - datetime.timedelta(days=14),
		cancelled=False,
		invisible=False,
		).prefetch_related(
			Prefetch('race_set',queryset=models.Race.objects.select_related(
				'distance').annotate(Count('result')).order_by('distance__distance_type', '-distance__length'))
			).order_by('start_date')

	context['page_title'] = u'Забеги в {} {} '.format(u'регионе' if region.active else u'стране', region.name, year)
	if year:
		context['page_title'] += u'в {} году '.format(year)
	else:
		context['page_title'] += u'за все годы '
	if events_type == forms.PROTOCOL_ABSENT:
		events = events.filter(pk__in=events_wo_results_ids - events_with_protocol_ids)
		context['page_title'] += u'без протоколов'
	else: #if events_type == forms.PROTOCOL_BAD_FORMAT:
		events_with_xls_protocol = models.Document.objects.filter(models.Q_IS_XLS_FILE)
		if year:
			events_with_xls_protocol = events_with_xls_protocol.filter(event__start_date__year=year)
		events_with_xls_protocol_ids = set(events_with_xls_protocol.values_list('event_id', flat=True))
		events = events.filter(pk__in=(events_wo_results_ids & events_with_protocol_ids) - events_with_xls_protocol_ids).prefetch_related(
			Prefetch('document_set', queryset=models.Document.objects.filter(document_type__in=models.DOC_PROTOCOL_TYPES)))
		context['page_title'] += u'с протоколами в неудобных форматах'
	context['events_type'] = events_type
	context['events'] = events
	return render(request, 'results/protocols_wanted.html', context)

def rating(request, country_id=None, distance_id=None, year=None, rating_type=None):
	context = user_edit_vars(request.user)
	form = None
	if request.method == 'POST':
		form = forms.RatingForm(request.POST)
	elif country_id:
		form = forms.RatingForm({
			'country_id': country_id,
			'distance_id': results_util.DISTANCE_CODES_INV.get(distance_id),
			'year': year,
			'rating_type': forms.RATING_TYPES_CODES_INV.get(rating_type),
		})
	if (form is None) or (not form.is_valid()):
		context['page_title'] = u'Рейтинг забегов по версии сайта «ПроБЕГ»'
		context['ratingForm'] = forms.RatingForm()
		return render(request, 'results/rating.html', context)

	context['show_rating'] = True
	context['ratingForm'] = form

	country_id = form.cleaned_data['country_id']
	country = models.Country.objects.filter(pk=country_id).first()

	distance_id = results_util.int_safe(form.cleaned_data['distance_id'])
	distance = models.Distance.objects.filter(pk=distance_id).first()

	year = results_util.int_safe(form.cleaned_data['year'])
	rating_type = results_util.int_safe(form.cleaned_data['rating_type'])
	context['value_name'] = forms.RATING_TYPES[rating_type][1]

	if distance:
		title_distance = u'Лучшие забеги на дистанцию {}'.format(distance.name)
	elif distance_id == results_util.DISTANCE_ANY:
		title_distance = u'Крупнейшие забеги на любую дистанцию'
		context['show_distance_column'] = True
	elif distance_id == results_util.DISTANCE_WHOLE_EVENTS:
		title_distance = u'Крупнейшие забеги'

	if year:
		title_year = u'в {} году'.format(year)
	else:
		title_year = u'за все годы'
	context['page_title'] = u'{} {} {} по {}'.format(
		title_distance, forms.get_degree_from_country(country), title_year, forms.RATING_TYPES_DEGREES[rating_type][1])
	context['link'] = reverse('results:rating', kwargs={
		'country_id': country.id if country else forms.RATING_COUNTRY_ALL,
		'distance_id': results_util.DISTANCE_CODES[distance_id],
		'year': year,
		'rating_type': forms.RATING_TYPES_CODES[rating_type]})

	if country:
		country_ids = [country.id]
	else:
		country_ids = forms.RATING_COUNTRY_IDS

	if distance_id == results_util.DISTANCE_WHOLE_EVENTS:
		context['rating_by_whole_events'] = True
		events = models.Event.get_events_by_countries(year, country_ids)
		if rating_type == forms.RATING_N_FINISHERS:
			events = events.annotate(rating_value=Sum('race__n_participants_finished'))
		elif rating_type == forms.RATING_N_FINISHERS_MALE:
			events = events.annotate(rating_value=Sum('race__n_participants_finished_men'))
		elif rating_type == forms.RATING_N_FINISHERS_FEMALE:
			events = events.annotate(rating_value=Sum('race__n_participants_finished')-Sum('race__n_participants_finished_men'))
		events = events.filter(rating_value__gt=0)
		filtered_results = events.select_related('series__city__region__country', 'city__region__country').prefetch_related(
			Prefetch('race_set',
				queryset=models.Race.objects.select_related('distance').order_by(
					'distance__distance_type', '-distance__length', 'precise_name')),
		).order_by('-rating_value')
	else:
		races = models.Race.get_races_by_countries(year, country_ids)
		if distance:
			races = races.filter(distance=distance)
		if rating_type in forms.RATING_TYPES_BY_FINISHERS:
			context['rating_by_n_finishers'] = True
			if rating_type == forms.RATING_N_FINISHERS:
				races = races.filter(n_participants_finished__gt=0).annotate(rating_value=F('n_participants_finished'))
			elif rating_type == forms.RATING_N_FINISHERS_MALE:
				races = races.filter(n_participants_finished_men__gt=0).annotate(rating_value=F('n_participants_finished_men'))
			elif rating_type == forms.RATING_N_FINISHERS_FEMALE:
				races = races.annotate(rating_value=F('n_participants_finished')-F('n_participants_finished_men')).filter(rating_value__gt=0)
			filtered_results = races.select_related(
				'event__series__city__region__country', 'event__city__region__country').order_by('-rating_value')
		else:
			result_ordering = '-result' if (distance.distance_type == models.TYPE_MINUTES) else 'result'
			context['rating_by_best_result'] = True
			races = races.filter(Q(distance_real=None) | Q(distance_real__length__gt=distance.length), is_for_handicapped=False)
			if rating_type == forms.RATING_BEST_MALE:
				results = models.Result.objects.filter(
					race__in=races, place_gender=1, gender=models.GENDER_MALE, status=models.STATUS_FINISHED)
			elif rating_type == forms.RATING_BEST_FEMALE:
				results = models.Result.objects.filter(
					race__in=races, place_gender=1, gender=models.GENDER_FEMALE, status=models.STATUS_FINISHED)
			filtered_results = results.select_related(
				'race__event__series__city__region__country', 'race__event__city__region__country').order_by(result_ordering)
	return paginate_and_render(request, 'results/rating.html', context, filtered_results)

def get_logo_page(request, event_id=None, series_id=None, organizer_id=None):
	context = {}
	if event_id:
		event = get_object_or_404(models.Event, pk=event_id)
		context['image_url'] = add_prefix(event.get_url_logo())
	elif series_id:
		series = get_object_or_404(models.Series, pk=series_id)
		context['image_url'] = add_prefix(series.get_url_logo())
	elif organizer_id:
		organizer = get_object_or_404(models.Organizer, pk=organizer_id)
		context['image_url'] = add_prefix(organizer.logo)
	return render(request, "results/modal_image.html", context)

def old_registration(request, event_id):
	event = get_object_or_404(models.Event, pk=event_id)
	return redirect('http://89.253.222.57/registr/reg.php?id={}'.format(event.id))
	