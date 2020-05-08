# -*- coding: utf-8 -*-
from __future__ import division
from django.template.loader import render_to_string
from django.core.urlresolvers import reverse
from django.db.models.query import Prefetch
from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum, Min
from django.utils import timezone
from django.conf import settings
from collections import OrderedDict, Counter
import datetime
import logging
import re
import io
import os

from results import models
from results import results_util
from .views_common import generate_html, is_good_symbol
from dbchecks import dbchecks

def set_stat_value(name, value, today): # Saving this way for last_update to update
	stat, _ = models.Statistics.objects.get_or_create(name=name, date_added=today)
	stat.value = value
	stat.save()
	print "{}: {} = {}".format(datetime.datetime.now(), name, value)

def get_stat_value(name):
	stat = models.Statistics.objects.filter(name=name).order_by('-date_added').first()
	return stat.value if stat else None

def update_events_count():
	today = datetime.date.today()
	good_events = models.Event.objects.filter(invisible=False, cancelled=False).exclude(series__id=results_util.OLD_PARKRUN_SERIES_ID)
	set_stat_value(
		'n_events_in_past',
		good_events.filter(start_date__lte=today).count(),
		today)
	set_stat_value(
		'n_events_in_future',
		good_events.filter(start_date__gte=today).count(),
		today)
	set_stat_value(
		'n_events_this_week',
		good_events.filter(start_date__gte=today, start_date__lte=today + datetime.timedelta(days=7)).count(),
		today)
	# set_stat_value(
	# 	'n_events_this_month',
	# 	good_events.filter(start_date__gte=today, start_date__lte=today + datetime.timedelta(days=31)).count(),
	# 	today)
	cis_countries = ('RU', 'BY', 'UA')
	cis_events = good_events.filter(
		Q(city__region__country_id__in=cis_countries)
		| (Q(city=None) & Q(series__city__region__country_id__in=cis_countries))
		| (Q(city=None) & Q(series__city=None) & Q(series__country_id__in=cis_countries))
	)
	set_stat_value(
		'n_events_this_month_RU_UA_BY',
		cis_events.filter(start_date__gte=today, start_date__lte=today + datetime.timedelta(days=models.DAYS_IN_DEFAULT_CALENDAR)).count(), today)

def update_results_count():
	today = datetime.date.today()
	set_stat_value('n_results', models.Result.objects.count(), today)
	set_stat_value('n_results_with_runner', models.Result.objects.exclude(runner=None).count(), today)
	set_stat_value('n_results_from_klb', models.Klb_result.objects.exclude(result=None).count(), today)
	set_stat_value('n_results_from_parkrun', models.Result.objects.exclude(parkrun_id=None).count(), today)
	set_stat_value('n_results_with_user', models.Result.objects.exclude(user=None).count(), today)
	# set_stat_value('n_results_from_ak', models.Result.objects.filter(loaded_from__startswith='AK55').count(), today)

def update_race_size_stat(debug=False):
	bad_races = []
	n_races_added = 0
	thousand_max = models.Race.objects.order_by('-pk').values_list('pk', flat=True)[0] // 1000
	for thousand in range(0, thousand_max + 1):
		if debug:
			print thousand
		for race in models.Race.objects.filter(event__start_date__lte=datetime.date.today(),
				pk__range=(1000*thousand, 1000*(thousand+1) - 1)).select_related(
				'event', 'race_size', 'distance').annotate(n_results=Count('result')).order_by('id'):
			if hasattr(race, 'race_size'):
				race_size = race.race_size
				if race.n_results < race_size.n_results:
					bad_races.append((race, race_size.last_update, race_size.n_results, race.n_results))
				race_size.n_results = race.n_results
				race_size.save()
			else:
				models.Race_size.objects.create(race=race, n_results=race.n_results)
				n_races_added += 1
	if debug:
		for race, last_update, old_n_results, n_results in bad_races:
			print u'{}, {} (id {}): {} было {} результатов, сейчас {} результатов'.format(
				race.name_with_event(), race.event.date(), race.id, last_update, old_n_results, n_results)
		print u'Учтено новых дистанций:', n_races_added
	else:
		res = ''
		if bad_races:
			res += u'\n\nДистанции, на которых уменьшилось число результатов ({}):'.format(len(bad_races))
			for race, last_update, old_n_results, n_results in bad_races:
				res += u'\n{}, {}, {}{}: {} было {} результатов, сейчас {} результатов'.format(
					race.name_with_event(), race.event.date(), models.SITE_URL, race.get_absolute_url(), last_update, old_n_results, n_results)
		return res

def update_distance_stat(distance, runner=None, user=None, club_member=None, year=None):
	if runner:
		result_set = runner.result_set
		person = runner
	elif user:
		result_set = user.result_set
		person = user.user_profile if hasattr(user, 'user_profile') else models.User_profile(user=user)
	else:
		result_set = club_member.runner.result_set
		person = club_member.runner

	to_calc_age_coef_data = club_member and (distance.distance_type != models.TYPE_MINUTES) \
		and (person.gender != models.GENDER_UNKNOWN) and person.birthday

	result_set = result_set.filter(race__distance=distance, do_not_count_in_stat=False, status__in=(models.STATUS_FINISHED, models.STATUS_COMPLETED))
	if year:
		result_set = result_set.filter(race__event__start_date__year=year)
	if club_member:
		if club_member.date_registered:
			result_set = result_set.filter(race__event__start_date__gte=club_member.date_registered)
		if club_member.date_removed:
			result_set = result_set.filter(race__event__start_date__lte=club_member.date_removed)
	results = result_set.select_related('race__event', 'race__distance', 'race__distance_real').order_by(
		'-result' if (distance.distance_type == models.TYPE_MINUTES) else 'result')
	if results.exists():
		stat = models.User_stat(runner=runner, user=user, club_member=club_member, distance=distance, year=year)
		stat.n_starts = results.count()
		results_sum = 0
		# value_best = results[0]
		# race_best = models.Race.objects.get(pk=value_best['race'])
		# Let's find best race with real distance not less than official distance
		results_with_time = results.filter(status=models.STATUS_FINISHED, result__gt=0)
		if results_with_time.exists(): # Or maybe we have only result with status=models.STATUS_COMPLETED
			value_best = None
			results_sum = 0

			value_best_age_coef = None
			time_age_coef_best = None
			results_age_coef_sum = 0

			for result in results_with_time.select_related('race__distance', 'race__distance_real', 'race__event'):
				results_sum += result.result
				if (value_best is None) and ( (result.race.distance_real is None) or (result.race.distance_real.length > result.race.distance.length) ):
					value_best = result

				if to_calc_age_coef_data:
					result_year = result.race.event.start_date.year
					result_age_coef = result.result * models.Coefficient.get_klb_coefficient(result_year, person.gender,
						result_year - person.birthday.year, distance)
					results_age_coef_sum += result_age_coef
					if (
							( (value_best_age_coef is None) or (time_age_coef_best > result_age_coef) )
						and ( (result.race.distance_real is None) or (result.race.distance_real.length > result.race.distance.length) )
						):
						value_best_age_coef = result
						time_age_coef_best = result_age_coef

			if value_best is None:
				value_best = results_with_time[0]
			if to_calc_age_coef_data and (value_best_age_coef is None):
				value_best_age_coef = results_with_time[0]
				time_age_coef_best = results_with_time[0].result # Not exact but let it be...

			race_best = value_best.race
			stat.best_result = value_best
			stat.value_best = value_best.result
			stat.pace_best = race_best.get_pace(stat.value_best)

			stat.value_mean = int(round(results_sum / results_with_time.count()))
			stat.pace_mean = distance.get_pace(stat.value_mean)
			if (distance.distance_type != models.TYPE_MINUTES) and (stat.value_mean > 6000):
				stat.value_mean = int(round(stat.value_mean, -2))

			if to_calc_age_coef_data:
				race_age_coef_best = value_best_age_coef.race
				stat.best_result_age_coef = value_best_age_coef
				stat.value_best_age_coef = time_age_coef_best
				stat.value_mean_age_coef = int(round(results_age_coef_sum / results_with_time.count()))

		# if club_member and club_member.id == 1079:
		# 	models.write_log('Saving stat for club member {}, year {}, distance {}'.format(
		# 		club_member.id if club_member else '', year, distance.id))
		# try:
		# 	stat.save()
		# except Exception as e:
		# 	models.write_log('Problem when saving stat for club member {}, year {}, distance {}'.format(
		# 		club_member.id if club_member else '', year, distance.id))
		stat.save()
		
		if distance.distance_type == models.TYPE_MINUTES:
			total_length = results_sum
			total_time = stat.n_starts * distance.length * 6000
		elif distance.distance_type == models.TYPE_METERS:
			# total_length = stat.n_starts * distance.length
			total_length = sum((result.race.distance_real if result.race.distance_real else result.race.distance).length
				for result in results.select_related('race__distance', 'race__distance_real'))
			total_time = results_sum
		else:
			total_length = 0
			total_time = results_sum
		return len(results), total_length, total_time
	return 0, 0, 0

def update_club_member_stat(club_member, distance, year):
	if year:
		years = [year]
	else: # We have to update all years when member was in club
		min_year = models.FIRST_YEAR_FOR_STAT_UPDATE
		if club_member.date_registered and club_member.date_registered.year > min_year:
			min_year = club_member.date_registered.year
		max_year = datetime.date.today().year
		if club_member.date_removed and club_member.date_removed.year < max_year:
			max_year = club_member.date_removed.year
		years = [None] + range(min_year, max_year + 1)
	for member_year in years:
		# if club_member.id == 1079: 
		# 	models.write_log('Updating stat for club member {}, year {}, distance {}'.format(
		# 		club_member.id, year, distance.id))
		update_distance_stat(distance, club_member=club_member, year=member_year)

DISTANCE_LIMIT = 5
# Exactly one of runner, user, club_member must be not None
def update_runner_stat(runner=None, user=None, club_member=None, year=None, update_club_members=True):
	person = None
	person_for_stat = None
	club_members = []
	if runner:
		result_set = runner.result_set
		person = runner
		person_for_stat = runner
		club_members = models.Club_member.objects.filter(runner=runner)
		runner.n_parkrun_results = runner.result_set.exclude(parkrun_id=None).count()
	elif user:
		result_set = user.result_set
		person = user
		if hasattr(user, 'user_profile'):
			person_for_stat = user.user_profile
		if hasattr(user, 'runner'):
			club_members = models.Club_member.objects.filter(runner=user.runner)
	elif club_member:
		result_set = club_member.runner.result_set
		person = club_member
		club_members = [club_member]

	if person is None:
		return

	n_starts = 0
	total_length = 0
	total_time = 0
	n_starts_cur_year = 0
	total_length_cur_year = 0
	total_time_cur_year = 0
	cur_year = models.CUR_RUNNERS_ORDERING_YEAR

	if runner or user:
		person.user_stat_set.all().delete()
	if update_club_members:
		for m in club_members:
			if year:
				m.user_stat_set.filter(year=year).delete()
			else:
				# models.write_log('Removing all stat for club member {}'.format(m.id))
				m.user_stat_set.all().delete()

	distance_ids = result_set.filter(
			status__in=(models.STATUS_FINISHED, models.STATUS_COMPLETED),
			race__distance__distance_type__in=(models.TYPE_METERS, models.TYPE_MINUTES),
		).order_by(
		'race__distance_id').values_list('race__distance_id', flat=True).distinct()
	# if club_members and club_members[0].id == 1079:
	# 	models.write_log('Distances: {}'.format(', '.join(unicode(x) for x in distance_ids)))
	for distance_id in distance_ids:
		distance = models.Distance.objects.get(pk=distance_id)
		if person_for_stat:
			res = update_distance_stat(distance, runner=runner, user=user, club_member=club_member)
			n_starts += res[0]
			total_length += res[1]
			total_time += res[2]
			if runner:
				res_cur_year = update_distance_stat(distance, runner=runner, user=user, club_member=club_member, year=cur_year)
				n_starts_cur_year += res_cur_year[0]
				total_length_cur_year += res_cur_year[1]
				total_time_cur_year += res_cur_year[2]
		if update_club_members and (distance_id in results_util.DISTANCES_FOR_CLUB_STATISTICS):
			for m in club_members:
				update_club_member_stat(m, distance, year)

	if person_for_stat:
		person_for_stat.n_starts = n_starts
		person_for_stat.total_length = total_length
		person_for_stat.total_time = total_time
		if runner:
			setattr(person_for_stat, 'n_starts_{}'.format(cur_year), n_starts_cur_year)
			setattr(person_for_stat, 'total_length_{}'.format(cur_year), total_length_cur_year)
			setattr(person_for_stat, 'total_time_{}'.format(cur_year), total_time_cur_year)
		if distance_ids.count() > DISTANCE_LIMIT:
			for user_stat in person.user_stat_set.filter(year=None).order_by('-n_starts', '-distance__length')[:DISTANCE_LIMIT]:
				user_stat.is_popular = True
				user_stat.save()
			person_for_stat.has_many_distances = True
		else:
			person_for_stat.has_many_distances = False
		person_for_stat.save()

def update_race_runners_stat(race):
	n_runners = 0
	for result in race.result_set.filter(runner__isnull=False).select_related('runner'):
		update_runner_stat(runner=result.runner)
		if result.user:
			update_runner_stat(user=result.user, update_club_members=False)
		n_runners += 1
	return n_runners

def update_runners_stat(id_from=0, debug=0):
	runners = models.Runner.objects.all()
	# runners = models.Runner.objects.filter(city__region_id=50)

	THOUSAND = 100
	if debug:
		print '{} update_runners_stat started'.format(datetime.datetime.now())
	n_runners = 0
	first_thousand = (id_from // THOUSAND) + 1
	max_thousand = (runners.order_by('-pk').first().id // THOUSAND) + 1
	for thousand in range(first_thousand, max_thousand + 1):
		for runner in runners.filter(id__range=(max(id_from, THOUSAND * (thousand - 1)), thousand * THOUSAND)).select_related('user').order_by('id'):
		# for runner in models.Runner.objects.annotate(Count('user_stat')).filter(user_stat__count__gt=5).select_related('user').order_by('id'):
			update_runner_stat(runner=runner, update_club_members=False)
			if debug >= 2:
				print 'Runner with id {} was updated'.format(runner.id)
			n_runners += 1
		if debug:
			print '{} Thousand finished: {}'.format(datetime.datetime.now(), thousand)
	if debug:
		print '{} update_runners_stat finished. Number of updated runners: {}, users: {}'.format(datetime.datetime.now(), n_runners, n_users)
	return n_runners

def update_users_stat():
	for user in User.objects.filter(user_profile__isnull=False):
		update_runner_stat(user=user)

def update_club_members_stat():
	n_members = 0
	for member in models.Club_member.objects.order_by('id'):
		update_runner_stat(club_member=member)
		n_members += 1
		if (member.id % 100) == 0:
			print member.id
	print "Done! Members updated:", n_members

def update_runners_wrong_stat():
	print '{} Started'.format(datetime.datetime.now())
	for runner_id in set(models.User_stat.objects.filter(pace_best=0, runner__isnull=False).values_list('runner', flat=True)):
		update_runner_stat(runner=models.Runner.objects.get(id=runner_id))
	print '{} Finished'.format(datetime.datetime.now())

def get_parkrun_series_ids_by_region_id(region_id):
	return set(models.Series.get_russian_parkruns().filter(city__region_id=region_id).values_list('id', flat=True))

def add_related_to_events(events):
	return events.select_related('series__city__region__country', 'city__region__country', 'series__country').prefetch_related(
		Prefetch('race_set',     queryset=models.Race.objects.select_related('distance').order_by('distance__distance_type',
			'-distance__length', 'precise_name')),
		Prefetch('review_set',   queryset=models.Document.objects.filter(document_type=models.DOC_TYPE_IMPRESSIONS)),
		Prefetch('photo_set',    queryset=models.Document.objects.filter(document_type=models.DOC_TYPE_PHOTOS)),
		Prefetch('news_set',     queryset=models.News.objects.order_by('-date_posted')),
		Prefetch('document_set', queryset=models.Document.objects.exclude(document_type__in=[9, 13]).order_by('document_type', 'comment')),
	).annotate(sum_finishers=Sum('race__n_participants_finished')).order_by('start_date', 'name')

def generate_default_calendar():
	context = {}
	today = datetime.date.today()
	events = []
	moscow_parkrun_ids = get_parkrun_series_ids_by_region_id(models.REGION_MOSCOW_ID)
	petersburg_parkrun_ids = get_parkrun_series_ids_by_region_id(models.REGION_SAINT_PETERSBURG_ID)
	other_parkrun_ids = set(models.Series.get_russian_parkruns().exclude(
		city__region_id__in=(models.REGION_MOSCOW_ID, models.REGION_SAINT_PETERSBURG_ID)).values_list('id', flat=True))
	parkrun_series_to_exclude = moscow_parkrun_ids | petersburg_parkrun_ids | other_parkrun_ids | set([results_util.OLD_PARKRUN_SERIES_ID])
	cur_day = today

	cis_countries = ('RU', 'BY', 'UA')
	cis_events = models.Event.objects.filter(invisible=False, cancelled=False).exclude(series__id__in=parkrun_series_to_exclude)
	cis_events = cis_events.filter(
		Q(city__region__country_id__in=cis_countries)
		| (Q(city=None) & Q(series__city__region__country_id__in=cis_countries))
		| (Q(city=None) & Q(series__city=None) & Q(series__country_id__in=cis_countries))
	)
	for _ in range(models.DAYS_IN_DEFAULT_CALENDAR):
		for event in add_related_to_events(cis_events.filter(start_date=cur_day)):
			events.append({'events': [event], 'is_single_event': True})
		if cur_day.weekday() == 5: # So it's Saturday
			events_today = add_related_to_events(models.Event.objects.filter(start_date=cur_day))
			moscow_parkruns = events_today.filter(series_id__in=moscow_parkrun_ids)
			if moscow_parkruns.exists():
				events.append({'events': moscow_parkruns})
			petersburg_parkruns = events_today.filter(series_id__in=petersburg_parkrun_ids)
			if petersburg_parkruns.exists():
				events.append({'events': petersburg_parkruns})
			other_parkruns = events_today.filter(series_id__in=other_parkrun_ids)
			if other_parkruns.exists():
				events.append({'events': other_parkruns, 'hide_cities': True})
		cur_day += datetime.timedelta(days=1)
	context['event_groups'] = events
	context['list_title'] = u"Календарь забегов в России, Украине, Беларуси на ближайший месяц ({})".format(
		models.dates2str(today, today + datetime.timedelta(days=models.DAYS_IN_DEFAULT_CALENDAR - 1)))
	generate_html('generators/default_calendar.html', context, 'default_calendar.html')

def generate_last_loaded_protocols():
	last_updates = models.Table_update.objects.filter(action_type=models.ACTION_RESULTS_LOAD).select_related('user').order_by(
		'-added_time')[:models.LAST_PROTOCOLS_EVENT_NUMBER * 6]
	used_race_ids = set()
	last_events = OrderedDict()
	editors = {}
	dates = {}
	for update in last_updates:
		race_id = update.child_id
		if race_id not in used_race_ids:
			used_race_ids.add(race_id)
			race = models.Race.objects.filter(pk=race_id).select_related('event__city__region__country', 'event__series__city__region__country',
				'event__series__country', ).first()
			if race:
				event = race.event
				user_name = update.user.get_full_name()
				if event in last_events:
					last_events[event] += u', <nobr>{}</nobr>'.format(race.distance)
					editors[event].add(user_name)
				else:
					if len(last_events) == models.LAST_PROTOCOLS_EVENT_NUMBER:
						break
					last_events[event] = u'<nobr>{}</nobr>'.format(race.distance)
					editors[event] = set([user_name])
					dates[event] = update.added_time
	res = OrderedDict()
	for event, distances in last_events.items():
		res[event] = {'distances': distances, 'editors': u', '.join(editors[event]), 'date': dates[event]}
	generate_html('generators/last_loaded_protocols.html', {'last_events': res}, 'last_loaded_protocols.html',
		to_old_probeg='dj_media/blocks/5_block_protokol.php')

def generate_last_added_reviews():
	last_reviews = models.Document.objects.filter(document_type__in=(models.DOC_TYPE_PHOTOS, models.DOC_TYPE_IMPRESSIONS), series=None).select_related(
		'created_by__user_profile', 'event__series__city__region__country', 'event__city__region__country').order_by(
		'-date_posted')[:models.LAST_PROTOCOLS_EVENT_NUMBER]
	res = []
	for review in last_reviews:
		user = review.created_by
		show_link_to_author = (review.author == user.get_full_name()) and hasattr(user, 'user_profile') and user.user_profile.is_public
		doc_type = u'отчёт' if (review.document_type == models.DOC_TYPE_IMPRESSIONS) else u'фотоальбом'
		res.append((review, doc_type, show_link_to_author))
	generate_html('generators/last_added_reviews.html', {'last_reviews': res}, 'last_added_reviews.html')

def generate_events_in_seria_by_year2(debug=False): # For Nadya
	with io.open(os.path.join(settings.BASE_DIR, 'results/templates/generated/events_in_seria_by_year.html'), 'w', encoding="utf8") as output_file:
		context_header = {}
		context_header['page_title'] = u"Все забеги {}-{} годов в России по сериям".format(
			models.NADYA_CALENDAR_YEAR_START, models.NADYA_CALENDAR_YEAR_END)
		context_header['last_update'] = datetime.datetime.now()
		output_file.write(render_to_string('generators/events_in_seria_by_year_header.html', context_header))

		series_ids = set(models.Event.objects.filter(series__city__region__country_id='RU', start_date__year__gte=2010).exclude(
			pk__in=models.Series.get_russian_parkrun_ids()).values_list('series_id', flat=True).distinct())
		all_series = models.Series.objects.filter(pk__in=series_ids).select_related('city')
		context = {}
		context['years'] = range(models.NADYA_CALENDAR_YEAR_START, models.NADYA_CALENDAR_YEAR_END + 1)
		# print 'Generating events in seria by year. Series number:', len(all_series), datetime.datetime.now()
		# counter = 0
		for region in models.Region.objects.filter(country_id='RU', active=True).order_by('name'):
			context['region'] = region
			context['seria'] = OrderedDict()
			for series in all_series.filter(city__region=region).order_by('city__name', 'name'):
				events = []
				for year in range(models.NADYA_CALENDAR_YEAR_START, models.NADYA_CALENDAR_YEAR_END + 1):
					events.append(series.event_set.filter(start_date__year=year).select_related('series__city__region__country',
						'city__region__country', 'series__country').order_by('start_date'))
				context['seria'][series] = events
			if debug:
				print u'{}: {} series are processed'.format(region.name_full, all_series.filter(city__region=region).count())
			output_file.write(render_to_string('generators/event_in_seria_by_year_spaces.html', context))
		output_file.write(render_to_string('generators/events_in_seria_by_year_footer.html', {}))

def best_result2value(distance, result): # Converts value from best_result field to centiseconds or meters
	result = result.strip()
	if result == '':
		return 0
	if distance.distance_type == models.TYPE_MINUTES:
		if result[-1] != u'м':
			return 0
		return results_util.int_safe(result[:-1].strip())
	else:
		res = re.match(r'^(\d{1,3}):(\d{2}):(\d{2})$', result)
		if res:
			return ((int(res.group(1)) * 60 + int(res.group(2))) * 60 + int(res.group(3))) * 100
		else:
			return 0

def update_course_records(series, to_clean=True, debug=False):
	races = models.Race.objects.filter(
		Q(loaded=models.RESULTS_LOADED) | ~Q(winner_male_result='') | ~Q(winner_female_result=''),
		event__series=series,
		is_for_handicapped=False,
	).select_related('distance', 'distance_real')
	if to_clean:
		races.update(is_male_course_record=False, is_female_course_record=False)
	races_by_distance_male = dict()
	races_by_distance_female = dict()
	distances = dict()
	for race in races:
		distance = race.distance_real if race.distance_real else race.distance
		best_male_result = race.result_set.filter(place_gender=1, gender=models.GENDER_MALE).first()
		if best_male_result:
			best_male_result = best_male_result.result
		else:
			best_male_result = best_result2value(distance, race.winner_male_result)
		best_female_result = race.result_set.filter(place_gender=1, gender=models.GENDER_FEMALE).first()
		if best_female_result:
			best_female_result = best_female_result.result
		else:
			best_female_result = best_result2value(distance, race.winner_female_result)
		if distance.id not in distances:
			distances[distance.id] = distance
		if best_male_result:
			# print race.event.start_date, best_male_result
			if (distance.id in races_by_distance_male):
				races_by_distance_male[distance.id].append((race, best_male_result))
			else:
				races_by_distance_male[distance.id] = [(race, best_male_result)]
		if best_female_result:
			if (distance.id in races_by_distance_female):
				races_by_distance_female[distance.id].append((race, best_female_result))
			else:
				races_by_distance_female[distance.id] = [(race, best_female_result)]
	for distance_id, distance in distances.items():
		for races_by_distance, field in \
				[(races_by_distance_male, 'is_male_course_record'), (races_by_distance_female, 'is_female_course_record')]:
			# distance_races = races_by_distance.get(distance_id, [])
			# if len(distance_races) < 2: # Should we mark as records distances with just one start?
			# 	continue
			if distance_id not in races_by_distance:
				continue
			distance_races = races_by_distance[distance_id]

			if distance.distance_type == models.TYPE_MINUTES:
				key = lambda x:-x[1]
			else:
				key = lambda x:x[1]
			distance_races.sort(key=key)
			best_result = distance_races[0][1]
			for race, winner_result in distance_races:
				if winner_result == best_result:
					if debug:
						if field == 'is_male_course_record':
							print race.id, winner_result
					setattr(race, field, True)
					race.save()
				else:
					break

def update_all_course_records(start_from=0):
	models.Race.objects.update(is_male_course_record=False, is_female_course_record=False)
	for series in models.Series.objects.filter(pk__gte=start_from).order_by('pk'):
		update_course_records(series, to_clean=False)
		if (series.id % 100) == 0:
			print series.id
	print 'Finished!'

def fix_race_headers(start_from=0, to_change=False):
	n_fixes = 0
	pattern = r'^\d:\d\d:\d\d$'
	# pattern = r'^(\d{2,3}) (\d{3})$'
	# pattern = r'^\d{4,7}$'
	for race in models.Race.objects.exclude(
			winner_male_result='', winner_female_result='').select_related('distance').order_by('pk'):
		for field in ['winner_male_result', 'winner_female_result']:
			value = getattr(race, field)
			res = re.match(pattern, value)
			if res:
				# new_value = u'{}{} м'.format(res.group(1), res.group(2))
				new_value = '0' + value
				# if len(value) < 7:
				# 	new_value = value + u' м'
				# else:
				# 	new_value = value + u'м'
				print u'Old: "{}", new: "{}"'.format(value, new_value)
				if to_change:
					setattr(race, field, new_value)
					race.save()
				n_fixes += 1
		# if n_fixes == 100:
		# 	break
	print 'Done! Fixes:', n_fixes

def check_result(distance, value):
	if value == '':
		return True
	if distance.distance_type == models.TYPE_MINUTES:
		patterns = [ur'^\d{1,6} м$', ur'^\d{7}м$']
	else:
		patterns = [r'^\d\d:\d\d:\d\d$',]
	return not all((re.match(pattern, value) is None) for pattern in patterns)

def check_race_headers(start_from=0):
	n_errors = 0
	for race in models.Race.objects.exclude(winner_male_result='', winner_female_result='').filter(
			distance__distance_type__gt=0).select_related('distance').order_by('pk'):
		for field in ['winner_male_result', 'winner_female_result']:
			value = getattr(race, field)
			if not check_result(race.distance, value):
				print u'Race: {}. Event: {}. {}: "{}"'.format(race.id, race.event_id, field, value)
				n_errors += 1
		# if n_errors >= 50:
		# 	break
	print 'Done! Errors:', n_errors

def get_runners_by_name_and_birthyear(lname, fname, year):
	runners = models.Runner.objects.filter(lname=lname, fname=fname, birthday__year=year)
	runners_with_extra_name_ids = models.Extra_name.objects.filter(lname=lname, fname=fname, runner__birthday__year=year).values_list(
		'runner_id', flat=True)
	return runners.union(models.Runner.objects.filter(pk__in=set(runners_with_extra_name_ids)))

def get_runners_by_name_and_birthday(lname, fname, midname, birthday):
	runners = models.Runner.objects.filter(lname=lname, fname=fname, birthday_known=True, birthday=birthday)
	if midname:
		runners = runners.filter(midname__in=('', midname))
	runners_with_extra_name = models.Extra_name.objects.filter(lname=lname, fname=fname, runner__birthday_known=True, runner__birthday=birthday)
	if midname:
		runners_with_extra_name = runners_with_extra_name.filter(midname__in=('', midname))
	runners_with_extra_name_ids = runners_with_extra_name.values_list('runner_id', flat=True)
	return runners.union(models.Runner.objects.filter(pk__in=set(runners_with_extra_name_ids)))

def attach_results_with_birthday(robot, admin, debug=False):
	n_results = 0
	n_results_for_klb = 0
	n_results_with_user = 0
	n_midnames_filled = 0
	n_winners_touched = 0
	touched_runners = set()
	mail_errors = ''
	mail_body = ''
	mail_summary = ''
	name_birthday_tuples = set(models.Result.objects.filter(runner=None, birthday_known=True, source=models.RESULT_SOURCE_DEFAULT).exclude(
		lname='').exclude(fname='').values_list('lname', 'fname', 'midname', 'birthday'))
	if debug:
		print 'Different tuples:', len(name_birthday_tuples)
	mail_header = (u'\nСегодня у нас {} различных наборов (ФИО, дата рождения) у результатов,' \
			+ u' не присоединённых ни к какому бегуну.').format(len(name_birthday_tuples))
	for lname, fname, midname, birthday in sorted(name_birthday_tuples):
		if n_results > 999:
			break
		runners = get_runners_by_name_and_birthday(lname, fname, midname, birthday)
		runners_count = runners.count()
		if runners_count > 1:
			mail_errors += u'\nЕсть больше одного бегуна {} {} {} {}. Непонятно, к кому присоединять такие результаты.'.format(
				lname, fname, midname, birthday.isoformat())
			if len(mail_errors) > 5000: # FIXME
				break
		elif runners_count == 1:
			runner = runners[0]
			for result in models.Result.objects.filter(runner=None, birthday_known=True, source=models.RESULT_SOURCE_DEFAULT,
					lname=lname, fname=fname, midname=midname, birthday=birthday).select_related('race__event'):
				n_results += 1
				race = result.race
				event = race.event
				event_date = event.start_date
				mail_body += (u'\n{}. {} ({}), {} ({}{}) — результат с id {} ({}, {}) — к бегуну {} ({}{}).').format(
					n_results, event, race, models.date2str(event_date, with_nbsp=False), models.SITE_URL, race.get_absolute_url(),
					result.id, result.strName(), result, runner.name(), models.SITE_URL, runner.get_absolute_url())
				result.runner = runner
				field_list = ['runner']
				if runner.user:
					result.user = runner.user
					result.add_for_mail()
					field_list.append('user')
					n_results_with_user += 1
					mail_body += u' Добавляем результат пользователю {} (id {}).'.format(runner.user.get_full_name(), runner.user.id)
				if result.midname and not runner.midname:
					runner.midname = result.midname
					mail_body += u' Поставили бегуну отчество {} от результата.'.format(result.midname)
					n_midnames_filled += 1
					runner.save()
					models.log_obj_create(robot, runner, models.ACTION_UPDATE, field_list=['midname'],
						comment=u'Автоматически при добавлении результата с id {}'.format(result.id), verified_by=admin)
				result.save()
				touched_runners.add(runner)
				is_for_klb = False
				klb_participant = None
				if runner.klb_person and models.is_active_klb_year(event_date.year):
					klb_participant = runner.klb_person.klb_participant_set.filter(match_year=event_date.year).first()
				if klb_participant and (result.get_klb_status() == models.KLB_STATUS_OK) \
						and ( (klb_participant.date_registered == None) or (klb_participant.date_registered <= event_date) ) \
						and ( (klb_participant.date_removed == None) or (klb_participant.date_removed >= event_date) ) \
						and not runner.klb_person.klb_result_set.filter(race__event=event).exists():
					is_for_klb = True
				models.log_obj_create(robot, event, models.ACTION_RESULT_UPDATE, field_list=field_list,
					child_object=result, comment=u'Автоматически по имени и дате рождения', is_for_klb=is_for_klb,
					verified_by=None if is_for_klb else admin)
				if is_for_klb:
					n_results_for_klb += 1
					mail_body += u' Добавляем результат в КЛБМатч.'
				if result.place_gender == 1:
					race.fill_winners_info()
					n_winners_touched += 1
	for runner in touched_runners:
		update_runner_stat(runner=runner)
		if runner.user:
			update_runner_stat(user=runner.user)
	if n_results:
		mail_body = u'\n\nПрисоединяем следующие результаты с датой рождения к бегунам:\n\n' + mail_body
		mail_summary += (u'\n\nИтого присоединено результатов: {}. В том числе:\nОтправлены на модерацию в КЛБМатч: {}.\n'\
			+ u'Привязаны к пользователям: {}.').format(n_results, n_results_for_klb, n_results_with_user)
		if n_midnames_filled:
			mail_summary += u'\n\nЗаполнены отчества бегунам на основании протоколов: {}.'.format(n_midnames_filled)
		n_users_for_letters = len(set(models.Result_for_mail.objects.filter(user__isnull=False, is_sent=False).values_list('user', flat=True)))
		mail_summary += u'\n\nПользователей, которым надо написать письма о новых результатах: {}.'.format(n_users_for_letters)
	if n_winners_touched:
		mail_summary += u'\n\nПривязано результатов победителей забегов: {}.'.format(n_winners_touched)
	if mail_errors:
		mail_errors = u'Ошибки при присоединении результатов к бегунам по дате рождения:\n\n' + mail_errors
	if debug:
		print 'Finished! Total results number: {}, for KLB: {}'.format(n_results, n_results_for_klb)
	return mail_header, mail_errors, mail_body, mail_summary

def create_new_runners_with_birthdays(robot, admin, debug=False):
	mail_errors = ''
	mail_body = ''
	mail_summary = ''
	free_official_results = models.Result.objects.filter(runner=None, birthday_known=True, source=models.RESULT_SOURCE_DEFAULT).exclude(
		lname='').exclude(fname='')
	name_birthday_tuples = set([(a.lower(), b.lower(), c) for a, b, c in free_official_results.values_list('lname', 'fname', 'birthday')])
	runner_tuples = set([(a.lower(), b.lower(), c) for a, b, c in models.Runner.objects.filter(birthday_known=True).values_list(
		'lname', 'fname', 'birthday')])
	n_good_tuples = 0
	n_errors = 0
	report_success = ''
	report_errors = ''
	for lname, fname, birthday in (name_birthday_tuples - runner_tuples):
		if n_good_tuples >= 100:
			break
		results = free_official_results.filter(lname=lname, fname=fname, birthday=birthday)
		if results.count() < 2:
			continue
		cur_midname = ''
		midname_error = False
		midnames = set(results.values_list('midname', flat=True))
		for midname in midnames:
			midname = midname.lower()
			if midname == '':
				continue
			if cur_midname.startswith(midname):
				continue
			if midname.startswith(cur_midname):
				cur_midname = midname
				continue
			midname_error = True
		if midname_error:
			if debug:
				print 'Data:', lname, fname, birthday
				print 'Midnames:', ', '.join(sorted(midnames))
			n_errors += 1
			mail_errors += u'\n{} {} ({}) — противоречивые отчества: {}'.format(lname, fname, birthday, ', '.join(sorted(midnames)))
			continue
		# print lname.title(), fname.title(), cur_midname.title(), unicode(birthday), unicode(results.count())
		n_similar_runners = get_runners_by_name_and_birthyear(lname, fname, birthday.year).count()
		if n_similar_runners:
			n_errors += 1
			mail_errors += u'\n{} {} ({}) — уже есть бегуны с такими же именем и годом рождения: {}{}'.format(lname, fname, birthday,
				models.SITE_URL, reverse('results:runners', kwargs={'lname': lname, 'fname': fname}))
			continue
		gender = models.Runner_name.objects.filter(name=fname).first()
		if gender is None:
			n_errors += 1
			mail_errors += u'\n{} {} ({}) — не получилось определить пол бегуна по имени'.format(lname, fname, birthday)
			continue
		runner = models.Runner.objects.create(
			lname=lname.title(),
			fname=fname.title(),
			midname=cur_midname.title(),
			birthday=birthday,
			birthday_known=True,
			gender=gender.gender,
			created_by=robot,
			)
		models.log_obj_create(robot, runner, models.ACTION_CREATE, comment=u'Создание нового бегуна по дате рождения', verified_by=admin)
		n_results_touched = 0
		for result in list(results):
			n_results_touched += 1
			result.runner = runner
			result.save()
			models.log_obj_create(robot, result.race.event, models.ACTION_RESULT_UPDATE, field_list=['runner'], child_object=result,
				comment=u'Создание нового бегуна по дате рождения', verified_by=admin)
		update_runner_stat(runner=runner)
		n_good_tuples += 1
		mail_body += u'\n{}. {} {} {} ({}, пол: {}) — создан: {}{}, привязано результатов: {}'.format(
			n_good_tuples, runner.lname, runner.fname, runner.midname, runner.birthday, runner.get_gender_display(),
			models.SITE_URL, runner.get_absolute_url(), n_results_touched)

		namesakes = models.Runner.objects.exclude(pk=runner.pk).filter(lname=runner.lname, fname=runner.fname)
		if namesakes.exists():
			mail_body += u'\nБегуны с теми же именем и фамилией ({}): {}{}'.format(
				namesakes.count(), models.SITE_URL, reverse('results:runners', kwargs={'lname': runner.lname, 'fname': runner.fname}))

	if n_good_tuples:
		mail_body = u'\n\nСоздаём новых бегунов по дате рождения:\n\n' + mail_body
		mail_summary += (u'\n\nИтого создано новых бегунов: {}.').format(n_good_tuples)
	if mail_errors:
		mail_errors = u'\n\nОшибки при создании бегунов по дате рождения:\n\n' + mail_errors
	if debug:
		print 'Done! Good tuples:', n_good_tuples, ', bad tuples:', n_errors
	return '', mail_errors, mail_body, mail_summary

# def attach_results_with_correct_year(): # Will we ever use it?..
# 	free_official_results = models.Result.objects.filter(runner=None, birthday_known=False, birthday__isnull=False,
# 		source=models.RESULT_SOURCE_DEFAULT).exclude(lname='').exclude(fname='')
# 	name_birthday_tuples = set([(a.lower(), b.lower(), c.year) for a, b, c in free_official_results.values_list('lname', 'fname', 'birthday')])
# 	n_good_tuples = 0
# 	n_results_attached = 0
# 	n_errors = 0
# 	f = open('/var/www/vhosts/probeg.org/httpdocs/names.txt', 'w')
# 	i = 0
# 	for lname, fname, year in name_birthday_tuples:
# 		i += 1
# 		if (i % 5000) == 0:
# 			print i, 'Good tuples:', n_good_tuples, ', results attached:', n_results_attached
# 		is_good_tuple = False
# 		runners = models.Runner.objects.filter(lname__iexact=lname, fname__iexact=fname, birthday__year=year)
# 		if runners.count() != 1:
# 			continue
# 		runner = runners[0]
# 		Q_year = Q(birthday=None) | ~Q(birthday__year=year)
# 		if runner.birthday_known:
# 			Q_year |= Q(birthday_known=True) & ~Q(birthday=runner.birthday)
# 		if models.Result.objects.filter(Q_year, lname__iexact=lname, fname__iexact=fname).exists():
# 			continue
# 		results = free_official_results.filter(lname__iexact=lname, fname__iexact=fname, birthday__year=year)
# 		midname = runner.midname.lower()
# 		for result in results:
# 			result_midname = result.midname.lower()
# 			if result_midname.startswith(midname) or midname.startswith(result_midname):
# 				is_good_tuple = True
# 				n_results_attached += 1
# 		if is_good_tuple:
# 			n_good_tuples += 1
# 	print 'Done! Good tuples:', n_good_tuples, ', results attached:', n_results_attached

N_BAD_USERS_TO_SEND = 3
def check_users_and_runners_links(robot):
	res = u''
	users_wo_profile = User.objects.filter(user_profile=None)
	if users_wo_profile.exists():
		res += u'\n\nПользователей, у которых не было профиля: {}. Первые:'.format(users_wo_profile.count())
		for user in users_wo_profile[:N_BAD_USERS_TO_SEND]:
			models.User_profile.objects.get_or_create(user=user)
			res += u'\n{} {}{} (создали профиль только что)'.format(
				user.get_full_name(), models.SITE_URL, reverse('results:user_details', kwargs={'user_id': user.id}))

	active_users_wo_runner = User.objects.filter(is_active=True, runner=None)
	if active_users_wo_runner.exists():
		res += u'\n\nАктивных пользователей, у которых не был указан бегун: {}. Первые:'.format(active_users_wo_runner.count())
		for user in active_users_wo_runner[:N_BAD_USERS_TO_SEND]:
			if hasattr(user, 'user_profile'):
				user.user_profile.create_runner(robot, comment=u'При ночной проверке роботом')
				res += u'\n{} {}{} (создали бегуна только что)'.format(user.get_full_name(), models.SITE_URL, user.user_profile.get_absolute_url())

	inactive_users_with_runner = User.objects.filter(is_active=False, runner__isnull=False)
	if inactive_users_with_runner.exists():
		res += u'\n\nНеактивных пользователей, у которых указан бегун: {}. Первые:'.format(inactive_users_with_runner.count())
		for user in inactive_users_with_runner[:N_BAD_USERS_TO_SEND]:
			if hasattr(user, 'user_profile'):
				res += u'\n{} {}{}'.format(user.get_full_name(), models.SITE_URL, user.user_profile.get_absolute_url())

	klb_persons_wo_runner = models.Klb_person.objects.filter(runner=None)
	if klb_persons_wo_runner.exists():
		res += u'\n\nУчастников КЛБМатчей, не привязанных ни к какому бегуну: {}. Первые:'.format(klb_persons_wo_runner.count())
		for person in klb_persons_wo_runner[:N_BAD_USERS_TO_SEND]:
			res += u'\n{} {}{}'.format(person.get_full_name_with_birthday(), models.SITE_URL, person.get_absolute_url())

	klb_results_wo_person = models.Klb_result.objects.filter(klb_person=None)
	if klb_results_wo_person.exists():
		res += u'\n\nРезультатов КЛБМатчей, не привязанных ни к какому КЛБ-участнику: {}. Первые:'.format(klb_results_wo_person.count())
		for klb_result in klb_results_wo_person[:N_BAD_USERS_TO_SEND]:
			res += u'\n{} (id {}), результат {} (id {})'.format(
				klb_result.race.name_with_event(), klb_result.race.id, klb_result.time_seconds_raw, klb_result.id)

	klb_results_wo_participant = models.Klb_result.objects.filter(klb_participant=None)
	if klb_results_wo_participant.exists():
		res += u'\n\nРезультатов КЛБМатчей, не привязанных ни к какому участнику отдельных матчей: {}. Первые:'.format(klb_results_wo_participant.count())
		for klb_result in klb_results_wo_participant[:N_BAD_USERS_TO_SEND]:
			res += u'\n{} (id {}), результат {} (id {})'.format(
				klb_result.race.name_with_event(), klb_result.race.id, klb_result.time_seconds_raw, klb_result.id)

	# 7383 - because of double Alexandr Terentyev in 2017
	min_id_klb_persons = models.Klb_person.objects.values('lname', 'fname', 'birthday').annotate(minid=Min('id')).order_by()
	min_ids = set(obj['minid'] for obj in min_id_klb_persons)
	duplicate_klb_persons = models.Klb_person.objects.exclude(pk=7383).exclude(id__in=min_ids)
	if duplicate_klb_persons.exists():
		res += u'\n\nПар участников КЛБМатчей с одинаковыми фамилией, именем, датой рождения: {}. Первые:'.format(duplicate_klb_persons.count())
		for person in duplicate_klb_persons[:N_BAD_USERS_TO_SEND]:
			res += u'\n{} {}{}'.format(person.get_full_name_with_birthday(), models.SITE_URL,
				reverse('results:runners', kwargs={'lname': person.lname, 'fname': person.fname}))

	results_on_races_with_one_runner = models.Klb_result.objects.filter(race__event__start_date__year__gte=2019, race__loaded=models.RESULTS_LOADED,
		race__n_participants__lte=1)
	n_bad_results = results_on_races_with_one_runner.count()
	if n_bad_results:
		res += u'\n\nРезультатов, учтённых в КЛБМатче, на стартах с не более чем одним участником: {}. Первые:'.format(n_bad_results)
		for klb_result in results_on_races_with_one_runner.select_related('race__event', 'klb_person__runner')[:N_BAD_USERS_TO_SEND]:
			race = klb_result.race
			runner = klb_result.klb_person.runner
			res += (u'\n{} ({}), {} ({}{}) — {} {}{}').format(
				race.event, race, models.date2str(race.event.start_date, with_nbsp=False), models.SITE_URL, race.get_absolute_url(),
				runner.name(), models.SITE_URL, runner.get_absolute_url())
	return res

def get_new_klb_reports_data():
	new_klb_reports_count = models.Klb_report.objects.filter(was_reported=False).count()
	if new_klb_reports_count:
		return u'\n\nСоздано новых слепков КЛБМатча: {}. Их полный список: {}{}'.format(
			new_klb_reports_count, models.SITE_URL, reverse('results:klb_reports'))
	else:
		return ''

def mark_old_payments_as_inactive():
	three_days_ago = timezone.now() - datetime.timedelta(days=3)
	n_payments_marked = models.Payment_moneta.objects.filter(is_active=True, is_paid=False, added_time__lte=three_days_ago).update(is_active=False)
	if n_payments_marked:
		n_participants_marked = models.Klb_participant.objects.filter(payment__is_active=False).update(payment=None, wants_to_pay_zero=False)
		return u'\n\nНеоплаченных платежей помечено как неактивные: {}, затронуто участников КЛБМатча: {}'.format(n_payments_marked, n_participants_marked)
	return ''

def get_db_checks_report():
	logger = logging.getLogger('dbchecks')

	res = u''
	# Checking ForeignKeys and OneToOneFields #
	for model_name, data in dbchecks.check_all_relationships2(logger).items():
		res += u'\n\nЗаписи в таблице {} с некорректными ссылками на другие таблицы: {}, {}'.format(model_name, data[0][0], data[0][1])
		res += u'\nЗапрос, который их выдаёт: {}'.format(data[1])

	# Checking equality #
	check_list = [
		(models.Klb_person, 'birthday', 'runner__birthday'), # disabled here
		(models.Klb_person, 'gender', 'runner__gender'),
		(models.Klb_result, 'event_raw_id', 'race__event_id'),
		(models.Klb_result, 'race_id', 'result__race_id'),
		(models.Klb_result, 'klb_person_id', 'klb_participant__klb_person_id'),
		(models.Klb_result, 'klb_person__runner__id', 'result__runner_id')  # Возможны, расхожения
	]

	for model_name, data in dbchecks.check_equality_by_list(check_list, logger).items():
		res += u'\n\nРасхождения в значениях полей {} — всего {}. Первые:'.format(model_name, data[0])
		for i, item in enumerate(data[1][:5]):
			res += u'\n{}. '.format(i + 1)
			for key, val in item.items():
				res += u'{}: {}\n'.format(key, val)
		res += u'\nЗапрос, который их выдаёт: {}'.format(data[2])
		res += u'\nКод на Python:'
		for line in data[3]:
			res += u'\n' + line
	return res

def make_connections_small():
	h, e, b, s = create_new_runners_with_birthdays(models.USER_ROBOT_CONNECTOR, models.USER_ROBOT_CONNECTOR, debug=True)
	print h
	print e
	print b
	print s

def make_connections(debug=False):
	mail_header = u'Доброе утро!\n\nНа связи Робот Присоединитель.'
	mail_errors = ''
	mail_body = ''
	mail_summary = ''

	try:
		h, e, b, s = attach_results_with_birthday(models.USER_ROBOT_CONNECTOR, models.USER_ROBOT_CONNECTOR, debug=debug)
		mail_header += h
		mail_errors += e
		mail_body += b
		mail_summary += s
	except Exception as err:
		mail_errors += u'\n\nНе удалось привязать результаты по дням рождения: {}'.format(err)

	try:
		h, e, b, s = create_new_runners_with_birthdays(models.USER_ROBOT_CONNECTOR, models.USER_ROBOT_CONNECTOR, debug=debug)
		mail_header += h
		mail_errors += e
		mail_body += b
		mail_summary += s
	except Exception as err:
		mail_errors += u'\n\nНе удалось создать новых бегунов: {}'.format(err)

	try:
		mail_errors += check_users_and_runners_links(models.USER_ROBOT_CONNECTOR)
	except Exception as err:
		mail_errors += u'\n\nНе удалось проверить ссылки у пользователей и бегунов: {}'.format(err)

	try:
		mail_errors += update_race_size_stat()
	except Exception as err:
		mail_errors += u'\n\nНе удалось проверить, у каких стартов уменьшилось число результатов: {}'.format(err)

	try:
		mail_body += get_new_klb_reports_data()
	except Exception as err:
		mail_errors += u'\n\nНе получилось напечатать информацию по новым слепкам КЛБМатча: {}'.format(err)

	try:
		mail_body += mark_old_payments_as_inactive()
	except Exception as err:
		mail_errors += u'\n\nНе удалось пометить неактивными старые неоплаченные платежи: {}'.format(err)

	try:
		mail_errors += get_db_checks_report()
	except Exception as err:
		mail_errors += u'\n\nНе удалось проверить таблицы на согласованность: {}'.format(err)

	mail_summary += u'\n\nНа сегодня это всё. До связи!\nВаш робот'
	message_from_site = models.Message_from_site.objects.create(
		sender_name=models.USER_ROBOT_CONNECTOR.get_full_name(),
		sender_email=models.INFO_MAIL_HEADER,
		target_email=models.INFO_MAIL,
		# target_email='alexey.chernov@gmail.com',
		title=u'Новости от Робота Присоединителя',
		message_type=models.MESSAGE_TYPE_TO_ADMINS,
		body=mail_header + '\n\n' + mail_errors + '\n\n' + mail_body + '\n\n' + mail_summary,
	)
	message_from_site.try_send(attach_file=False)
	if message_from_site.is_sent:
		models.Klb_report.objects.filter(was_reported=False).update(was_reported=True)

def fill_unknown_genders():
	n_names = 0
	for result in models.Result.objects.filter(source=models.RESULT_SOURCE_DEFAULT, gender=models.GENDER_UNKNOWN):
		name = models.Runner_name.objects.filter(name__iexact=result.fname).first()
		if name:
			# print result.fname, name.gender
			result.gender = name.gender
			result.save()
			n_names += 1
	print "Names corrected:", n_names

def get_runner_quantity_in_series(series_id):
	# series = models.Series.objects.get(pk=series_id)
	names = Counter()
	for result in models.Result.objects.filter(race__event__series_id=series_id):
		names[(result.lname, result.fname)] += 1
	for name, count in names.most_common(3):
		print name[0], name[1], count
		for result in models.Result.objects.filter(race__event__series_id=series_id, lname=name[0], fname=name[1]):
			print result.comment

def connect_winner_runners():
	race_ids = set(models.Result.objects.filter(source=models.RESULT_SOURCE_DEFAULT, place_gender=1, runner__isnull=False).values_list(
		'race_id', flat=True))
	print 'Races found:', len(race_ids)
	n_done = 0
	for race in models.Race.objects.filter(pk__in=race_ids).order_by('pk'):
		race.fill_winners_info()
		n_done += 1
		if (n_done % 200) == 0:
			print race.id
	print 'Finished!', n_done

def check_document_old_fields(to_repair=False): # Are there events with good documents but empty old fields?
	n_repaired = 0
	for doc_type, old_field_name in models.DOCUMENT_FIELD_NAMES.items():
		if doc_type == models.DOC_TYPE_PRELIMINARY_PROTOCOL:
			continue
		events_with_docs_ids = set(models.Document.objects.filter(~(Q(url_original='') & (Q(upload=None) | Q(hide_local_link=models.DOC_HIDE_ALWAYS))),
			document_type=doc_type).values_list('event_id', flat=True))
		kwargs = {}
		kwargs[old_field_name] = ''
		bad_events = models.Event.objects.filter(pk__in=events_with_docs_ids, **kwargs)
		print doc_type, models.DOCUMENT_TYPES[doc_type][1], bad_events.count()
		if to_repair:
			for event in bad_events:
				doc = event.document_set.filter(document_type=doc_type).first()
				if doc:
					doc.update_event_field()
					n_repaired += 1
		if bad_events:
			print 'First:', bad_events[0].id, bad_events[0].name
	if n_repaired:
		print 'Repaired: {} fields'.format(n_repaired)

def fill_n_male_participants():
	n_fixed = 0
	for race in models.Race.objects.filter(n_participants__gt=0, loaded=models.RESULTS_LOADED).order_by('id'):
		results = race.get_official_results()
		participants = results.exclude(status=models.STATUS_DNS)
		if race.n_participants != participants.count():
			# print 'Race {} {}: {} real participants, {} saved in n_participants'.format(race.id, race, participants.count(), race.n_participants)
			race.n_participants = participants.count()
		# race.n_participants_men = participants.filter(gender=models.GENDER_MALE).count()
			race.save()
			n_fixed += 1
			if (n_fixed % 100) == 0:
				print n_fixed, race.id
	print 'Done!', n_fixed

def print_race_results_anonimized_csv_for_melekhov():
	# race = models.Race.objects.get(pk=race_id)
	series_ids = [1358, 1559, 1560, 1357, 1359, 185]
	races = models.Race.objects.filter(event__series_id__in=series_ids, is_for_handicapped=False, loaded=models.RESULTS_LOADED,
		event__start_date__range=(datetime.date(2009, 1, 1), datetime.date.today()))
	with io.open('all-for-melekhov.csv', 'w', encoding="cp1251") as output_file:
		output_file.write(
			u'ID старта;Название;Дата;Дистанция;Фактическая дистанция;№ результата;Пол;Дата/год рождения;Возраст;Время;Время в сотых секунды\n')
		for race in races:
			results = race.result_set.exclude(age=None, birthday=None).filter(status=models.STATUS_FINISHED).order_by('result')
			for i, result in enumerate(results):
				output_file.write(u';'.join(unicode(x) for x in [race.id, race.event.name, race.event.start_date, race.distance_with_heights(),
					race.distance_real if race.distance_real else '',
					i + 1, result.get_gender_display(), result.strBirthday(with_nbsp=False, short_format=True), result.age if result.age else '',
					result, result.result]) + u'\n')

def get_results_for_melekhov(): # For avmelekhov@gmail.com at 2018-08-16
	series_ids = [1358, 1559, 1560, 1357, 1359, 185]
	races = models.Race.objects.filter(event__series_id__in=series_ids, is_for_handicapped=False,
		event__start_date__range=(datetime.date(2009, 1, 1), datetime.date.today()))
	n_finishers = 0
	with io.open('all_events.csv', 'w', encoding="cp1251") as output_file:
		output_file.write(
			u'Название;Дата;Дистанция;Фактическая дистанция, если отличается;Загружены ли результаты;'
			+ u'Всего финишировало;В том числе у кого известны пол и возраст\n')
		for race in races.order_by('event__series_id', 'event__start_date', '-distance__length'):
			results = race.result_set.filter(status=models.STATUS_FINISHED)
			output_file.write(u';'.join(unicode(x) for x in [race.event.name, race.event.start_date, race.distance_with_heights(),
				race.distance_real if race.distance_real else '',
				race.get_loaded_display(), results.count(), results.exclude(age=None, birthday=None).count()]) + u'\n')
			if race.n_participants_finished:
				n_finishers += results.count() #race.n_participants_finished

def compare_with_old_results(debug=False):
	race_ids = set(models.Result1705.objects.values_list('race_id', flat=True).distinct())
	thousand_max = max(race_ids) // 1000
	with io.open('results_disappeared.txt', 'w') as output_file:
		for thousand in range(0, thousand_max + 1):
			if debug:
				print thousand
			ids_in_thousand = [i for i in range(1000*thousand, 1000*(thousand + 1)) if i in race_ids]
			for race in models.Race.objects.filter(pk__in=ids_in_thousand).select_related('event', 'race_size', 'distance').order_by('id'):
				old_n_res = [0] * 3
				new_n_res = [0] * 3
				to_print = False
				for i, _ in models.RESULT_SOURCES:
					old_n_res[i] = race.result1705_set.filter(source=i).count()
					new_n_res[i] = race.result_set.filter(source=i).count()
					# if old_n_res[i] > new_n_res[i]:
					# 	to_print = True
				if (old_n_res[0] > new_n_res[0]) or (sum(old_n_res) > sum(new_n_res)):
					output_file.write(u'{}	{}	{}{}	{}	{}	{}	{}	{}	{}\n'.format(race.name_with_event(), race.event.start_date,
						models.SITE_URL, race.get_absolute_url(), 
						old_n_res[0], old_n_res[1], old_n_res[2], new_n_res[0], new_n_res[1], new_n_res[2]))

def find_bad_paces():
	n_res = 0
	thousand_max = models.User_stat.objects.exclude(runner=None).order_by('-pk').first().id // 10000
	print thousand_max
	for thousand in range(0, thousand_max + 1):
		for stat in models.User_stat.objects.exclude(runner=None).exclude(value_best=None).filter(
				pk__range=(10000*thousand, 10000*(thousand + 1) - 1),
				distance__distance_type__in=(models.TYPE_METERS, models.TYPE_MINUTES)
				).order_by('pk').select_related('best_result__race', 'distance'):
			pace_best = stat.distance.get_pace(stat.value_best)
			if pace_best > 10000:
				print stat.runner.id, stat.distance, stat.best_result.race_id
				n_res += 1
				if n_res == 20:
					return

def find_too_slow_results():
	results = models.Result.objects.filter(race__distance__distance_type=models.TYPE_METERS)
	for length, centiseconds in ((42000, 10*3600*100), (20000, 5*3600*100), (10000, 3*3600*100), (3000, 2*3600*100), (1000, 1800*100)):
		results_count = results.filter(race__distance__length__lte=length, result__gte=centiseconds).count()
		if results_count:
			print length, centiseconds, results_count

def fix_results_gender(): # When there are too many results with unknown gender
	# for i in range(30):
	# 	for r in models.Result.objects.filter(gender=0, klb_result__isnull=False).select_related('klb_result__klb_person')[:1000]:
	# 		r.gender = r.klb_result.klb_person.gender
	# 		r.save()
	# 	print i
	for r in models.Result.objects.filter(gender=0, runner_id__gt=0).select_related('runner'):
		if r.runner.gender:
			r.gender = r.runner.gender
			r.save()
		else:
			print r.runner.id, r.runner.name_with_midname()
	# for runner in models.Runner.objects.filter(gender=0):
	# 	name = models.Runner_name.objects.filter(name=runner.fname).first()
	# 	if name:
	# 		runner.gender = name.gender
	# 		runner.save()
	# 	else:
	# 		print runner.id, runner.name_with_midname()
	print 'Done!'

def fix_best_result_length():
	count = 0
	for race in models.Race.objects.filter(winner_male_result__startswith='0').exclude(winner_male_result__startswith='0:'):
		if (len(race.winner_male_result) > 5) and race.winner_male_result[0] == '0' and race.winner_male_result[2] == ':':
			count += 1
			race.winner_male_result = race.winner_male_result[1:]
			race.save()
	print count
	count = 0
	for race in models.Race.objects.filter(winner_female_result__startswith='0').exclude(winner_female_result__startswith='0:'):
		if (len(race.winner_female_result) > 5) and race.winner_female_result[0] == '0' and race.winner_female_result[2] == ':':
			count += 1
			race.winner_female_result = race.winner_female_result[1:]
			race.save()
	print count

def set_unique_starts_as_race_records(debug=True):
	thousand_max = models.Race.objects.order_by('-pk').values_list('pk', flat=True)[0] // 1000
	good_races = models.Race.objects.filter(event__start_date__lte=datetime.date.today(), distance_real=None)
	male_records = female_records = 0
	for thousand in range(0, thousand_max + 1):
		if debug:
			print thousand, male_records, female_records
		for race in good_races.filter(pk__range=(1000*thousand, 1000*(thousand+1) - 1)).select_related('event').order_by('id'):
			if good_races.filter(event__series_id=race.event.series_id, distance=race.distance).count() == 1:
				if race.winner_male_result and not models.Race.objects.filter(event__series_id=race.event.series_id, distance=race.distance,
						is_male_course_record=True).exists():
					race.is_male_course_record = True
					race.save()
					male_records += 1
				if race.winner_female_result and not models.Race.objects.filter(event__series_id=race.event.series_id, distance=race.distance,
						is_female_course_record=True).exists():
					race.is_female_course_record = True
					race.save()
					female_records += 1
	print 'Done!', male_records, female_records

def most_popular_clubs(year=2018, to_exclude_parkrun=True):
	results = models.Result.objects.filter(race__event__start_date__year=year, source=models.RESULT_SOURCE_DEFAULT)
	if to_exclude_parkrun:
		results = results.exclude(race__event__series_id__in=models.Series.get_russian_parkrun_ids())
	c = Counter(s.lower().replace(u'"', u'').replace(u'\n', u' ').replace(u'   ', u' ').replace(u'  ', u' ').replace(u'“', u'').replace(u'”', u'').replace(
			u'«', u' ').replace(u'»', u'').replace(u'клб ', u'').replace(u'клуб любителей бега ', u'').replace(u'клуб ', u'').strip()
		for s in results.values_list('club_name', flat=True))

	# with io.open('club_names_2018.txt', 'w', encoding="utf8") as output_file:
	# 	for k, v in sorted(c.items()):
	# 		# output_file.write(u'{}\t{}\n'.format(k, v))
	# 		output_file.write(u'{}\n'.format(k))
	# return

	with io.open('club_names_2018_win.txt', 'w', encoding="cp1251") as output_file:
		for k, v in sorted(c.items()):
			try:
				s_cp1251 = u''.join([i if is_good_symbol(i) else '' for i in k])
				output_file.write(s_cp1251 + '\n')
			except Exception as e:
				pass
	return

	bad_club_names = [u'', u'независимый', u'лично', u'noclub', u'-', u'rus', u'нет клуба/no club', u'санкт-петербург', u'(kyiv)', u'нет', u'(dnipro)']
	for bad_name in bad_club_names:
		if bad_name in c:
			del c[bad_name]

	other_names = [
		(u'wake&amp;run', u'wake&run'),
		(u'клб "вита"', u'вита'),
		(u'ilr', u'i love running'),
		(u'мк "бим"', u'бим'),
		(u'ао "фпк"', u'фпк'),
		# (u'', u''),
		# (u'', u''),
		# (u'', u''),
		# (u'', u''),
	]

	for bad, good in other_names:
		if bad in c:
			c[good] += c[bad]
			del c[bad]

	for club, count in c.most_common(200):
		print club, '%t', count
	print 'Total', len(c)

def load_splits():
	result = models.Result.objects.get(pk=3495676)
	result.split_set.all().delete()
	n_splits = 0
	with io.open('/home/admin/chernov/2019-06-11-nyrr-5k.csv', 'r') as input_file:
		for line in input_file:
			fields = line.split(';')
			length = results_util.int_safe(fields[0])
			if length == 0:
				print 'Wrong length:', line
				return
			distance = models.Distance.objects.get(distance_type=models.TYPE_METERS, length=length)
			res = re.match(r'^(\d{1,2}):(\d{2})\.(\d{2})(\d)$', fields[1]) # minutes[:.,]seconds[.,]centiseconds_lastdigit
			if res:
				hours = 0
				minutes = int(res.group(1))
				seconds = int(res.group(2))
				hundredths = int(res.group(3))
				thousandths = int(res.group(4))
				if thousandths:
					if hundredths < 99:
						hundredths += 1
					elif seconds < 59:
						hundredths = 0
						seconds += 1
					elif minutes < 59:
						hundredths = 0
						seconds = 0
						minutes += 1
					else:
						hundredths = 0
						seconds = 0
						minutes = 0
						hours += 1
				value = models.tuple2centiseconds(hours, minutes, seconds, hundredths)
				models.Split.objects.create(result=result, distance=distance, value=value)
				n_splits += 1
	print 'Splits created:', n_splits

def fill_n_parkrun_results_once():
	n_parkrun_ids = Counter()
	for runner_id in models.Result.objects.exclude(parkrun_id=None).exclude(runner_id=None).values_list('runner_id', flat=True):
		n_parkrun_ids[runner_id] += 1
	print 'runners:', len(n_parkrun_ids)
	print n_parkrun_ids[87357]
	n_fixed = 0
	for runner_id, count in n_parkrun_ids.items():
		models.Runner.objects.filter(pk=runner_id).update(n_parkrun_results=count)
		n_fixed += 1
		if (n_fixed % 1000) == 0:
			print n_fixed

def print_most_active_users():
	user_ids = []
	emails = []
	for user in User.objects.filter(is_superuser=False).annotate(Count('table_update')).order_by('-table_update__count')[:50]:
		print(u'{} {} {}'.format(user.email, user.get_full_name(), user.table_update__count))
		user_ids.append(user.id)
		if not models.is_admin(user):
			emails.append(user.email)
	print(user_ids)
	print(', '.join(emails))

def try_call_function(desc, func, **kwargs):
	try:
		function_call = models.Function_call.objects.create(
			name=func.__name__,
			args=u', '.join(u'{}={}'.format(k, v) for k, v in kwargs.items()),
			description=desc,
			start_time=timezone.now(),
		)
		try:
			func(**kwargs)
			function_call.running_time = timezone.now() - function_call.start_time
			function_call.save()
		except Exception as e:
			function_call.error = repr(e)
			try:
				function_call.save()
			except:
				pass
	except:
		pass
