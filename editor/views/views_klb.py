# -*- coding: utf-8 -*-
from __future__ import division
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.db.models.query import Prefetch
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import connection
from django.http import Http404

from collections import Counter
import datetime
import math
import time

from results import models, models_klb
from .views_common import group_required
from .views_stat import update_runner_stat
from .views_klb_stat import length2bonus, meters2distance_raw, roundup_centiseconds, distance2meters, get_distance, klb_result2value
from .views_klb_stat import get_klb_score_for_result, update_participants_score, update_match

# Call this only if all tests are passed, including: person is participant at the day of race and result.runner is in (person.runner, None)
def create_klb_result(result, person, user, distance=None, was_real_distance_used=None, only_bonus_score=False, comment='', participant=None):
	runner, created = person.get_or_create_runner(user)
	result.runner = runner
	if runner.user:
		old_user = result.user
		result.user = runner.user
		result.add_for_mail(old_user=old_user)
	result.save()
	if distance is None:
		distance, was_real_distance_used = result.race.get_distance_and_flag_for_klb()
	meters = result.result if (distance.distance_type == models.TYPE_MINUTES) else distance.length
	year = result.race.event.start_date.year
	if participant is None:
		participant = person.klb_participant_set.filter(match_year=year).first()
	klb_result = models.Klb_result(
		klb_person=person,
		klb_participant=participant,
		result=result,
		race=result.race,
		distance_raw=meters2distance_raw(meters),
		time_seconds_raw=(distance.length * 60) if (distance.distance_type == models.TYPE_MINUTES) else roundup_centiseconds(result.result),
		was_real_distance_used=was_real_distance_used,
		added_by=user,
	)
	klb_result.klb_score = 0 if only_bonus_score else get_klb_score_for_result(klb_result)
	if klb_result.klb_score > models_klb.MAX_CLEAN_SCORE:
		klb_result.klb_score = 0
	klb_result.bonus_score = length2bonus(meters, year)
	klb_result.clean()
	klb_result.save()
	models.log_obj_create(user, result.race.event, models.ACTION_KLB_RESULT_CREATE, child_object=klb_result, comment=comment)
	klb_result.refresh_from_db()
	connection.cursor().execute("UPDATE KLBresults SET FinTime = %s WHERE IDres = %s",
		[models.secs2time(klb_result.time_seconds_raw, fill_hours=False), klb_result.id])
	return klb_result

def update_klb_result_time(klb_result, user): # When race type is TYPE_METERS and only time was changed
	result = klb_result.result
	klb_result.time_seconds_raw = roundup_centiseconds(result.result)
	klb_result.klb_score = get_klb_score_for_result(klb_result)
	klb_result.save()
	connection.cursor().execute("UPDATE KLBresults SET FinTime = %s WHERE IDres = %s",
		[models.secs2time(klb_result.time_seconds_raw, fill_hours=False), klb_result.id])
	models.log_obj_create(user, result.race.event, models.ACTION_KLB_RESULT_UPDATE, field_list=['time_seconds_raw', 'klb_score'], child_object=klb_result)

def update_klb_result_meters(klb_result, user, year=None): # When race type is TYPE_MINUTES and only distance was changed
	result = klb_result.result
	if year is None:
		year = result.race.event.start_date.year
	klb_result.distance_raw = meters2distance_raw(result.result)
	klb_result.klb_score = get_klb_score_for_result(klb_result)
	klb_result.bonus_score = length2bonus(result.result, year)
	klb_result.save()
	models.log_obj_create(user, result.race.event, models.ACTION_KLB_RESULT_UPDATE, field_list=['distance_raw', 'klb_score'], child_object=klb_result)

def update_klb_result_bonuses(race): # Update all bonuses for results for given race
	year = race.event.start_date.year
	if not models.is_active_klb_year(year):
		print 'Bad year'
		return
	if race.distance.distance_type != models.TYPE_MINUTES:
		print 'Bad distance: it must me TYPE_MINUTES'
		return
	n_wrong_bonuses = 0
	for klb_result in race.klb_result_set.select_related('result'):
		if abs(float(klb_result.bonus_score) - length2bonus(klb_result.result.result, year)) > 0.0005:
			print 'Old bonus:', klb_result.bonus_score, ' correct bonus:', length2bonus(klb_result.result.result, year)
			klb_result.bonus_score = length2bonus(klb_result.result.result, year)
			klb_result.save()
			models.log_obj_create(models.USER_ROBOT_CONNECTOR, race.event, models.ACTION_KLB_RESULT_UPDATE,
				field_list=['bonus_score'], child_object=klb_result)
			n_wrong_bonuses += 1
	print 'Wrong bonuses:', n_wrong_bonuses

def recalc_klb_result(klb_result, user, comment): # E.g. when age or gender of runner has changed. Returns True if result was changed
	result = klb_result.result
	score_old = klb_result.klb_score
	score_new = get_klb_score_for_result(klb_result) if (klb_result.klb_score > 0) else 0
	if abs(score_new - float(score_old)) > 0.0005:
		klb_result.klb_score = get_klb_score_for_result(klb_result) if (klb_result.klb_score > 0) else 0
		klb_result.save()
		models.log_obj_create(user, result.race.event, models.ACTION_KLB_RESULT_UPDATE, field_list=['klb_score'],
			child_object=klb_result, comment=comment)
		return True
	return False

def create_results_for_klb(year, debug=True):
	user = models.USER_ROBOT_CONNECTOR
	results_created = 0
	runners_created = 0
	problems = []
	touched_runners = set()
	for klb_result in models.Klb_result.objects.filter(race__event__start_date__year__gte=year, result=None, is_error=False).exclude(
		race__loaded__in=models.RESULTS_SOME_OR_ALL_OFFICIAL):
	# for klb_result in models.Klb_result.objects.filter(race__event__id=9268, result=None):
		klb_person = klb_result.klb_person
		runner = klb_person.runner
		parsed, value = klb_result2value(klb_result)
		if parsed:
			result = models.Result.objects.create(
				race=klb_result.race,
				runner=runner,
				user=runner.user,
				loaded_by=user,
				lname=klb_person.lname,
				fname=klb_person.fname,
				source=models.RESULT_SOURCE_KLB,
				gender=klb_person.gender,
				status=models.STATUS_FINISHED,
				result=value,
			)
			klb_result.result = result
			klb_result.save()
			models.log_obj_create(user, result.race.event, models.ACTION_KLB_RESULT_UPDATE, field_list=['result'], child_object=klb_result,
				comment=u'Автоматически по КЛБ-результату')
			touched_runners.add(runner)
			if klb_result.race.loaded == models.RESULTS_NOT_LOADED:
				klb_result.race.loaded = models.RESULTS_SOME_UNOFFICIAL
				klb_result.race.save()
		else:
			problems.append((klb_result.id, klb_result.race.id, klb_result.distance_raw, klb_result.time_seconds_raw))
		results_created += 1
		if debug:
			if (results_created % 500) == 0:
				print results_created
	for runner in touched_runners:
		update_runner_stat(runner=runner)
		if runner.user:
			update_runner_stat(user=runner.user, update_club_members=False)
	if debug:
		print 'Finished! Results created: {}'.format(results_created)
		print 'Runners created: {}'.format(runners_created)
		print "Results with problems:", '\n'.join(unicode(x) for x in problems)
	return results_created

def attach_klb_results(year, debug=False):
	"""We look at all klb_results with result=None and try to find official or unofficial result for them"""
	results_absent = {}
	n_results_found_with_runner = 0
	n_results_found_wo_runner = 0
	race_w_unlinked_klb_results_ids = set(models.Klb_result.objects.filter(
		result=None,
		race__event__start_date__year__gte=year,
		is_error=False,
	).values_list('race', flat=True))
	races = models.Race.objects.filter(id__in=race_w_unlinked_klb_results_ids).exclude(loaded=models.RESULTS_NOT_LOADED).select_related(
		'distance').order_by('id')
	for race in races:
		race_year = race.event.start_date.year
		race_results = race.result_set
		is_active_klb_year = models.is_active_klb_year(race_year)
		klb_results = race.klb_result_set.filter(result=None, is_error=False).select_related('klb_person__runner')
		for klb_result in klb_results:
			result_found = False
			person = klb_result.klb_person
			appropriate_race_results = race_results.filter(status=models.STATUS_FINISHED)
			if race.distance.distance_type != models.TYPE_MINUTES:
				appropriate_race_results = appropriate_race_results.filter(
					result__range=(klb_result.time_seconds_raw * 100 - 99, klb_result.time_seconds_raw * 100))

			result = appropriate_race_results.filter(runner=person.runner).first()
			if not result:
				result = appropriate_race_results.filter(Q(lname=person.lname, fname=person.fname) | Q(lname=person.fname, fname=person.lname)).first()

			if result:
				results_are_equal = False
				if race.distance.distance_type == models.TYPE_MINUTES:
					parsed, meters = distance2meters(klb_result.distance_raw)
					if parsed and (result.result == meters):
						results_are_equal = True
				else: # Distance type is meters
					seconds = int(math.ceil(result.result / 100))
					if seconds == klb_result.time_seconds_raw:
						results_are_equal = True
					# elif (abs(seconds - klb_result.time_seconds_raw) < 60) and not is_active_klb_year:
					# 	# If year is not KLB-active, we connect more results
					# 	results_are_equal = True
				if results_are_equal:
					if hasattr(result, 'klb_result'):
						if debug:
							print 'Trying to link klb_result {} to result {} but the latter already has its klb_result'.format(
								klb_result.id, result.id)
					if result.runner and (result.runner != person.runner):
						if debug:
							print 'Trying to link klb_result {} to result {} but they have different runners: {}, {}'.format(
								klb_result.id, result.id, result.runner.id, person.runner.id)
					else:
						# if klb_result.result: # Now this result with source=RESULT_SOURCE_KLB isn't needed
						# 	klb_result.result.delete()
						klb_result.result = result
						klb_result.save()
						if result.runner is None:
							runner = person.runner
							result.runner = runner
							result.user = runner.user
							result.save()
							n_results_found_wo_runner += 1
						else:
							n_results_found_with_runner += 1
						result_found = True
			if not result_found:
				if race.id in results_absent:
					results_absent[race.id].add((klb_result, result, is_active_klb_year))
				else:
					results_absent[race.id] = set([(klb_result, result, is_active_klb_year)])
	return results_absent, n_results_found_wo_runner, n_results_found_with_runner

def restore_strava_link_if_needed(user, result, lost_result):
	if lost_result.strava_link:
		result_on_strava = models.Result_on_strava.objects.create(
			result=result,
			link=lost_result.strava_link,
			added_by=user,
		)
		models.log_obj_create(user, result_on_strava, models.ACTION_CREATE, comment=u'При восстановлении потерянного результата')

def attach_lost_results(year, user, request=None):
	# We try to connect each lost result to new result from the same race
	n_deleted_lost_results = 0
	lost_results = []
	touched_runners = set()
	for lost_result in list(models.Lost_result.objects.filter(
			race__event__start_date__year__gte=year).select_related('race').order_by('race_id')):
		race = lost_result.race
		# TODO check: is there any command in POST?
		result_from = lost_result.result - 100
		result_to = lost_result.result + 100
		result_to_connect = race.result_set.filter(
			Q(lname__iexact=lost_result.lname, fname__iexact=lost_result.fname)
			| Q(lname__iexact=lost_result.fname, fname__iexact=lost_result.lname),
			Q(result__range=(result_from, result_to)) | Q(result=lost_result.result // 60),
			status=lost_result.status).first()
		if (result_to_connect is None) and request:
			select_name = 'result_for_lost_{}'.format(lost_result.id)
			if select_name in request.POST:
				result_to_connect = models.Result.objects.filter(pk=request.POST[select_name]).first()
		if (result_to_connect is None) and request:
			if 'delete_lost_result_{}'.format(lost_result.id) in request.POST:
				lost_result.delete()
				n_deleted_lost_results += 1
				continue
		if result_to_connect:
			result_is_restored = False
			if (result_to_connect.runner == lost_result.runner) and (result_to_connect.user == lost_result.user):
				result_is_restored = True
			elif (result_to_connect.runner is None) and (result_to_connect.user is None):
				result_to_connect.runner = lost_result.runner
				result_to_connect.user = lost_result.user
				result_to_connect.save()
				models.log_obj_create(user, race.event, models.ACTION_RESULT_UPDATE,
					field_list=['user', 'runner'], child_object=result_to_connect, comment=u'При восстановлении привязки')
				result_is_restored = True
			
			if result_is_restored:
				restore_strava_link_if_needed(user, result_to_connect, lost_result)
				lost_result.delete()
				n_deleted_lost_results += 1
				touched_runners.add(result_to_connect.runner)
			else:
				if request:
					messages.warning(request, u'Возникла проблема с привязками у результата с id {}'.format(result_to_connect.id))
				lost_results.append(lost_result)
		else:
			lost_results.append(lost_result)
	if touched_runners:
		for runner in touched_runners:
			update_runner_stat(runner=runner)
			if runner.user:
				update_runner_stat(user=runner.user, update_club_members=False)
		messages.success(request, u'При привязке старых результатов затронуто бегунов: {}. Их статистика пересчитана.'.format(len(touched_runners)))
	return lost_results, n_deleted_lost_results

@group_required('admins')
def klb_status(request, year=0):
	year = models.int_safe(year)
	context = {}
	context['oldest_year'] = 1950
	if (year > models.CUR_KLB_YEAR) or (year < context['oldest_year']):
		year = models.CUR_KLB_YEAR - 1
	context['year'] = year
	context['last_active_year'] = max(models.CUR_KLB_YEAR, models.NEXT_KLB_YEAR)
	context['page_title'] = u'Статус КЛБМатча'

	# Part 1. We look at all klb_results with race=None and try to find race for them (hope it isn't used now)
	# models.write_log(u'{} KLB Status: Step 1'.format(datetime.datetime.now()))
	events_absent = set()
	distances_not_parsed = set()
	distances_absent = set()
	races_absent = set()
	n_results = 0
	for result in models.Klb_result.objects.filter(race=None, event_raw__start_date__year__gte=year).select_related('event_raw'):
		distance_raw = result.distance_raw
		time_seconds_raw = result.time_seconds_raw
		event = result.event_raw
		if event is None:
			events_absent.add(result.id)
			continue
		distance_type, length = get_distance(distance_raw, time_seconds_raw)
		if distance_type is None:
			distances_not_parsed.add((event.id, distance_raw, time_seconds_raw))
			continue
		distance = models.Distance.objects.filter(distance_type=distance_type, length=length).first()
		if distance is None:
			distances_absent.add((event.id, models.DIST_TYPES[distance_type][1], length))
			continue
		race = event.race_set.filter(Q(distance=distance) | Q(distance_real=distance)).first()
		if race is None:
			races_absent.add((event, distance))
			continue
		result.race = race
		if race.distance == distance:
			result.was_real_distance_used = models.DISTANCE_FOR_KLB_FORMAL
		else: # race.distance_real == distance
			result.was_real_distance_used = models.DISTANCE_FOR_KLB_REAL
		result.save()
		n_results += 1
	context['events_absent'] = events_absent
	context['distances_not_parsed'] = distances_not_parsed
	context['distances_absent'] = distances_absent
	context['races_absent'] = sorted(races_absent, key=lambda x:x[0].id)
	if n_results:
		messages.success(request, u'Только что мы проставили дистанции у {} результатов'.format(n_results))

	# Part 2. We look at all klb_results with result=None and try to find official or unofficial result for them
	# models.write_log(u'{} KLB Status: Step 2'.format(datetime.datetime.now()))
	klb_results_absent, n_results_found_wo_runner, n_results_found_with_runner = attach_klb_results(year)
	if n_results_found_wo_runner or n_results_found_with_runner:
		messages.success(request, u'Только что мы привязали к БД результатов {} результатов, у которых не было бегуна, и {} — у которых был'.format(
			n_results_found_wo_runner, n_results_found_with_runner))
	context['klb_results_absent'] = [(models.Race.objects.get(pk=race_id), results) for race_id, results in klb_results_absent.items()]

	# Part 3. We create results for all klb_results without corresponding row in Result table
	# models.write_log(u'{} KLB Status: Step 3'.format(datetime.datetime.now()))
	n_results_created = create_results_for_klb(year=year, debug=False)
	if n_results_created:
		messages.success(request, u'Только что мы создали ещё {} временных результатов из КЛБМатча'.format(n_results_created))

	# Part 4. For each result entered by user or created from KLB-result but whose race results are already loaded
	# we look for results with same lname&fname.
	# If admin has just asked to replace such result with similar one, we replace it and delete unofficial result
	context['unoff_results_in_loaded_races'] = []
	results_connected = 0
	results_deleted = 0
	n_updates_made_official = 0
	touched_runners = set()
	for unoff_result in list(models.Result.objects.filter(race__event__start_date__year__gte=year,
			race__loaded__in=models.RESULTS_SOME_OR_ALL_OFFICIAL).exclude(
			source=models.RESULT_SOURCE_DEFAULT).select_related('race__event').order_by('race__event__start_date')):
		race = unoff_result.race
		was_deleted = False
		if unoff_result.runner:
			runner = unoff_result.runner
			similar_results = race.get_official_results().filter(
				Q(lname=runner.lname, fname=runner.fname) | Q(lname=runner.fname, fname=runner.lname))
			if similar_results.count() == 1:
				result = similar_results[0]
				# if (result.result == unoff_result.result) and (result.status == unoff_result.status):
				if (abs(result.result - unoff_result.result) < 200) and (result.status == unoff_result.status):
					results_connected, results_deleted, n_updates_made_official, was_deleted = try_replace_unoff_result_by_official(
						request, unoff_result, result, touched_runners, results_connected, results_deleted, n_updates_made_official)
		else:
			similar_results = []
		if not was_deleted:
			context['unoff_results_in_loaded_races'].append({'result': unoff_result, 'similar_results': similar_results})
	report_changes_with_unoff_results(request, touched_runners, results_connected, results_deleted, n_updates_made_official)

	# Part 5. We try to connect each lost result to new result from the same race
	# models.write_log(u'{} KLB Status: Step 6'.format(datetime.datetime.now()))
	context['lost_results'], n_deleted_lost_results = attach_lost_results(year, request.user, request)
	if n_deleted_lost_results:
		messages.success(request, u'Только что мы привязали ранее потерянных привязок к результатам: {}'.format(n_deleted_lost_results))

	# Part 6. Most recent races with loaded results that weren't processed for KLBMatch
	# models.write_log(u'{} KLB Status: Step 7'.format(datetime.datetime.now()))
	context['races_for_klb'] = []
	context['MAX_RACES_FOR_KLB'] = 15
	races_for_klb = models.Race.objects.filter(
			Q(distance__distance_type=models.TYPE_MINUTES)
			| Q(distance__distance_type=models.TYPE_METERS, distance__length__gte=models_klb.get_min_distance_for_score(models.CUR_KLB_YEAR)), 
			event__start_date__year__gte=models.CUR_KLB_YEAR, # Something strange can happen near end of year if min_distance_for_score changes
			was_checked_for_klb=False,
			loaded=models.RESULTS_LOADED
		).select_related('event__city__region__country', 'event__series__city__region__country', 'distance').order_by('event__start_date')
	for race in races_for_klb:
		if (race.get_klb_status() == models.KLB_STATUS_OK) and not race.klb_result_set.filter(result=None).exists():
			context['races_for_klb'].append(race)
			if len(context['races_for_klb']) >= context['MAX_RACES_FOR_KLB']:
				break

	if year > context['oldest_year']:
		# Part 7. Preliminary protocols
		prel_ids = set(models.Document.objects.filter(document_type=models.DOC_TYPE_PRELIMINARY_PROTOCOL).values_list('event_id', flat=True))
		context['events_with_preliminary_protocols'] = models.Event.objects.filter(pk__in=prel_ids).order_by('-start_date').select_related(
			'city__region__country', 'series__city__region__country').prefetch_related(
				Prefetch('document_set', queryset=models.Document.objects.filter(document_type__in=models.DOC_PROTOCOL_TYPES)))

		# Part 8. Most recent events in RU/BY/UA with distances without results
		# if year == models.CUR_KLB_YEAR:
		# models.write_log(u'{} KLB Status: Step 8'.format(datetime.datetime.now()))
		country_ids = ('BY', 'RU', 'UA')
		distance_types = (models.TYPE_METERS, models.TYPE_MINUTES)
		today = datetime.date.today()
		WEEK_AGO = today - datetime.timedelta(days=7)
		year_from = today.year
		if today.month <= 6:
			year_from -= 1

		context['races_wo_results'] = models.Race.objects.filter(
				Q(event__city__region__country_id__in=country_ids) | Q(event__series__city__region__country_id__in=country_ids),
				Q(distance__distance_type=models.TYPE_METERS, distance__length__gte=9500) | Q(distance__distance_type=models.TYPE_MINUTES),
				# distance__distance_type__in=distance_types,
				has_no_results=False,
				event__start_date__range=(datetime.date(year_from, 1, 1), WEEK_AGO),
			).exclude(loaded=models.RESULTS_LOADED).order_by('-event__start_date', 'event_id', 'distance__distance_type', '-distance__length').select_related(
			'event__city__region__country', 'event__series__city__region__country')

		# # Part 9. Races in Russia-2016 with protocols but no results
		# event_ids_with_any_protocol = set(models.Document.objects.filter(document_type__in=models.DOC_PROTOCOL_TYPES,
		# 	event__isnull=False).values_list('event__id', flat=True))
		# context['races_with_protocol'] = models.Race.objects.filter(
		# 	Q(event__city__region__country_id='RU') | Q(event__series__city__region__country_id='RU'),
		# 	event__start_date__year=2016,
		# 	event_id__in=event_ids_with_any_protocol,
		# 	loaded=models.RESULTS_NOT_LOADED,
		# 	has_no_results=False,
		# 	).select_related('event', 'distance').order_by('-event__start_date') #[:20]

		# Part 10. Most recent events with XLS/XLSX protocols and with distances without results
		YEAR_FROM = 2015
		protocols = models.Document.objects.filter(
			models.Q_IS_XLS_FILE,
			document_type__in=models.DOC_PROTOCOL_TYPES,
			event__start_date__year__gte=YEAR_FROM,
			event__start_date__lte=WEEK_AGO,
			is_processed=False,
		)
		event_with_protocol_ids = set(protocols.values_list('event__id', flat=True))
		races_wo_results = models.Race.objects.filter(
			loaded=models.RESULTS_NOT_LOADED,
			event__start_date__year__gte=YEAR_FROM,
			event__start_date__lte=WEEK_AGO,
			has_no_results=False,
		)
		event_with_not_loaded_races_ids = set(races_wo_results.values_list('event__id', flat=True))

		context['events_with_xls_protocol'] = models.Event.objects.filter(id__in=event_with_protocol_ids & event_with_not_loaded_races_ids
			).prefetch_related(
				Prefetch('race_set', queryset=models.Race.objects.select_related('distance').order_by('distance__distance_type', '-distance__length')),
				Prefetch('document_set', queryset=models.Document.objects.filter(
					models.Q_IS_XLS_FILE, document_type__in=models.DOC_PROTOCOL_TYPES))
			).order_by('-start_date')[:context['MAX_RACES_FOR_KLB']]
	return render(request, 'editor/klb/status.html', context)

@group_required('admins')
def connect_klb_results(request):
	year = models.int_safe(request.POST.get('year', models.CUR_KLB_YEAR))
	if request.method == 'POST':
		results_connected = 0
		results_deleted = 0
		touched_active_participants = set()
		touched_inactive_participants = set()
		teams_by_race_deleting = {}
		teams_by_race_connecting = {}
		for key, val in request.POST.items():
			if key.startswith("to_connect_klb_"):
				klb_result_id = models.int_safe(key[len("to_connect_klb_"):])
				klb_result = models.Klb_result.objects.filter(pk=klb_result_id).select_related('race__event').first()
				if not klb_result:
					messages.warning(request, u'Результат в КЛБМатче с id {} не найден. Пропускаем'.format(klb_result_id))
					continue
				if klb_result.result:
					messages.warning(request, u'Результат в КЛБМатче с id {} уже привязан к результату с id {}. Пропускаем'.format(
						klb_result_id, klb_result.result.id))
					continue
				person = klb_result.klb_person
				race = klb_result.race
				event = race.event
				race_year = event.start_date.year
				participant = person.klb_participant_set.filter(match_year=race_year).first()
				team = participant.team
				if val == "delete":
					if models.is_active_klb_year(race_year):
						touched_active_participants.add(participant)
						models.log_obj_delete(request.user, event, child_object=klb_result, action_type=models.ACTION_KLB_RESULT_DELETE)
						if team:
							if race not in teams_by_race_deleting:
								teams_by_race_deleting[race] = Counter()
							teams_by_race_deleting[race][team] += 1
						klb_result.delete()
						results_deleted += 1
					else:
						messages.warning(request,
							u'КЛБ-результат бегуна {} на забеге {} не может быть удалён — тот матч уже завершён'.format(person, event))
				elif val == "connect": # So we should connect klb_result with selected result
					result_id = models.int_safe(request.POST.get("result_for_klb_{}".format(klb_result_id), 0))
					result = models.Result.objects.filter(pk=result_id).first()
					if not result:
						messages.warning(request, u'Результат с id {} не найден. Пропускаем'.format(result_id))
						continue
					runner, created = person.get_or_create_runner(request.user)
					result.runner = runner
					result.user = runner.user
					result.save()
					if models.is_active_klb_year(race_year):
						touched_active_participants.add(participant)
						if result.status == models.STATUS_FINISHED:
							klb_result.result = result
							klb_result.save()
							if result.race.distance.distance_type == models.TYPE_MINUTES:
								update_klb_result_meters(klb_result, request.user, race_year)
							else:
								update_klb_result_time(klb_result, request.user)
							if team:
								if race not in teams_by_race_connecting:
									teams_by_race_connecting[race] = Counter()
								teams_by_race_connecting[race][team] += 1
							results_connected += 1
						else: # he didn't finish, so we delete this klb_result
							models.log_obj_delete(request.user, event, child_object=klb_result, action_type=models.ACTION_KLB_RESULT_DELETE)
							if team:
								if race not in teams_by_race_deleting:
									teams_by_race_deleting[race] = Counter()
								teams_by_race_deleting[race][team] += 1
							klb_result.delete()
							results_deleted += 1
					else:
						touched_inactive_participants.add(participant)
						if result.status == models.STATUS_FINISHED:
							klb_result.result = result
							klb_result.save()
		if results_connected:
			messages.success(request, u'Привязано результатов из КЛБМатча: {}'.format(results_connected))
		if results_deleted:
			messages.success(request, u'Удалено результатов из КЛБМатча: {}'.format(results_deleted))
		if touched_active_participants:
			update_participants_score(touched_active_participants)
			messages.success(request, u'Затронуто участников активных Матчей: {}. Их результаты пересчитаны.'.format(len(touched_active_participants)))
			for comment, teams_by_race in ((u'Удаление', teams_by_race_deleting), (u'Пересчёт', teams_by_race_connecting)):
				for race, touched_teams in teams_by_race.items():
					for team in touched_teams:
						prev_score = team.score
						team.refresh_from_db()
						models.Klb_team_score_change.objects.create(
							team=team,
							race=race,
							clean_sum=team.score - team.bonus_score,
							bonus_sum=team.bonus_score,
							delta=team.score - prev_score,
							n_persons_touched=touched_teams[team],
							comment=u'{} КЛБ-результатов при замене неофициальных результатов на официальные'.format(comment),
							added_by=request.user,
						)
		if touched_inactive_participants:
			messages.success(request, u'Затронуто участников старых Матчей: {}. Их результаты не трогаем.'.format(len(touched_inactive_participants)))
	return redirect('editor:klb_status', year=year)

def try_replace_unoff_result_by_official(request, unoff_result, result, touched_runners, results_connected, results_deleted, n_updates_made_official):
	res = 0
	if result.runner and (result.runner != unoff_result.runner):
		messages.warning(request, u'Официальный результат {} ( id {}) уже привязан к бегуну {}. Пропускаем'.format(result, result.id, result.runner))
		return 0, 0, 0, False
	field_list = []
	runner = unoff_result.runner
	if runner:
		if result.runner != runner:
			result.runner = runner
			field_list.append('runner')
			if runner.user:
				result.user = runner.user
				field_list.append('user')
	else:
		messages.warning(request, u'Unofficial result with id {} has no runner connected. We tried to connect it with official result with id {}'.format(
			unoff_result.id, result.id))
		return 0, 0, 0, False
	result.save()
	event = unoff_result.race.event
	models.log_obj_create(request.user, event, models.ACTION_RESULT_UPDATE, field_list=field_list, child_object=result,
		comment=u'При замене неофициального результата на официальный')
	touched_runners.add(runner)
	results_connected += 1

	# Was this result waiting for moderation for Match?
	table_update = models.Table_update.objects.filter(model_name=models.Event.__name__, row_id=event.id, child_id=unoff_result.id,
		action_type=models.ACTION_UNOFF_RESULT_CREATE, is_verified=False, is_for_klb=True).first()
	if table_update:
		table_update.child_id = result.id
		table_update.action_type = models.ACTION_RESULT_UPDATE
		table_update.save()
		table_update.append_comment(u'сделан из неофициального результата')
		n_updates_made_official += 1

	if hasattr(unoff_result, 'result_on_strava') and not hasattr(result, 'result_on_strava'):
		result_on_strava = unoff_result.result_on_strava
		result_on_strava.result = result
		result_on_strava.save()
		models.log_obj_create(request.user, result_on_strava, models.ACTION_UPDATE, field_list=['result'],
			comment=u'При замене неофициального результата на официальный')

	models.log_obj_delete(request.user, event, child_object=unoff_result, action_type=models.ACTION_RESULT_DELETE, comment=u'Со страницы статуса матча')
	unoff_result.delete()
	results_deleted += 1
	return results_connected, results_deleted, n_updates_made_official, True

def report_changes_with_unoff_results(request, touched_runners, results_connected, results_deleted, n_updates_made_official):
	if results_connected:
		messages.success(request, u'Заменено неоф. результатов на официальные: {}'.format(results_connected))
	if results_deleted:
		messages.success(request, u'Удалено неоф. результатов: {}'.format(results_deleted))
	if touched_runners:
		for runner in touched_runners:
			update_runner_stat(runner=runner)
			if runner.user:
				update_runner_stat(user=runner.user, update_club_members=False)
		messages.success(request, u'Затронуто бегунов: {}. Их статистика пересчитана.'.format(len(touched_runners)))
	if n_updates_made_official:
		messages.success(request, u'Заявок на добавление неофициальных результатов в КЛБМатч переделано в заявки с официальными результатами: {}'.format(
			n_updates_made_official))

@group_required('admins')
def connect_unoff_results(request):
	year = models.int_safe(request.POST.get('year', models.CUR_KLB_YEAR))
	user = request.user
	if request.method == 'POST':
		results_connected = 0
		results_deleted = 0
		n_updates_made_official = 0
		touched_runners = set()
		for key, val in request.POST.items():
			if key.startswith("to_connect_unoff_"):
				unoff_result_id = models.int_safe(key[len("to_connect_unoff_"):])
				unoff_result = models.Result.objects.filter(pk=unoff_result_id).select_related('race__event').first()
				if unoff_result is None:
					messages.warning(request, u'Неофициальный результат с id {} не найден. Пропускаем'.format(unoff_result_id))
					continue
				event = unoff_result.race.event
				if val == "delete":
					if unoff_result.runner:
						touched_runners.add(unoff_result.runner)
					models.log_obj_delete(user, event, child_object=unoff_result, action_type=models.ACTION_RESULT_DELETE,
						comment=u'Со страницы статуса матча')
					unoff_result.delete()
					results_deleted += 1
				elif val == "connect": # So we should connect unoff_result with selected result
					result_id = models.int_safe(request.POST.get("result_for_unoff_{}".format(unoff_result_id), 0))
					result = models.Result.objects.filter(pk=result_id).first()
					if result is None:
						messages.warning(request, u'Официальный результат с id {} не найден. Пропускаем'.format(result_id))
						continue
					results_connected, results_deleted, n_updates_made_official, _ = try_replace_unoff_result_by_official(
						request, unoff_result, result, touched_runners,
						results_connected, results_deleted, n_updates_made_official)
		report_changes_with_unoff_results(request, touched_runners, results_connected, results_deleted, n_updates_made_official)
	return redirect('editor:klb_status', year=year)

@group_required('admins')
def klb_update_match(request, year):
	year = models.int_safe(year)
	if not models.is_active_klb_year(year):
		messages.warning(request, u'Результаты КЛБМатча–{} сейчас не могут быть пересчитаны: матч неактивен'.format(year))
	else:
		update_match(year)
		messages.success(request, u'Результаты КЛБМатча–{} успешно обновлены'.format(year))
	return redirect('results:klb_match_summary', year=year)

# Used just once. Can be used to check whether there are mistakes with results in current year
def fill_klb_result_participants(year):
	all_participants = models.Klb_participant.objects.filter(match_year=year)
	person_ids = set(all_participants.values_list('klb_person_id', flat=True))
	n_done = 0
	for klb_result in models.Klb_result.objects.filter(event_raw__start_date__year=year, klb_participant=None).select_related('klb_person', 'event_raw'):
		if klb_result.klb_person_id not in person_ids:
			print 'Klb_result {}, result {}, race {}, person {}: participant not found'.format(
				klb_result.id, klb_result.result_id, klb_result.race_id, klb_result.klb_person_id)
			continue
		person = klb_result.klb_person
		participant = all_participants.get(klb_person_id=klb_result.klb_person_id)
		event_date = klb_result.event_raw.start_date
		if year >= 2017:
			if participant.date_registered and (participant.date_registered > event_date):
				print u'{} {} был включён в команду только {}. Его результат на забеге {} не годится'.format(
					person.fname, person.lname, participant.date_registered, klb_result.event_raw)
				continue
			elif participant.date_removed and (participant.date_removed < event_date):
				print u'{} {} был исключён из команды уже {}. Его результат на забеге {} не годится'.format(
					person.fname, person.lname, participant.date_removed, klb_result.event_raw)
				continue
		klb_result.klb_participant = participant
		klb_result.save()
		n_done += 1
	print 'Done! Year:', year, '. Participants filled:', n_done

N_EMAILS_IN_GROUP = 90

@group_required('admins')
def klb_team_leaders_emails(request, year=models.CUR_KLB_YEAR):
	emails = set()
	club_ids = set(models.Klb_team.objects.filter(year=year).values_list('club_id', flat=True))
	for club in models.Club.objects.filter(pk__in=club_ids):
		emails.add(club.head_email)
		emails.add(club.speaker_email)
	user_ids = set(models.Club_editor.objects.filter(club_id__in=club_ids).values_list('user_id', flat=True))
	for user in User.objects.filter(pk__in=user_ids):
		emails.add(user.email)

	context = {}
	correct_emails = []
	incorrect_emails = []
	for email in sorted(emails):
		email = email.strip()
		if email == '':
			continue
		if models.is_email_correct(email):
			correct_emails.append(email)
		else:
			incorrect_emails.append(email)

	n_hundreds = ((len(correct_emails) - 1) // N_EMAILS_IN_GROUP) + 1
	context['correct_emails'] = []
	for i in range(n_hundreds):
		context['correct_emails'].append(u', '.join(correct_emails[i * N_EMAILS_IN_GROUP:(i + 1) * N_EMAILS_IN_GROUP]))
	context['incorrect_emails'] = u', '.join(incorrect_emails)
	context['page_title'] = u'Адреса всех имеющих права на клубы, участвующие в КЛБМатче–{}'.format(year)
	context['year'] = year
	return render(request, 'editor/klb/club_emails_by_year.html', context)

@group_required('admins')
def klb_who_did_not_pay(request, year=models.CUR_KLB_YEAR):
	year = max(2019, int(year))
	context = {}
	context['year'] = year
	context['page_title'] = u'КЛБМатч-{}: кто не заплатил за участие'.format(year)

	members = models.Klb_participant.objects.filter(match_year=year)
	team_members_not_paid = members.filter(paid_status=models.PAID_STATUS_NO).exclude(team=None)
	team_ids = set(team_members_not_paid.values_list('team_id', flat=True))

	context['n_teams_with_members'] = models.Klb_team.objects.filter(year=year, n_members__gt=0).count()
	context['n_teams_paid'] = context['n_teams_with_members'] - len(team_ids)
	context['n_teams_not_paid'] = len(team_ids)
	context['n_team_members_not_paid'] = team_members_not_paid.count()

	Q_senior_or_disabled = Q(is_senior=True) | Q(klb_person__disability_group__gt=0)
	context['n_members'] = members.count()
	context['n_members_paid'] = members.filter(paid_status=models.PAID_STATUS_FULL).count()
	context['n_seniors_paid'] = members.filter(paid_status=models.PAID_STATUS_FULL).filter(Q_senior_or_disabled).count()
	context['n_members_paid_zero'] = members.filter(paid_status=models.PAID_STATUS_FREE).count()

	context['teams'] = []
	teams_not_paid_emails = set()
	for team in models.Klb_team.objects.filter(pk__in=team_ids).prefetch_related('club__editors').annotate(Count('klb_participant')).order_by('name'):
		data = {}
		data['team'] = team
		data['participants_not_paid'] = team.klb_participant_set.filter(paid_status=models.PAID_STATUS_NO).select_related(
			'klb_person', 'added_by__user_profile').order_by('date_registered', 'klb_person__lname', 'klb_person__fname')
		data['n_seniors_not_paid'] = data['participants_not_paid'].filter(Q_senior_or_disabled).count()
		data['team_admins'] = team.club.editors.all()
		for editor in team.club.editors.all():
			teams_not_paid_emails.add(editor.email)
		context['teams'].append(data)
	context['teams_not_paid_emails'] = u', '.join(sorted(teams_not_paid_emails))

	context['individuals_not_paid'] = members.filter(paid_status=models.PAID_STATUS_NO, team=None).select_related(
		'klb_person__runner__user__user_profile').order_by('klb_person__lname', 'klb_person__fname')
	individuals_not_paid_emails = set(context['individuals_not_paid'].values_list('email', flat=True))
	context['individuals_not_paid_emails'] = u', '.join(sorted(individuals_not_paid_emails))

	context['n_individuals_paid'] = members.filter(paid_status=models.PAID_STATUS_FULL, team=None).count()
	context['n_individuals_for_free'] = members.filter(paid_status=models.PAID_STATUS_FREE, team=None).count()
	return render(request, 'editor/klb/did_not_pay.html', context)

@group_required('admins')
def klb_repeating_contact_data(request, year=models.CUR_KLB_YEAR):
	year = max(2019, int(year))
	context = {}
	context['year'] = year
	context['page_title'] = u'КЛБМатч-{}: повторяющиеся личные данные'.format(year)

	participants_by_email = {}
	participants_by_phone = {}
	for participant in models.Klb_participant.objects.filter(match_year=year).select_related('klb_person', 'team', 'added_by__user_profile').order_by(
			'added_time'):
		if participant.email:
			if participant.email not in participants_by_email:
				participants_by_email[participant.email] = []
			participants_by_email[participant.email].append(participant)
		if participant.phone_number_clean:
			if participant.phone_number_clean not in participants_by_phone:
				participants_by_phone[participant.phone_number_clean] = []
			participants_by_phone[participant.phone_number_clean].append(participant)

	context['same_emails'] = sorted((k, v) for k, v in participants_by_email.items() if (len(v) > 1))
	context['same_phones'] = sorted((k, v) for k, v in participants_by_phone.items() if (len(v) > 1))

	return render(request, 'editor/klb/repeating_contact_data.html', context)
