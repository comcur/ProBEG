# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.contrib.auth.models import User
from django.db.models.query import Prefetch
from django.db.models import Count, Q, Sum
from django.utils import translation
from django.conf import settings
from collections import OrderedDict, Counter
import datetime
import re
import io
import os

from results import models, results_util
from editor.views.views_common import group_required
from editor.views.views_stat import get_stat_value, set_stat_value

TAB_MAIN = 0
TAB_LARGEST = 1
TAB_REGIONS = 2
TAB_AGE = 3
TAB_RESULTS = 4
TAB_DETAILS = 5

MIN_N_PARTICIPANTS_FOR_QUANTILES = 50 # Earlier it was 20

MIN_LENGTH_FOR_ULTRAMARATHON = 42500

PAGES_WITH_SHOW_ALL_OPTION = {
	2017: (2,),
	2018: (2,),
	2019: (2,),
}

FIRST_REPORT_YEAR = {'RU': 2016, 'BY': 2018}
DEFAULT_REPORT_YEAR = 2017
REPORT_GENERATING_YEAR = 2018

COUNTRIES_WITH_REPORTS = ('RU', 'BY')

TAB_NAMES = {
	2016: [
			u'Самое интересное',
			u'Часть 1. Основные дистанции',
			u'Часть 2. Забеги по регионам',
			u'Часть 3. Возраст участников',
			u'Часть 4. Результаты на основных дистанциях',
			u'Технические подробности',
		],
	2017: [
			u'Самое интересное',
			u'Часть 1. Основные дистанции',
			u'Часть 2. Забеги по регионам',
			u'Часть 3. Результаты на основных дистанциях',
			u'Технические подробности',
		],
	2018: [
			u'Самое интересное',
			u'Часть 1. Основные дистанции',
			u'Часть 2. Забеги по регионам',
			u'Часть 3. Результаты на основных дистанциях',
			u'Технические подробности',
		],
	2019: [
			u'Самое интересное',
			u'Часть 1. Основные дистанции',
			u'Часть 2. Забеги по регионам',
			u'Часть 3. Результаты на основных дистанциях',
			u'Технические подробности',
		],
}

def country_report(request, year, country_id, tab=TAB_MAIN, show_all=False):
	country = get_object_or_404(models.Country, pk=country_id, pk__in=COUNTRIES_WITH_REPORTS)
	country_name = country.nameEn.lower()

	year = results_util.int_safe(year)
	# if year == REPORT_GENERATING_YEAR: # Open me when preparing new report
	# 	return russia_report_generator(request, tab=tab, show_all=show_all)
	if year < FIRST_REPORT_YEAR[country.id]:
		year = DEFAULT_REPORT_YEAR

	context = {}
	context['year'] = year
	context['page_title'] = u'Бег на длинные дистанции в {}. Итоги {} года'.format(country.prep_case, year)
	context['tab_names'] = TAB_NAMES[year]
	context['prev_year_report_exists'] = (year > FIRST_REPORT_YEAR[country.id])

	tab = results_util.int_safe(tab)
	if not (0 <= tab < len(context['tab_names'])):
		tab = TAB_MAIN
	context['cur_tab_name'] = context['tab_names'][tab]
	context['tab'] = tab
	if tab < len(context['tab_names']) - 1:
		context['next_tab_name'] = context['tab_names'][tab + 1]

	if (country.id == 'RU') and (year == 2016):
		context['show_all'] = show_all
		return render(request, 'report_russia/{}/part{}.html'.format(year, tab), context=context)
	else:
		context['template_name'] = 'report_{}/{}/part{}{}.html'.format(country_name, year, tab, '_full' if show_all else '')
		return render(request, 'results/base_template.html', context=context)

def get_prev_year_event_n_participants(event):
	old_events = event.series.event_set.filter(start_date__year=event.start_date.year - 1)
	if event.series_id in (2057, 3545): # Hack for multi-sity series
		old_events = old_events.filter(city=event.city)
	if old_events.count() == 1:
		return old_events.first().race_set.aggregate(Sum('n_participants_finished'))['n_participants_finished__sum']
	return None

def get_prev_year_race_n_participants(race, try_similar_lengths):
	old_events = race.event.series.event_set.filter(start_date__year=race.event.start_date.year - 1)
	if old_events.count() == 1:
		old_event = old_events.first()
		old_races = old_event.race_set.filter(distance=race.distance)
		if old_races.exists():
			return old_races.aggregate(Sum('n_participants_finished'))['n_participants_finished__sum']
		if try_similar_lengths: # We try to find a race with similar distance, starting from longer ones
			length = race.distance.length
			first_old_race = old_event.race_set.filter(distance__distance_type=race.distance.distance_type,
				distance__length__range=(int(length * 0.85), int(length * 1.15))).order_by('-distance__length').first()
			if first_old_race:
				return old_event.race_set.filter(distance=first_old_race.distance).aggregate(
					Sum('n_participants_finished'))['n_participants_finished__sum']
	return None

def filterByRegionId(events, region_id):
	return events.filter(Q(city__region_id=region_id) | Q(city=None, series__city__region_id=region_id))

def get_context_for_new_report(country, year, tab, show_all):
	context = {}
	context['page_title'] = u'Бег на длинные дистанции в {}. Итоги {} года'.format(country.prep_case, year)
	context['year'] = year
	context['country'] = country
	context['tab_names'] = [
		u'Самое интересное',
		u'Часть 1. Основные дистанции',
		u'Часть 2. Забеги по регионам',
		u'Часть 3. Результаты на основных дистанциях',
		u'Технические подробности',
	]
	context['cur_tab_name'] = context['tab_names'][tab]
	context['tab'] = tab
	if tab < len(context['tab_names']) - 1:
		context['next_tab_name'] = context['tab_names'][tab + 1]
	context['show_all'] = show_all
	context['prev_year_report_exists'] = (year > FIRST_REPORT_YEAR[country.id])

	country_name = country.nameEn.lower()
	context['report_url'] = 'results:{}_report'.format(country_name)

	events = models.Event.get_events_by_countries(year, [country.id])
	events_old = models.Event.get_events_by_countries(year - 1, [country.id])
	events_2yr = models.Event.get_events_by_countries(year - 2, [country.id])

	races = models.Race.get_races_by_countries(year, [country.id])
	races_old = models.Race.get_races_by_countries(year - 1, [country.id])
	races_2yr = models.Race.get_races_by_countries(year - 2, [country.id])

	if tab == TAB_MAIN:
		context['show_manual_text'] = (year == 2019) and (country.id == 'RU')
		context['show_automatic_text'] = not context['show_manual_text']
		context['n_events_total'] = events.count()
		context['n_events_total_old'] = events_old.count()
		context['n_events_total_2yr'] = events_2yr.count()

		context['n_races_total'] = races.filter(n_participants_finished__gt=0).count()
		context['n_races_total_old'] = races_old.filter(n_participants_finished__gt=0).count()
		context['n_races_total_2yr'] = races_2yr.filter(n_participants_finished__gt=0).count()

		n_finishers_total = races.aggregate(Sum('n_participants_finished'), Sum('n_participants_finished_men'))
		n_finishers_total_old = races_old.aggregate(Sum('n_participants_finished'), Sum('n_participants_finished_men'))
		context['n_finishers_total'] = n_finishers_total['n_participants_finished__sum']
		context['n_finishers_total_old'] = n_finishers_total_old['n_participants_finished__sum']
		context['n_finishers_total_thousands'] = context['n_finishers_total'] // 1000

		context['n_finishers_women'] = context['n_finishers_total'] - n_finishers_total['n_participants_finished_men__sum']
		context['n_finishers_women_old'] = context['n_finishers_total_old'] - n_finishers_total_old['n_participants_finished_men__sum']

		if country.id == 'RU':
			for city_id, city_name in ((models.CITY_MOSCOW_ID, 'moscow'), (models.CITY_SAINT_PETERSBURG_ID, 'petersburg')):
				region_id = models.City.objects.get(pk=city_id).region_id
				Q_for_event = Q(city__region_id=region_id) | Q(city=None, series__city__region_id=region_id)
				Q_for_race = Q(event__city__region_id=region_id) | Q(event__city=None, event__series__city__region_id=region_id)
				context['n_events_{}'.format(city_name)] = events.filter(Q_for_event).count()
				context['n_events_{}_old'.format(city_name)] = events_old.filter(Q_for_event).count()
				context['n_finishers_{}'.format(city_name)] = races.filter(Q_for_race).aggregate(
					Sum('n_participants_finished'))['n_participants_finished__sum']
				context['n_finishers_{}_old'.format(city_name)] = races_old.filter(Q_for_race).aggregate(
					Sum('n_participants_finished'))['n_participants_finished__sum']

		context['n_distinct_participants_thousands'] = get_stat_value('n_distinct_runners_{}_{}'.format(country.id, year)) // 1000
		context['n_distinct_participants_thousands_old'] = get_stat_value('n_distinct_runners_{}_{}'.format(country.id, year - 1)) // 1000

		if country.id == 'RU':
			parkrun_series_ids = models.Series.get_russian_parkruns().values_list('id', flat=True)
			parkrun_races = models.Race.objects.filter(event__series_id__in=parkrun_series_ids, event__start_date__year=year).filter(
				n_participants_finished__gt=0)
			parkrun_races_old = models.Race.objects.filter(event__series_id__in=parkrun_series_ids, event__start_date__year=year - 1).filter(
				n_participants_finished__gt=0)
			context['n_events_parkrun'] = parkrun_races.count()
			context['n_events_parkrun_old'] = parkrun_races_old.count()
			context['n_events_parkrun_percent'] = int(round(100 * context['n_events_parkrun'] / context['n_events_total']))
			context['n_parkrun_cities'] = len(set(parkrun_races.values_list('event__series__city_id', flat=True)))
			context['n_parkrun_cities_old'] = len(set(parkrun_races_old.values_list('event__series__city_id', flat=True)))

			context['n_events_wo_parkrun'] = context['n_events_total'] - context['n_events_parkrun']
			context['n_events_wo_parkrun_old'] = context['n_events_total_old'] - context['n_events_parkrun_old']

			context['n_events_moscow'] = filterByRegionId(events, models.REGION_MOSCOW_ID).count()
			context['n_events_moscow_old'] = filterByRegionId(events_old, models.REGION_MOSCOW_ID).count()
			context['n_events_moscow_ratio'] = (100 * context['n_events_moscow']) // context['n_events_total']
			context['n_events_moscow_ratio_old'] = (100 * context['n_events_moscow_old']) // context['n_events_total_old']

			context['n_events_petersburg'] = filterByRegionId(events, models.REGION_SAINT_PETERSBURG_ID).count()
			context['n_events_petersburg_old'] = filterByRegionId(events_old, models.REGION_SAINT_PETERSBURG_ID).count()
			context['n_events_petersburg_ratio'] = (100 * context['n_events_petersburg']) // context['n_events_total']
			context['n_events_petersburg_ratio_old'] = (100 * context['n_events_petersburg_old']) // context['n_events_total_old']

			context['n_events_moscow_region'] = filterByRegionId(events, 47).count()
			context['n_events_moscow_region_old'] = filterByRegionId(events_old, 47).count()

			context['n_events_petersburg_region'] = filterByRegionId(events, 41).count()
			context['n_events_petersburg_region_old'] = filterByRegionId(events_old, 41).count()

		context['largest_events'] = []
		for event in events.annotate(
			np=Sum('race__n_participants_finished'), np_men=Sum('race__n_participants_finished_men')).prefetch_related(
				Prefetch('race_set',
				queryset=models.Race.objects.select_related('distance').filter(precise_name='').order_by(
					'distance__distance_type', '-distance__length', 'precise_name')
		)).select_related('series__city__region').order_by('-np')[:10]:
			men_percent = min(100, int(event.np_men * 100 / event.np))
			context['largest_events'].append({
				'event': event,
				'percent_men': men_percent,
				'percent_women': 100 - men_percent,
				'n_participants_old': get_prev_year_event_n_participants(event),
			})

	elif tab == TAB_RESULTS:
		context['n_events'] = events.count()
		context['n_events_old'] = events_old.count()

		context['n_races'] = races.count()
		context['n_races_old'] = races_old.count()

		races_with_results = races.filter(loaded=models.RESULTS_LOADED)
		races_with_results_old = races_old.filter(loaded=models.RESULTS_LOADED)
		context['n_races_with_results'] = races_with_results.count()
		context['n_races_with_results_old'] = races_with_results_old.count()

		context['n_races_only_n_finishers'] = races.exclude(loaded=models.RESULTS_LOADED).filter(
			n_participants_finished__gt=0).count()

		n_results_considered = races_with_results.aggregate(Sum('n_participants_finished'), Sum('n_participants_finished_men'))
		context['n_results_considered'] = n_results_considered['n_participants_finished__sum']
		context['n_results_considered_women'] = context['n_results_considered'] - n_results_considered['n_participants_finished_men__sum']
		context['n_results_considered_old'] = races_with_results_old.aggregate(
			Sum('n_participants_finished'))['n_participants_finished__sum']

		context['MIN_N_PARTICIPANTS_FOR_QUANTILES'] = MIN_N_PARTICIPANTS_FOR_QUANTILES

		context['n_good_races'] = []
		context['n_good_races_old'] = []
		for distance_id in results_util.DISTANCES_TOP_FOUR:
			context['n_good_races'].append(races_with_results.filter(
				distance_id=distance_id,
				n_participants_finished__gte=MIN_N_PARTICIPANTS_FOR_QUANTILES,
				event__series__surface_type__in=(models.SURFACE_DEFAULT, models.SURFACE_HARD),
				event__surface_type__in=(models.SURFACE_DEFAULT, models.SURFACE_HARD),
				surface_type__in=(models.SURFACE_DEFAULT, models.SURFACE_HARD),
				distance_real=None,
			).count())
			context['n_good_races_old'].append(races_with_results_old.filter(
				distance_id=distance_id,
				n_participants_finished__gte=MIN_N_PARTICIPANTS_FOR_QUANTILES,
				event__series__surface_type__in=(models.SURFACE_DEFAULT, models.SURFACE_HARD),
				event__surface_type__in=(models.SURFACE_DEFAULT, models.SURFACE_HARD),
				surface_type__in=(models.SURFACE_DEFAULT, models.SURFACE_HARD),
				distance_real=None,
			).count())

	elif tab == TAB_LARGEST:
		distances = list(races.values('distance').annotate(Count('distance'), Sum('n_participants_finished')))
		distances_old = list(races_old.values('distance').annotate(Count('distance'), Sum('n_participants_finished')))
		distances_old_count_dict = {x['distance']: x['distance__count'] for x in distances_old}
		distances_old_participants_dict = {x['distance']: x['n_participants_finished__sum'] for x in distances_old}

		context['top_distances_count'] = [(
				models.Distance.objects.get(pk=x['distance']),
				x['distance__count'],
				distances_old_count_dict.get(x['distance'])
			) for x in sorted(distances, key=lambda x:-x['distance__count'])[:10]]

		context['top_distances_finishers'] = [(
				models.Distance.objects.get(pk=x['distance']),
				x['n_participants_finished__sum'],
				distances_old_participants_dict.get(x['distance'])
			) for x in sorted(distances, key=lambda x:-x['n_participants_finished__sum'] if x['n_participants_finished__sum'] else 0)[:10]]

		bad_race_ids = set() # Races with incorrect results, e.g. too fast ones
		if year == 2019:
			bad_race_ids = set([53309, 51238, 44785])
		elif year == 2018:
			bad_race_ids = set([36171])

		context['main_distances'] = []
		for distance_id in results_util.DISTANCES_FOR_REPORT_LARGEST_EVENTS:
			distance = models.Distance.objects.get(pk=distance_id)
			distance_races = races.filter(distance=distance).exclude(pk__in=bad_race_ids)
			if distance_races.exists():
				races_dict = get_largest_races_best_results_dict(distance_races, distance,
					5 if (distance_id == results_util.DIST_100KM_ID) else 10, distance_id not in (results_util.DIST_5KM_ID, ))
				races_dict['distance'] = distance
				context['main_distances'].append(races_dict)

		context['main_distances_race_needed'] = []

		ultra_races = races.filter(Q(distance_real=None) | Q(distance_real__length__gte=MIN_LENGTH_FOR_ULTRAMARATHON),
			distance__distance_type=models.TYPE_METERS, distance__length__gte=MIN_LENGTH_FOR_ULTRAMARATHON, is_multiday=False)
		context['main_distances_race_needed'].append(get_largest_races_best_results_dict(ultra_races, u'Ультрамарафоны', 10, False))

		TRAIL_SURFACES = (models.SURFACE_SOFT, models.SURFACE_MOUNTAIN)
		trail_races = races.filter(Q(surface_type__in=TRAIL_SURFACES)
			| Q(surface_type=models.SURFACE_DEFAULT, event__surface_type__in=TRAIL_SURFACES)
			| Q(surface_type=models.SURFACE_DEFAULT, event__surface_type=models.SURFACE_DEFAULT, event__series__surface_type__in=TRAIL_SURFACES))
		context['main_distances_race_needed'].append(
			get_largest_races_best_results_dict(trail_races, u'Трейловые забеги и горный бег', 10, False))

	elif tab == TAB_REGIONS:
		regions = country.region_set.filter(active=True)
		events_by_region = []
		N_TOP_REGIONS = 100 if show_all else 10
		for region in regions:
			dicts = {year - 1: {}, year: {}}
			for cur_year, cur_year_events in ((year - 1, events_old), (year, events)):
				region_events = cur_year_events.filter(Q(city__region=region) | Q(city=None, series__city__region=region))
				dicts[cur_year]['n_events'] = region_events.count()
				race_aggr = models.Race.objects.filter(event__in=list(region_events)).aggregate(
					Sum('n_participants_finished'), Sum('n_participants_finished_men'))
				dicts[cur_year]['n_finishers'], dicts[cur_year]['n_finishers_men'] = \
					race_aggr['n_participants_finished__sum'], race_aggr['n_participants_finished_men__sum']
				if dicts[cur_year]['n_finishers'] is None:
					dicts[cur_year]['n_finishers'] = 0
				if dicts[cur_year]['n_finishers_men'] is None:
					dicts[cur_year]['n_finishers_men'] = 0

			events_by_region.append({
				'region': region,
				'population': int(region.population / 1000),
				'n_events': dicts[year]['n_events'],
				'n_events_old': dicts[year - 1]['n_events'],
				'n_finishers': dicts[year]['n_finishers'],
				'n_finishers_old': dicts[year - 1]['n_finishers'],
				'n_finishers_men': dicts[year]['n_finishers_men'],
				'fraction': int(dicts[year]['n_finishers_men'] * 100 / dicts[year]['n_finishers']) if dicts[year]['n_finishers'] else 0,

				'n_events_per_population': dicts[year]['n_events'] * 1000000 / region.population,
				'n_events_per_population_old': dicts[year - 1]['n_events'] * 1000000 / region.population,
				'n_finishers_per_population': dicts[year]['n_finishers'] * 1000 / region.population,
				'n_finishers_per_population_old': dicts[year - 1]['n_finishers'] * 1000 / region.population,

				'n_finishers_men_per_population': dicts[year]['n_finishers_men'] * 1000 / region.population,
				'n_finishers_women_per_population': (dicts[year]['n_finishers'] - dicts[year]['n_finishers_men']) * 1000 / region.population,
				})
		context['regions_by_events'] = sorted(events_by_region, key=lambda x:-x['n_events'])[:N_TOP_REGIONS]
		context['regions_by_finishers'] = sorted(events_by_region, key=lambda x:-x['n_finishers'])[:N_TOP_REGIONS]
		context['regions_by_events_per_population'] = sorted(events_by_region, key=lambda x:-x['n_events_per_population'])[:N_TOP_REGIONS]
		context['regions_by_finishers_per_population'] = sorted(events_by_region,
			key=lambda x:-x['n_finishers_per_population'])[:N_TOP_REGIONS]
		context['show_full_page_link'] = (not show_all) and (regions.count() > 10)

	elif tab == 3:
		context.update(get_result_quantiles_context(country, year, races))

	return context

def get_largest_races_best_results_dict(races, distance, n_largest_races, to_count_best_results):
	if to_count_best_results:
		races_for_results = races.filter(Q(distance_real=None) | Q(distance_real__length__gt=distance.length), is_for_handicapped=False)
		results = models.Result.objects.filter(race__in=races_for_results, source=models.RESULT_SOURCE_DEFAULT,
			status=models.STATUS_FINISHED).select_related('race__event__series__city__region', 
			'race__event__city__region', 'runner').order_by('-result' if (distance.distance_type == models.TYPE_MINUTES) else 'result')
		best_results_men = results.filter(gender=models.GENDER_MALE).exclude(pk=2033929)[:10]
		best_results_women = results.filter(gender=models.GENDER_FEMALE)[:10]
	else:
		best_results_men = []
		best_results_women = []

	largest_races = []
	for race in races.filter(n_participants_finished__gt=0).exclude(precise_name__endswith=u'этап эстафеты').select_related(
			'event__series__city__region', 'event__city__region', 'distance').order_by(
			'-n_participants_finished', 'event__start_date')[:n_largest_races]:

		same_races = race.event.race_set.filter(distance=race.distance).exclude(precise_name__endswith=u'этап эстафеты').aggregate(
			Sum('n_participants_finished'), Sum('n_participants_finished_men'))
		n_participants_finished = same_races['n_participants_finished__sum']
		n_participants_finished_men = same_races['n_participants_finished_men__sum']

		men_percent = min(100, int(n_participants_finished_men * 100 / n_participants_finished))
		largest_races.append({
			'race' : race,
			'n_participants_finished' : n_participants_finished,
			'n_participants_finished_men' : n_participants_finished_men,
			'men_percent': men_percent,
			'women_percent': 100 - men_percent,
			'n_participants_finished_old' : get_prev_year_race_n_participants(race, isinstance(distance, basestring)),
		})
	return {
			'distance': distance,
			'best_results_men': best_results_men,
			'best_results_women': best_results_women,
			'largest_races': largest_races,
			}


def russia_report_generator(request, tab=TAB_MAIN, show_all=False):
	year = REPORT_GENERATING_YEAR
	tab = results_util.int_safe(tab)
	context = get_context_for_new_report(year, tab, show_all)
	if tab == 3:
		return render(request, 'report_russia/{}/part{}.html'.format(year, tab), context=context)
	else:
		return render(request, 'report_russia/generator/part{}.html'.format(tab), context=context)

def generate_country_report(country_id, year=REPORT_GENERATING_YEAR, tabs=None):
	if country_id not in COUNTRIES_WITH_REPORTS:
		print('Reports are now available for Russia and Belarus only, not for {}.'.format(country_id))
		return
	country = models.Country.objects.get(pk=country_id)
	country_name = country.nameEn.lower()
	if year <= DEFAULT_REPORT_YEAR:
		print('You cannot re-generate report for year {}: it is finalized and published.'.format(year))
		return
	translation.activate(settings.LANGUAGE_CODE)

	if tabs is None:
		tabs = range(0, len(TAB_NAMES[year]))
	for tab in tabs: # range(0,1): #, len(TAB_NAMES[year])): # (1, ):
		file_template = 'report_russia/generator/part{}.html'.format(tab)
		file_target = os.path.join(settings.BASE_DIR, 'results/templates/report_{}/{}/part{}.html'.format(country_name, year, tab))
		with io.open(file_target, 'w', encoding="utf8") as output_file:
			output_file.write(render_to_string(file_template, get_context_for_new_report(country, year, tab, False)))
		print 'File is generated:', file_target
		if (tab in PAGES_WITH_SHOW_ALL_OPTION[year]) and (country.id == 'RU'):
			file_target = os.path.join(settings.BASE_DIR, 'results/templates/report_{}/{}/part{}_full.html'.format(country_name, year, tab))
			with io.open(file_target, 'w', encoding="utf8") as output_file:
				output_file.write(render_to_string(file_template, get_context_for_new_report(country, year, tab, True)))
			print 'File is generated:', file_target
	print 'Done!'

def fill_age_categories(to_save=False):
	n_found = 0
	results = []
	for category in list(models.Age_category.objects.filter(
			birthyear_min=None,
			birthyear_max=None,
			age_min=None,
			age_max=None,
			is_bad=False
	)):
		# res = re.search(ur'(\d{4})[ -]+(\d{4})', category.name) # (^\d)
		# if res:
		# 	year1 = int(res.group(1))
		# 	year2 = int(res.group(2))
		# 	if year1 > year2:
		# 		year1, year2 = year2, year1
		# 	print year1, '\t', year2, '\t', category.name
		# 	if to_save:
		# 		category.birthyear_min = year1
		# 		category.birthyear_max = year2
		# 		category.save()
		# 	n_found += 1
		# res = re.search(ur'(\d{4})[ -]+(\d{4})', category.name) # (^\d)

		# res = re.search(ur'(\d{4}).+и ст', category.name) # (^\d)
		# if res:
		# 	year2 = int(res.group(1))
		# 	print year2, '\t', category.name
		# 	if to_save:
		# 		category.birthyear_max = year2
		# 		category.save()
		# 	n_found += 1

		# res = re.search(ur'(\d{4})>', category.name) # (^\d)
		# if res:
		# 	year2 = int(res.group(1))
		# 	print year2, '\t', category.name
		# 	if to_save:
		# 		category.birthyear_max = year2
		# 		category.save()
		# 	n_found += 1

		res = re.search(ur'(\d{4})<', category.name) # (^\d)
		if res:
			year1 = int(res.group(1))
			print year1, '\t', category.name
			if to_save:
				category.birthyear_min = year1
				category.save()
			n_found += 1

		# res = re.search(ur'(\d{4}).+и мол', category.name) # (^\d)
		# if res:
		# 	year1 = int(res.group(1))
		# 	print year1, '\t', category.name
		# 	if to_save:
		# 		category.birthyear_min = year1
		# 		category.save()
		# 	n_found += 1

		# res = re.search(ur'(\d{4})[ -]+(\d{2})\D', category.name) # (^\d)
		# res = re.search(ur'(\d{4})[ -]+(\d{2})$', category.name) # (^\d)
		# if res:
		# 	year1 = int(res.group(1))
		# 	# if year1 < 2000:
		# 	year2 = int(res.group(2)) + 100 * (year1 // 100)
		# 	if year1 > year2:
		# 		year1, year2 = year2, year1
		# 	print year1, '\t', year2, '\t', category.name
		# 	if to_save:
		# 		category.birthyear_min = year1
		# 		category.birthyear_max = year2
		# 		category.save()
		# 	n_found += 1

		# res = re.search(ur'(\d{2})[ -]+(\d{2}).+г.[ ]*р.', category.name) # (^\d)
		# if res:
		# 	year1 = int(res.group(1)) + 1900
		# 	year2 = int(res.group(2)) + 1900
		# 	if year1 > year2:
		# 		year1, year2 = year2, year1
		# 	print year1, '\t', year2, '\t', category.name
		# 	if to_save:
		# 		category.birthyear_min = year1
		# 		category.birthyear_max = year2
		# 		category.save()
		# 	n_found += 1

	# 	res = re.search(ur'\D*(\d{2})[ -]+(\d{2})\D*', category.name) # (^\d)
	#	res = re.search(ur'от[ ]*(\d{2})[ ]*до[ ]*(\d{2})\D*', category.name) # (^\d)
	# 	if res:
	# 		age1 = int(res.group(1))
	# 		age2 = int(res.group(2))
	# 		# if (age1 < age2) and (age1 < 70):
	# 		results.append(u'{}\t{}\t{}'.format(age1, age2, category.name))
	# 		# print age1, '\t', age2, '\t', category.name
	# 		if to_save:
	# 			category.age_min = age1
	# 			category.age_max = age2
	# 			category.save()
	# 		n_found += 1
	# print '\n'.join(sorted(results))

	# 	res = re.search(ur'\D*(\d{2})[ -]+(\d{2})\D*', category.name) # (^\d)
	# 	if res:
	# 		age1 = int(res.group(1))
	# 		age2 = int(res.group(2))
	# 		if (age1 < age2) and (age2 in (74,75,79,80,80,84)):
	# 			results.append(u'{}\t{}\t{}'.format(age1, age2, category.name))
	# 			# print age1, '\t', age2, '\t', category.name
	# 			if to_save:
	# 				category.age_min = age1
	# 				category.age_max = age2
	# 				category.save()
	# 			n_found += 1
	# print '\n'.join(sorted(results))

	# 	res = re.search(ur'\D*(\d{2})[ -]+(\d{2})\D*', category.name) # (^\d)
	# 	if res:
	# 		age1 = int(res.group(1))
	# 		age2 = int(res.group(2))
	# 		if (age1 < age2) and (age2 not in (74,75,79,80,80,84)):
	# 			age1 += 1900
	# 			age2 += 1900
	# 			results.append(u'{}\t{}\t{}'.format(age1, age2, category.name))
	# 			# print age1, '\t', age2, '\t', category.name
	# 			if to_save:
	# 				category.birthyear_min = age1
	# 				category.birthyear_max = age2
	# 				category.save()
	# 			n_found += 1
	# print '\n'.join(sorted(results))

	# 	res = re.search(ur'\D*(\d{1,2})[ -]+(\d{1,2})\D*', category.name) # (^\d)
	# 	if res and (u'кл' not in category.name):
	# 		age1 = int(res.group(1))
	# 		age2 = int(res.group(2))
	# 		if age1 < age2:
	# 			results.append(u'{}\t{}\t{}'.format(age1, age2, category.name))
	# 			# print age1, '\t', age2, '\t', category.name
	# 			if to_save:
	# 				category.age_min = age1
	# 				category.age_max = age2
	# 				category.save()
	# 			n_found += 1
	# print '\n'.join(sorted(results))

	# 	res = re.search(ur'\D*(\d{2})[ -]+(\d{2})\D*', category.name) # (^\d)
	# 	if res:
	# 		age1 = int(res.group(1))
	# 		age2 = int(res.group(2))
	# 		if age1 > age2:
	# 			age1 += 1900
	# 			age2 += 1900
	# 			age1, age2 = age2, age1
	# 			results.append(u'{}\t{}\t{}'.format(age1, age2, category.name))
	# 			# print age1, '\t', age2, '\t', category.name
	# 			if to_save:
	# 				category.age_min = age1
	# 				category.age_max = age2
	# 				category.save()
	# 			n_found += 1
	# print '\n'.join(sorted(results))

		# res = re.search(ur'(\d{2}).*и ст', category.name) # (^\d)
		# if res:
		# 	age1 = int(res.group(1))
		# 	print age1, '\t', category.name
		# 	if to_save:
		# 		category.age_min = age1
		# 		category.save()
		# 	n_found += 1

		# res = re.search(ur'(\d{2}).*и мл', category.name)
		# res = re.search(ur'до[ ]*(\d{2}).*лет', category.name)
		# res = re.search(ur'до[ ]*(\d{2})', category.name)
		# if res:
		# 	age2 = int(res.group(1))
		# 	print age2, '\t', category.name
		# 	if to_save:
		# 		category.age_max = age2
		# 		category.save()
		# 	n_found += 1

		# res = re.search(ur'>(\d{2})', category.name) # (^\d)
		# if res:
		# 	age1 = int(res.group(1))
		# 	print age1, '\t', category.name
		# 	if to_save:
		# 		category.age_min = age1
		# 		category.save()
		# 	n_found += 1

		# res = re.search(ur'(\d{2})[+]', category.name) # (^\d)
		# if res:
		# 	age1 = int(res.group(1))
		# 	print age1, '\t', category.name
		# 	if to_save:
		# 		category.age_min = age1
		# 		category.save()
		# 	n_found += 1
	print 'Done! Categories found:', n_found

def print_birthdays_ages(year, results):
	AGE_MIN = 0
	AGE_MAX = 110
	BIRTHYEAR_MIN = year - AGE_MAX
	BIRTHYEAR_MAX = year
	MAX_DIFF = 10
	GROUP_STEP = 5
	LAST_GROUP = 80
	birthyears = [ [0.]*3 for _ in range(BIRTHYEAR_MAX + 1)] # [from result birthyear; from runner birthyear; from group]
	ages = [ [0.]*2 for _ in range(AGE_MAX + 1)] # [from result age; from group]

	results_with_birthday = results.exclude(birthday=None)
	n_results = 0
	for birthyear in range(BIRTHYEAR_MIN, BIRTHYEAR_MAX + 1):
		n_found = results.filter(birthday__year=birthyear).count()
		# print n_found
		n_results += n_found
		birthyears[birthyear][0] += n_found
	# print u'Известен год рождения результата:', n_results
	
	results_wo_bd = results.filter(birthday=None)
	n_results = 0
	for birthyear in range(BIRTHYEAR_MIN, BIRTHYEAR_MAX + 1):
		n_found = results_wo_bd.filter(runner__birthday__year=birthyear).count()
		# print birthyear, n_found
		n_results += n_found
		birthyears[birthyear][1] += n_found
	# print u'Известен только год рождения бегуна:', n_results
	
	results_wo_bd_wo_runner = results.filter(
		Q(runner=None) | Q(runner__birthday=None),
		birthday=None)
	n_results = 0
	for age in range(AGE_MIN, AGE_MAX + 1):
		n_found = results_wo_bd_wo_runner.filter(age=age).count()
		# print age, n_found
		n_results += n_found
		ages[age][0] += n_found
	# print u'Известен возраст результата:', n_results

	results_wo_age = results.filter(
		Q(runner=None) | Q(runner__birthday=None),
		birthday=None, age=None)
	categories = set(results_wo_age.values_list('category', flat=True)) - set([''])
	# print len(groups)
	n_results = 0
	n_results_used_age = 0
	n_results_used_birthday = 0
	for category_name in categories:
		category = models.Age_category.objects.filter(name=category_name).first()
		if category is None:
			print 'Missing category:', category_name
			continue
		if category.is_bad:
			continue
		n_found = results_wo_age.filter(category=category_name).count()
		if n_found == 0:
			continue
		n_results += n_found
		if category.birthyear_min or category.birthyear_max:
			year_from = max(category.birthyear_min, BIRTHYEAR_MIN) if category.birthyear_min else BIRTHYEAR_MIN
			year_to = min(category.birthyear_max, BIRTHYEAR_MAX) if category.birthyear_max else BIRTHYEAR_MAX
			diff = year_to - year_from
			if 0 < diff <= MAX_DIFF:
				n_results_used_birthday += n_found
				# print diff, category_name
				for birthyear in range(year_from, year_to + 1):
					birthyears[birthyear][2] += n_found / (diff + 1)
		elif category.age_min or category.age_max:
			age_from = max(category.age_min, AGE_MIN) if category.age_min else AGE_MIN
			age_to = min(category.age_max, AGE_MAX) if category.age_max else AGE_MAX
			diff = age_to - age_from
			if 0 < diff <= MAX_DIFF:
				n_results_used_age += n_found
				# print diff, category_name
				for age in range(age_from, age_to + 1):
					ages[age][1] += n_found / (diff + 1)
	# print u'Известна только группа результата:', n_results
	# print u'Определили примерный год рождения по группе:', n_results_used_birthday
	# print u'Определили примерный возраст по группе:', n_results_used_age
	# for age in range(AGE_MIN, AGE_MAX + 1):
	# 	print unicode(age) + '\t' + '\t'.join(unicode(x) for x in ages[age])
	# for birthyear in range(BIRTHYEAR_MIN, BIRTHYEAR_MAX + 1):
	# 	print unicode(birthyear) + '\t' + '\t'.join(unicode(x) for x in birthyears[birthyear])
	people = [0.] * (AGE_MAX + 1)
	for age in range(AGE_MAX + 1):
		people[age] = sum(ages[age]) + sum(birthyears[year - age])
	for group in range(0, LAST_GROUP, GROUP_STEP):
		# print u'{}-{}\t{}'.format(group, group + GROUP_STEP - 1, int(sum(people[group:group + GROUP_STEP])))
		print int(sum(people[group:group + GROUP_STEP]))
	# print u'{}+\t{}'.format(LAST_GROUP, int(sum(people[LAST_GROUP:])))
	print int(sum(people[LAST_GROUP:]))

def get_age_stat():
	year = REPORT_GENERATING_YEAR
	russian_races = models.Race.get_russian_races(year)

	for distance_id in results_util.DISTANCES_TOP_FOUR:
		distance = models.Distance.objects.get(pk=distance_id)
		russian_results = models.Result.objects.filter(
			race__in=russian_races.filter(distance=distance),
			source=models.RESULT_SOURCE_DEFAULT,
			# status__in=(models.STATUS_FINISHED, models.STATUS_DNF, models.STATUS_DSQ),
			status=models.STATUS_FINISHED,
		).exclude(gender=models.GENDER_UNKNOWN)
		print u'{}. Всего финишировавших, у которых известен пол: {}'.format(distance.name, russian_results.count())
		print_birthdays_ages(year, russian_results)

		russian_results_male = russian_results.filter(gender=models.GENDER_MALE)
		print u'Мужчины:', russian_results_male.count()
		print_birthdays_ages(year, russian_results_male)
		
		russian_results_female = russian_results.filter(gender=models.GENDER_FEMALE)
		print u'Женщины:', russian_results_female.count()
		print_birthdays_ages(year, russian_results_female)
		# print u'Всего официальных результатов у стартовавших на забегах в России, у которых известен пол:', russian_results.count()
		# for gender, name in models.GENDER_CHOICES[1:]:
		# 	print name, russian_results.filter(gender=gender).count()

		# print_birthdays_ages(year, russian_results.filter(gender=models.GENDER_FEMALE))

def get_result_stat(year=REPORT_GENERATING_YEAR):
	russian_events = models.Event.get_russian_events(year).filter(
		series__surface_type__in=(models.SURFACE_DEFAULT, models.SURFACE_HARD),
		surface_type__in=(models.SURFACE_DEFAULT, models.SURFACE_HARD),
	).values_list('id', flat=True)
	russian_races = models.Race.objects.filter(
		event_id__in=russian_events,
		surface_type__in=(models.SURFACE_DEFAULT, models.SURFACE_HARD),
		distance_real=None,
		n_participants_finished__gte=20,
	)
	steps = [
		(results_util.DIST_MARATHON_ID, 20 * 60 * 100, (0, 20, 19)), # in centiseconds
		(results_util.DIST_HALFMARATHON_ID, 10 * 60 * 100, (0, 20, 19)),
		(results_util.DIST_10KM_ID, 5 * 60 * 100, (0, 20, 19)),
		(results_util.DIST_5KM_ID, 150 * 100, (0, 21, 20)),
	]
	with io.open(os.path.join(settings.BASE_DIR, '../chernov/rus_results_{}.txt'.format(year)), 'w', encoding='utf8') as f:
		for distance_id, step, n_baskets in steps:
			distance = models.Distance.objects.get(pk=distance_id)
			for gender in (models.GENDER_MALE, models.GENDER_FEMALE):
				results = models.Result.objects.filter(
					race_id__in=russian_races.filter(distance=distance).values_list('id', flat=True),
					source=models.RESULT_SOURCE_DEFAULT,
					status=models.STATUS_FINISHED,
					gender=gender,
				)
				results_count = results.count()
				# print u'{}. Пол: {}. Всего финишировавших: {}'.format(distance.name, models.GENDER_CHOICES[gender][1], results_count)
				f.write(u'{}. Пол: {}. Всего финишировавших: {}\n'.format(distance.name, models.GENDER_CHOICES[gender][1], results_count))
				N_BASKETS = n_baskets[gender]
				baskets = [0] * N_BASKETS
				for result in results.values_list('result', flat=True):
					basket = min(N_BASKETS - 1, result // step)
					baskets[basket] += 1
				printed_count = 0.
				for basket in range(N_BASKETS - 1, -1, -1):
					if baskets[basket] > 0:
						percent = baskets[basket] / results_count
						printed_count += percent * 100
						percent_str = '({0:.1f}%)'.format(percent * 100).replace('.', ',').rjust(7)
						symbols_to_cut = 3 if (distance_id == results_util.DIST_5KM_ID) else 1
						if basket == N_BASKETS - 1:
							limits = '{} +        '.format(models.centisecs2time(step * basket)[symbols_to_cut:])
						else:
							limits = '{} – {}'.format(models.centisecs2time(step * basket)[symbols_to_cut:],
								models.centisecs2time(step * (basket + 1) - 100)[symbols_to_cut:])
						# print '{} {}\t{}'.format(limits, percent, baskets[basket])
						# print '{} {}\t{}'.format(limits, percent_str, unicode(percent).replace('.', ','))
						# f.write('{} {}\t{}\n'.format(limits, percent_str, unicode(percent).replace('.', ',')))
						f.write('{}\t{}\t{}\n'.format(limits, unicode(percent).replace('.', ','), baskets[basket]))
				print 'Total percents:', printed_count
	print 'Done!'

# Given a list of tuples(result, runner_id), take just the best (smallest) result for each runner_id, and keep all results with runner_id=None
def get_best_results_by_runner(results):
	results_wo_runner = []
	runners_best = {}

	for result, runner_id in results:
		if runner_id:
			if runner_id in runners_best:
				if result < runners_best[runner_id]:
					runners_best[runner_id] = result
			else:
				runners_best[runner_id] = result
		else:
			results_wo_runner.append(result)
	return sorted(results_wo_runner + runners_best.values())

def get_result_quantiles_context(country, year, cur_year_races):
	normal_surfaces = (models.SURFACE_DEFAULT, models.SURFACE_HARD, models.SURFACE_ROAD, models.SURFACE_STADIUM, models.SURFACE_INDOOR)
	races = cur_year_races.filter(
		event__series__surface_type__in=normal_surfaces,
		event__surface_type__in=normal_surfaces,
		surface_type__in=normal_surfaces,
		distance_real=None,
		n_participants_finished__gte=MIN_N_PARTICIPANTS_FOR_QUANTILES,
	)
	quantiles = (1, 2, 3, 5, 10, 25, 50, 75)

	context = {}

	context['distances'] = OrderedDict()
	for distance_id in results_util.DISTANCES_TOP_FOUR:
		distance = models.Distance.objects.get(pk=distance_id)
		races_ids = races.filter(distance=distance).values_list('id', flat=True)
		data = {}
		for gender in (models.GENDER_MALE, models.GENDER_FEMALE):
			results = models.Result.objects.filter(
				race_id__in=races_ids,
				source=models.RESULT_SOURCE_DEFAULT,
				status=models.STATUS_FINISHED,
				gender=gender,
			).values_list('result', 'runner_id')

			best_results = get_best_results_by_runner(results)
			results_count = len(best_results)

			gender_data = []
			for quantile in quantiles:
				result_number = int(round(results_count * quantile / 100))
				# print(u'distance: {}, quantile: {}, result_number: {}'.format(distance, quantile, result_number))
				gender_data.append(models.centisecs2time(best_results[max(result_number - 1, 0)], round_hundredths=True))
			data[gender] = gender_data
		context['distances'][distance] = data
	context['quantiles'] = quantiles
	return context

def get_regions_stat():
	year = REPORT_GENERATING_YEAR
	russian_regions = models.Region.objects.filter(country_id='RU', active=True)
	with io.open(os.path.join(settings.BASE_DIR, '../chernov/rus_regions_{}.txt'.format(year)), 'w', encoding='utf8') as f:
		f.write(u'Region id\tName\tFull name\tPopulation\tNumber of events\tNumber of finishers\tNumber of male finishers\n')
		for region in russian_regions:
			region_events = models.Event.get_russian_events(year).filter(Q(city__region=region) | Q(city=None, series__city__region=region))
			n_events = region_events.count()
			race_aggr = models.Race.objects.filter(event__in=list(region_events)).aggregate(
				Sum('n_participants_finished'), Sum('n_participants_finished_men'))
			n_finishers, n_finishers_men = race_aggr['n_participants_finished__sum'], race_aggr['n_participants_finished_men__sum']
			if n_finishers is None:
				n_finishers = 0
			if n_finishers_men is None:
				n_finishers_men = 0
			f.write(u'{}\t{}\t{}\t{}\t{}\t{}\t{}\n'.format(
				region.id, region.name, region.name_full, region.population, n_events, n_finishers, n_finishers_men))
	print "Done!"

def res2str(result):
	res = []
	if result['midname']:
		res.append(result['midname'])
	if result['birthday_known']:
		res.append(unicode(result['birthday']))
	elif result['birthday']:
		res.append(unicode(result['birthday'].year))
	if result['age']:
		res.append(u'{} years'.format(result['age']))
	return u','.join(res)

def get_min_n_distinct_people(year, results, debug=False):
	# Results is set of dicts: each dict has fields midname, birthday, birthday_known, age
	n_results = 0
	if debug:
		print 'All names:'
		for result in results:
			print res2str(result)
	while True: # Results with midname and birthday_known
		result_to_work = None
		for result in results:
			if result['midname'] and result['birthday_known']:
				result_to_work = result
				break
		if result_to_work is None:
			break
		if debug:
			print 'Deleting', res2str(result_to_work), 'reason: 1'
		n_results += 1
		results = [r for r in results if not (
			(r['midname'] in ('', result_to_work['midname']))
			and ( 
					(r['birthday'] is None)
					or ( (r['birthday'].year == result_to_work['birthday'].year) and not r['birthday_known'])
					or (r['birthday_known'] and (r['birthday'] == result_to_work['birthday']))
				)
			and (
					r['birthday']
					or (r['age'] is None)
					or (abs(r['age'] + result_to_work['birthday'].year - year) < 2)
				)
		)]
	while True: # Results with midname='' and birthday_known
		result_to_work = None
		for result in results:
			if result['birthday_known']:
				result_to_work = result
				break
		if result_to_work is None:
			break
		if debug:
			print 'Deleting', res2str(result_to_work), 'reason: 2'
		n_results += 1
		results = [r for r in results if not (
				( 
					(r['birthday'] is None)
					or ( (r['birthday'].year == result_to_work['birthday'].year) and not r['birthday_known'])
					or (r['birthday_known'] and (r['birthday'] == result_to_work['birthday']))
				)
			and (
					r['birthday']
					or (r['age'] is None)
					or (abs(r['age'] + result_to_work['birthday'].year - year) < 2)
				)
		)]
	while True: # Results with midname and birth year
		result_to_work = None
		for result in results:
			if result['midname'] and result['birthday']:
				result_to_work = result
				break
		if result_to_work is None:
			break
		if debug:
			print 'Deleting', res2str(result_to_work), 'reason: 3'
		n_results += 1
		results = [r for r in results if not (
			(r['midname'] in ('', result_to_work['midname']))
			and ( 
					(r['birthday'] is None)
					or (r['birthday'].year == result_to_work['birthday'].year)
				)
			and (
					r['birthday']
					or (r['age'] is None)
					or (abs(r['age'] + result_to_work['birthday'].year - year) < 2)
				)
		)]
	while True: # Results with midname='' and birth year
		result_to_work = None
		for result in results:
			if result['birthday']:
				result_to_work = result
				break
		if result_to_work is None:
			break
		if debug:
			print 'Deleting', res2str(result_to_work), 'reason: 4'
		n_results += 1
		results = [r for r in results if not (
				( 
					(r['birthday'] is None)
					or (r['birthday'].year == result_to_work['birthday'].year)
				)
			and (
					r['birthday']
					or (r['age'] is None)
					or (abs(r['age'] + result_to_work['birthday'].year - year) < 2)
				)
		)]
	while True: # Results with midname and age
		result_to_work = None
		for result in results:
			if result['midname'] and result['age']:
				result_to_work = result
				break
		if result_to_work is None:
			break
		if debug:
			print 'Deleting', res2str(result_to_work), 'reason: 5'
		n_results += 1
		results = [r for r in results if not (
			(r['midname'] in ('', result_to_work['midname']))
			and (
					(r['age'] is None)
					or (abs(r['age'] - result['age']) < 2)
				)
		)]
	while True: # Results with midname='' and age
		result_to_work = None
		for result in results:
			if result['age']:
				result_to_work = result
				break
		if result_to_work is None:
			break
		if debug:
			print 'Deleting', res2str(result_to_work), 'reason: 6'
		n_results += 1
		results = [r for r in results if not (
				(
					(r['age'] is None)
					or (abs(r['age'] - result['age']) < 2)
				)
		)]
	while True: # Results with midname
		result_to_work = None
		for result in results:
			if result['midname']:
				result_to_work = result
				break
		if result_to_work is None:
			break
		if debug:
			print 'Deleting', res2str(result_to_work), 'reason: 7'
		n_results += 1
		results = [r for r in results if not (
			(r['midname'] in ('', result_to_work['midname']))
		)]
	if results:
		result_to_work = results[0]
		if debug:
			print 'Deleting', res2str(result_to_work), 'reason: 8'
		n_results += 1
	return n_results

def check_distinct_results():
	year = REPORT_GENERATING_YEAR
	lname = u'Гебель'
	fname = u'Марина'
	russian_races = models.Race.get_russian_races(year)
	rus_finished_results = models.Result.objects.filter(race__in=russian_races, status=models.STATUS_FINISHED)
	free_results = rus_finished_results.filter(runner=None)
	print 'Answer:', get_min_n_distinct_people(year, list(free_results.filter(lname=lname, fname=fname).values(
					'midname', 'birthday', 'birthday_known', 'age')), debug=True)

def count_min_n_participants(country_id, year=REPORT_GENERATING_YEAR):
	country = models.Country.objects.get(pk=country_id)
	races = models.Race.get_races_by_countries(year, [country.id])
	rus_finished_results = models.Result.objects.filter(race__in=races, status=models.STATUS_FINISHED)
	n_dist_runners = len(set(rus_finished_results.exclude(runner=None).values_list('runner_id', flat=True)))
	print 'Different runners in {}:'.format(year), n_dist_runners
	free_results = rus_finished_results.filter(runner=None)
	names = sorted(set(free_results.exclude(lname='').exclude(fname='').values_list('lname', 'fname')))
	first_letters = sorted(set([name[0][0].lower() for name in names]))
	print 'Different names:', len(names)
	total = 0
	for letter in first_letters:
		# if letter < u'р':
		# 	continue
		n_runners = 0
		names_from_letter = [name for name in names if (name[0][0].lower() == letter)]
		runners_dict = {}
		for result in free_results.filter(lname__istartswith=letter).values('lname', 'fname', 'midname', 'birthday', 'birthday_known', 'age'):
			lname = result['lname'].lower()
			fname = result['fname'].lower()
			if (lname, fname) not in runners_dict:
				runners_dict[(lname, fname)] = []
			runners_dict[(lname, fname)].append({
				'midname': result['midname'],
				'birthday': result['birthday'],
				'birthday_known': result['birthday_known'],
				'age': result['age'],
			})
		print 'Names starting from', letter, ':', len(names_from_letter), ', dict size:', len(runners_dict)
		counter = 0
		for lfname, lfresults in runners_dict.items():
			counter += 1
			# if ((counter % 50) == 0) or (counter > 500):
			# if (counter % 500) == 0:
				# print counter, n_runners, lfname[0], lfname[1]
			n_runners += get_min_n_distinct_people(year, lfresults)
		print 'Different people from unclaimed results on letter', letter, ':', n_runners
		total += n_runners
	set_stat_value('n_distinct_runners_{}_{}'.format(country.id, year), n_dist_runners + total, datetime.date.today())
	print('Total: {}'.format(n_dist_runners + total))

def get_n_participants(): # For saint-petersburg.ru
	for year in range(2014, 2018):
		res = models.Race.get_russian_races(year).aggregate(Sum('n_participants'), Sum('n_participants_finished'), Sum('n_participants_finished_men'))
		print(year, res['n_participants__sum'], res['n_participants_finished__sum'], res['n_participants_finished_men__sum'])

def get_n_finishers_wo_parkrun():
	for year in range(2016, 2019):
		russian_races = models.Race.get_russian_races(year)
		n_finishers_total = russian_races.aggregate(Sum('n_participants_finished'), Sum('n_participants_finished_men'))
		n_finishers_parkrun = russian_races.filter(
			event__series__url_site__startswith=results_util.RUSSIAN_PARKRUN_SITE).aggregate(
			Sum('n_participants_finished'), Sum('n_participants_finished_men'))
		print(
			year,
			n_finishers_total['n_participants_finished__sum'],
			n_finishers_total['n_participants_finished_men__sum'],
			n_finishers_total['n_participants_finished__sum'] - n_finishers_total['n_participants_finished_men__sum'],
			n_finishers_parkrun['n_participants_finished__sum'],
			n_finishers_parkrun['n_participants_finished_men__sum'],
			n_finishers_parkrun['n_participants_finished__sum'] - n_finishers_parkrun['n_participants_finished_men__sum'],
		)
