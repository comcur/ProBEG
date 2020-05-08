# -*- coding: utf-8 -*-
from __future__ import division, print_function
from django.core.urlresolvers import reverse
from django.db.models import F, Q, Sum
import datetime
import decimal
import re
import xlsxwriter
from collections import OrderedDict, Counter

from results import models, models_klb, results_util
from .views_mail import send_newsletter
from .views_stat import update_runner_stat
from .views_common import group_required, generate_html

def round_decimal(x):
	return decimal.Decimal(x).quantize(decimal.Decimal('.001'), rounding=decimal.ROUND_HALF_UP)

def length2bonus(length, year):
	if length < models_klb.get_min_distance_for_bonus(year):
		return 0.
	if year >= 2020:
		res = round_decimal(length / models_klb.get_bonus_score_denominator(year))
		return min(res, decimal.Decimal(models_klb.get_max_bonus_for_one_race(year)))
	else:
		res = round(length / models_klb.get_bonus_score_denominator(year), 3)
		return min(res, models_klb.get_max_bonus_for_one_race(year))

def meters2distance_raw(length):
	if length == 42195:
		return u'марафон'
	if length == 21098:
		return u'полумарафон'
	if length == 10000:
		return u'10 км'
	if length == 15000:
		return u'15 км'
	if length == 20000:
		return u'20 км'
	if length == 30000:
		return u'30 км'
	if length == 100000:
		return u'100 км'
	kilometers = length // 1000
	meters = length % 1000
	return '{}.{}'.format(kilometers, unicode(meters).zfill(3))

def roundup_centiseconds(centiseconds):
	seconds = centiseconds // 100
	if centiseconds % 100: # TODO: Remove in 2017
		seconds += 1
	return seconds

def distance2meters(distance_raw):
	distance_raw = distance_raw.strip()
	if distance_raw.endswith(u' км'):
		distance_raw = distance_raw[:-3]
	res = re.match(r'^(\d{1,4})[\. ](\d{3})$', distance_raw) # 12.345 or 12 345
	if res:
		return True, int(res.group(1)) * 1000 + int(res.group(2))
	res = re.match(r'^(\d{1,4})\.(\d{2})$', distance_raw) # 12.34
	if res:
		return True, int(res.group(1)) * 1000 + int(res.group(2)) * 10
	res = re.match(r'^(\d{1,4})\.(\d{1})$', distance_raw) # 12.3
	if res:
		return True, int(res.group(1)) * 1000 + int(res.group(2)) * 100
	res = re.match(r'^(\d{1,4})$', distance_raw) # 12
	if res:
		return True, int(res.group(1)) * 1000
	res = re.match(r'^(\d{1,4})\.(\d{4})$', distance_raw) # 12.3456
	if res:
		return True, int(res.group(1)) * 1000 + int(round(int(res.group(2)) / 10))
	return False, 0

def get_distance(distance_raw, time_seconds_raw):
	if distance_raw == u'марафон':
		return models.TYPE_METERS, 42195
	if distance_raw == u'полумарафон':
		return models.TYPE_METERS, 21098
	if distance_raw == u'21,1':
		return models.TYPE_METERS, 21098
	if (time_seconds_raw % 3600 == 0) or (time_seconds_raw == 5100):
		return models.TYPE_MINUTES, time_seconds_raw // 60
	if distance_raw == u'21':
		return models.TYPE_METERS, 21000
	if distance_raw.endswith(u' км'):
		res = models.float_safe(distance_raw[:-3])
		if res > 0:
			return models.TYPE_METERS, int(round(res * 1000))
	# if models.int_safe(distance_raw) > 0:
	# 	return models.TYPE_METERS, models.int_safe(distance_raw) * 1000
	res = models.float_safe(distance_raw)
	if res > 0:
		return models.TYPE_METERS, int(round(res * 1000))
	return None, None

def klb_result2value(klb_result): # Result must have race. Returns <is parsed?>, <result in centiseconds/meters/...>
	if klb_result.race is None:
		return False, 0
	if klb_result.race.distance.distance_type == models.TYPE_MINUTES:
		parsed, meters = distance2meters(klb_result.distance_raw)
		return parsed, meters
	else: # Distance type is regular
		return True, klb_result.time_seconds_raw * 100

# Return centiseconds for age 20-30, score, bonus score
def get_klb_score(result_year, birth_year, gender, length, centiseconds, itra_score=0, debug=False):
	if debug:
		print("length: {}, centiseconds: {}".format(length, centiseconds))
	bonus_score = length2bonus(length, result_year)

	clean_score = 0
	if itra_score and (result_year >= 2019):
		clean_score += (itra_score / 2)

	if not (models_klb.get_min_distance_for_score(result_year) <= length <= models_klb.get_max_distance_for_score(result_year)):
		return centiseconds, clean_score, bonus_score
	class_year = 2017 if (result_year <= 2017) else 2018 # There are only 2017 and 2018 for now
	coef = models.Coefficient.get_klb_coefficient(result_year, gender, result_year - birth_year, length)
	seconds = roundup_centiseconds(centiseconds)
	seconds = seconds * coef
	classes = models.Sport_class.objects.filter(year=class_year, gender=gender, length__lte=length).order_by('-length').first()
	clean_score += round(3 ** ( 2 + (classes.master_value - seconds) / (classes.third_class_value - classes.master_value) ), 3)

	return int(round(seconds)) * 100, clean_score, bonus_score

def get_bonus_score_for_klb_result(klb_result):
	result = klb_result.result
	distance, was_real_distance_used = result.race.get_distance_and_flag_for_klb()
	meters = result.result if (distance.distance_type == models.TYPE_MINUTES) else distance.length
	year = result.race.start_date.year if result.race.start_date else result.race.event.start_date.year
	return length2bonus(meters, year)

def get_klb_scores_for_result(klb_result, debug=False):
	bonus_score = get_bonus_score_for_klb_result(klb_result)
	if klb_result.race.is_multiday:
		return 0, 0, bonus_score
	year = klb_result.race.event.start_date.year
	person = klb_result.klb_person
	race = klb_result.race
	distance = race.distance
	distance_length = distance.length if (klb_result.was_real_distance_used == models.DISTANCE_FOR_KLB_FORMAL) else race.distance_real.length
	if distance.distance_type == models.TYPE_MINUTES:
		length = klb_result.result.result
		centiseconds = distance_length * 6000
	else:
		length = distance_length
		if 21097 <= length <= 21099:
			length = 21100
		elif (year <= 2017) and (42195 <= length <= 42199):
			length = 42200
		elif (year >= 2018) and (42196 <= length <= 42200):
			length = 42195
		centiseconds = klb_result.result.result
	if centiseconds == 0: # It means there is some mistake
		return 0, 0, bonus_score
	return get_klb_score(year, person.birthday.year, person.gender, length, centiseconds, itra_score=race.itra_score, debug=debug)

def get_klb_score_for_result(klb_result, debug=False):
	return get_klb_scores_for_result(klb_result, debug=debug)[1]

def fill_klb_results_for_car(): # Some strange event in Sumy, Ukraine
	race = models.Race.objects.get(pk=29635)
	team = models.Klb_team.objects.get(pk=627)
	prev_score = team.score
	n_results_changed = 0
	for klb_result in list(race.klb_result_set.all()):
		if klb_result.klb_score == 0:
			person = klb_result.klb_person
			klb_result.klb_score = get_klb_score(race.event.start_date.year, person.birthday.year, person.gender,
				length=klb_result.result.result, centiseconds=klb_result.result.time_for_car, debug=False)[1]
			klb_result.save()
			n_results_changed += 1
	team.refresh_from_db()
	models.Klb_team_score_change.objects.create(
		team=team,
		race=race,
		clean_sum=team.score - team.bonus_score,
		bonus_sum=team.bonus_score,
		delta=team.score - prev_score,
		n_persons_touched=n_results_changed,
		comment=u'Обработка странной дистанции в КЛБМатч',
		added_by=models.USER_ROBOT_CONNECTOR,
	)
	print('Done! Results changed:', n_results_changed)

def fill_klb_results_for_car_2(): # Some strange event in Sumy, Ukraine
	race = models.Race.objects.get(pk=29635)
	team = models.Klb_team.objects.get(pk=627)
	prev_score = team.score
	n_results_changed = 0
	touched_persons = set()
	for klb_result in list(race.klb_result_set.all()):
		touched_persons.add(klb_result.klb_person)
		n_results_changed += 1
	update_persons_score(year=race.event.start_date.year, persons_to_update=touched_persons)
	team.refresh_from_db()
	models.Klb_team_score_change.objects.create(
		team=team,
		race=race,
		clean_sum=team.score - team.bonus_score,
		bonus_sum=team.bonus_score,
		delta=team.score - prev_score,
		n_persons_touched=n_results_changed,
		comment=u'Обработка странной дистанции в КЛБМатч',
		added_by=models.USER_ROBOT_CONNECTOR,
	)
	print('Done! Results changed:', n_results_changed)

def fill_bonus_score(year):
	distances_not_parsed = []
	bonuses_filled = 0
	# for result in models.Klb_result.objects.filter(race__event__start_date__year=year, bonus_score=0).select_related('race__distance'):
	for result in models.Klb_result.objects.filter(race__event__start_date__year=year).select_related('race__distance'):
		race = result.race
		distance = race.distance
		if distance.distance_type == models.TYPE_MINUTES:
			parsed, length = distance2meters(result.distance_raw)
		else: # Distance type is regular
			parsed = True
			length = race.distance_real.length if (result.was_real_distance_used == models.DISTANCE_FOR_KLB_REAL) else distance.length
		if not parsed:
			distances_not_parsed.append((result.id, race.id, result.klb_person.id, result.distance_raw))
			continue
		result.bonus_score = length2bonus(length, year)
		result.save()
		bonuses_filled += 1
	print("Bonuses filled:", bonuses_filled)
	print("Not parsed distances:", distances_not_parsed)

def update_participant_score(participant, to_clean=True, to_calc_sum=True, to_update_team=False):
	year = participant.match_year
	results = participant.klb_person.klb_result_set.filter(event_raw__start_date__year=year)
	if to_clean:
		results.update(is_in_best=False, is_in_best_bonus=False)
	for result in results.order_by('-klb_score')[:models_klb.get_n_results_for_clean_score(year)]:
		result.is_in_best = True
		result.save()
	if models.is_active_klb_year(year):
		n_results_for_bonus_score = models_klb.get_n_results_for_bonus_score(year)
		if results.count() <= n_results_for_bonus_score:
			results.update(is_in_best_bonus=True)
		else:
			for result in results.order_by('-bonus_score')[:n_results_for_bonus_score]:
				result.is_in_best_bonus = True
				result.save()
		if to_calc_sum:
			participant.bonus_sum = results.filter(is_in_best_bonus=True).aggregate(Sum('bonus_score'))['bonus_score__sum']
			if participant.bonus_sum is None:
				participant.bonus_sum = 0
			participant.bonus_sum = min(participant.bonus_sum, models_klb.get_max_bonus_per_year(year))

			clean_sum = results.filter(is_in_best=True).aggregate(Sum('klb_score'))['klb_score__sum']
			if clean_sum is None:
				clean_sum = 0
			participant.score_sum = participant.bonus_sum + clean_sum
			participant.n_starts = results.count()
			participant.save()
		if to_update_team and participant.team:
			update_team_score(participant.team, to_calc_sum=True)

def update_participant_stat(participant, clean_stat=True, match_categories=None):
	year = participant.match_year
	if clean_stat:
		participant.klb_participant_stat_set.all().delete()
	klb_person = participant.klb_person
	result_ids = set(klb_person.klb_result_set.filter(event_raw__start_date__year=year).values_list('result_id', flat=True))
	results = models.Result.objects.filter(pk__in=result_ids)
	if not results.exists():
		return
	n_marathons = 0
	n_ultramarathons = 0
	lengths = []
	for result in results:
		distance = result.race.get_distance_and_flag_for_klb()[0]
		meters = result.result if (distance.distance_type == models.TYPE_MINUTES) else distance.length
		lengths.append(meters)
		if 42195 <= meters <= 42200:
			n_marathons += 1
		elif meters > 42200:
			n_ultramarathons += 1
	if match_categories is None:
		match_categories = models.Klb_match_category.get_categories_by_year(year)
	stat_types = set(match_categories.values_list('stat_type', flat=True))
	if models.KLB_STAT_LENGTH in stat_types:
		participant.create_stat(models.KLB_STAT_LENGTH, sum(lengths))
	if models.KLB_STAT_N_MARATHONS in stat_types:
		participant.create_stat(models.KLB_STAT_N_MARATHONS, n_marathons)
	if models.KLB_STAT_N_ULTRAMARATHONS in stat_types:
		participant.create_stat(models.KLB_STAT_N_ULTRAMARATHONS, n_ultramarathons)
	if models.KLB_STAT_18_BONUSES in stat_types:
		participant.create_stat(models.KLB_STAT_18_BONUSES, sum(sorted(lengths)[-18:]))
	if (klb_person.gender == models.GENDER_MALE) and (models.KLB_STAT_N_MARATHONS_AND_ULTRA_MALE in stat_types):
		participant.create_stat(models.KLB_STAT_N_MARATHONS_AND_ULTRA_MALE, n_marathons + n_ultramarathons)
	if (klb_person.gender == models.GENDER_FEMALE) and (models.KLB_STAT_N_MARATHONS_AND_ULTRA_FEMALE in stat_types):
		participant.create_stat(models.KLB_STAT_N_MARATHONS_AND_ULTRA_FEMALE, n_marathons + n_ultramarathons)

def update_team_score(team, to_clean=True, to_calc_sum=False):
	participants = team.klb_participant_set.all()
	n_runners_for_club_clean_score = models_klb.get_n_runners_for_team_clean_score(team.year)
	if to_clean:
		if participants.count() <= n_runners_for_club_clean_score:
			participants.update(is_in_best=True)
		else:
			participants.update(is_in_best=False)
			for participant in participants.exclude(n_starts=0).annotate(
					clean_score=F('score_sum')-F('bonus_sum')).order_by('-clean_score', '-n_starts')[:n_runners_for_club_clean_score]:
				participant.is_in_best = True
				participant.save()
	if models.is_active_klb_year(team.year):
		if to_calc_sum:
			clean_score = participants.filter(is_in_best=True).aggregate(clean_score=Sum(F('score_sum')-F('bonus_sum')))['clean_score']
			if clean_score is None:
				clean_score = 0
			team.bonus_score = participants.aggregate(Sum('bonus_sum'))['bonus_sum__sum']
			if team.bonus_score is None:
				team.bonus_score = 0
			team.score = clean_score + team.bonus_score
		team.n_members = participants.count()
		team.n_members_started = participants.filter(n_starts__gt=0).count()
		team.save()

def fill_age_groups(year):
	participants = models.Klb_participant.objects.filter(match_year=year, age_group=None)
	if not participants.exists():
		print("All participants already have their age group.")
		return
	models.Klb_person.objects.filter(gender=models.GENDER_UNKNOWN, gender_raw=u'м').update(gender=models.GENDER_MALE)
	models.Klb_person.objects.filter(gender=models.GENDER_UNKNOWN, gender_raw=u'ж').update(gender=models.GENDER_FEMALE)
	for age_group in models.Klb_age_group.objects.filter(match_year=year):
		participants.filter(klb_person__gender=age_group.gender,
			klb_person__birthday__year__range=(age_group.birthyear_min, age_group.birthyear_max)
		).update(age_group=age_group)

def fill_teams(year):
	for participant in models.Klb_participant.objects.filter(match_year=year, team=None).exclude(
			team_number=models.INDIVIDUAL_RUNNERS_CLUB_NUMBER):
		participant.team = models.Klb_team.objects.filter(number=participant.team_number, year=year).first()
		participant.save()

def fill_match_places(year, fill_age_places=False):
	fill_teams(year=year)
	place = 0
	place_small_teams = 0
	place_medium_teams = 0
	place_secondary_teams = 0
	models.Klb_team.objects.filter(year=year).update(place=None, place_small_teams=None, place_medium_teams=None, place_secondary_teams=None)
	small_team_limit = models_klb.get_small_team_limit(year)
	medium_team_limit = models_klb.get_medium_team_limit(year)
	for team in models.Klb_team.objects.filter(year=year).exclude(number=models.INDIVIDUAL_RUNNERS_CLUB_NUMBER).select_related('club').order_by(
			'-score', 'name'):
		team.n_members = team.klb_participant_set.count()
		place += 1
		team.place = place
		if team.n_members <= small_team_limit:
			place_small_teams += 1
			team.place_small_teams = place_small_teams
			if (year >= 2019) and team.name.startswith(team.club.name + '-') and not team.is_not_secondary_team:
				place_secondary_teams += 1
				team.place_secondary_teams = place_secondary_teams
		elif team.n_members <= medium_team_limit:
			place_medium_teams += 1
			team.place_medium_teams = place_medium_teams
		team.save()

	if fill_age_places:
		fill_age_groups(year=year)
		place = 0
		place_gender = {models.GENDER_FEMALE: 0, models.GENDER_MALE: 0}
		place_group = {}
		models.Klb_participant.objects.filter(match_year=year).update(place=None, place_gender=None, place_group=None)
		for participant in models.Klb_participant.objects.filter(match_year=year, score_sum__gt=0).select_related(
				'klb_person', 'age_group').order_by('-score_sum'):
			gender = participant.klb_person.gender
			group_id = participant.age_group.id

			place += 1
			place_gender[gender] += 1
			place_group[group_id] = place_group.get(group_id, 0) + 1

			participant.place = place
			participant.place_gender = place_gender[gender]
			participant.place_group = place_group[group_id]

			participant.save()
		models.Klb_age_group.objects.filter(match_year=year, gender=models.GENDER_UNKNOWN).update(
			n_participants=models.Klb_participant.objects.filter(match_year=year).count(),
			n_participants_started=place
		)
		for gender in [models.GENDER_FEMALE, models.GENDER_MALE]:
			models.Klb_age_group.objects.filter(match_year=year, birthyear_min=None, gender=gender).update(
				n_participants=models.Klb_participant.objects.filter(match_year=year, klb_person__gender=gender).count(),
				n_participants_started=place_gender[gender]
			)
		for group in models.Klb_age_group.objects.filter(match_year=year, birthyear_min__isnull=False):
			group.n_participants = models.Klb_participant.objects.filter(match_year=year, age_group=group).count()
			group.n_participants_started = place_group.get(group.id, 0)
			group.save()

def fill_participants_stat_places(year, match_categories=None, debug=False):
	if match_categories is None:
		match_categories = models.Klb_match_category.get_categories_by_year(year)
	# models.Klb_participant_stat.objects.filter(klb_participant__match_year=year).delete()
	# counter = 0
	# for participant in models.Klb_participant.objects.filter(match_year=year).order_by('pk'):
	# 	fill_participant_stat(participant, clean_stat=False, stat_types=stat_types)
	# 	counter += 1
	# 	if debug:
	# 		if (counter % 500) == 0:
	# 			print(counter)
	for match_category in match_categories:
		counter = 0
		cur_place = 0
		cur_value = -1
		for stat in models.Klb_participant_stat.objects.filter(klb_participant__match_year=year, stat_type=match_category.stat_type,
				value__gt=0).order_by('-value'):
			counter += 1
			if stat.value != cur_value:
				cur_place = counter
				cur_value = stat.value
			stat.place = cur_place
			stat.save()
		match_category.n_participants_started = counter
		match_category.save()
	if debug:
		print('Participants categories values are updated!')

def fill_categories_n_participants(year):
	""" Just once, for old years """
	for match_category in models.Klb_match_category.get_categories_by_year(year):
		match_category.n_participants_started = models.Klb_participant_stat.objects.filter(klb_participant__match_year=year, stat_type=match_category.stat_type,
				value__gt=0).count()
		match_category.save()
	print('Done!')

# Update everything: participants score, teams score. teams places, age group places
def update_match(year, debug=False):
	if debug:
		print('{} Started KLBMatch-{} update'.format(datetime.datetime.now(), year))
	# fill_bonus_score(year=year) - looks like it's not needed in 2018
	# TODO: add race__ in 2 places
	models.Klb_result.objects.filter(event_raw__start_date__year=year).update(is_in_best=False, is_in_best_bonus=False)
	models.Klb_participant_stat.objects.filter(klb_participant__match_year=year).delete()
	match_categories = models.Klb_match_category.get_categories_by_year(year)
	for participant in models.Klb_participant.objects.filter(match_year=year):
		update_participant_score(participant, to_clean=False)
		update_participant_stat(participant, clean_stat=False, match_categories=match_categories)
	for team in models.Klb_team.objects.filter(year=year):
		update_team_score(team, to_calc_sum=True)
	fill_match_places(year=year, fill_age_places=models.is_active_klb_year(year))
	fill_participants_stat_places(year=year, match_categories=match_categories, debug=debug)
	if debug:
		print("Year {} is updated".format(year))
		print("Match is updated!")
		print('{} Finished KLBMatch-{} update'.format(datetime.datetime.now(), year))

def update_persons_score(year, persons_to_update=[], update_runners=False, debug=False):
	if debug:
		print('{} Started persons score update'.format(datetime.datetime.now()))
	participants = models.Klb_participant.objects.filter(match_year=year, klb_person__in=persons_to_update)
	team_ids = set(participants.filter(team__isnull=False).values_list('team', flat=True))
	teams = models.Klb_team.objects.filter(pk__in=team_ids)
	for participant in participants:
		update_participant_score(participant, to_calc_sum=True)
	for team in teams:
		update_team_score(team, to_calc_sum=True)
	fill_match_places(year=year)
	if update_runners:
		for person in persons_to_update:
			if hasattr(person, 'runner'):
				update_runner_stat(runner=person.runner)
				if person.runner.user:
					update_runner_stat(user=person.runner.user, update_club_members=False)
	if debug:
		print("Persons are updated!")
		print('{} Finished persons score update'.format(datetime.datetime.now()))

def update_participants_score(participants, update_runners=False):
	persons_sets = {} # We make separate sets for every year
	persons_sets[models.CUR_KLB_YEAR] = set()
	if models.NEXT_KLB_YEAR:
		persons_sets[models.NEXT_KLB_YEAR] = set()
	for participant in participants:
		if models.is_active_klb_year(participant.match_year):
			persons_sets[participant.match_year].add(participant.klb_person)
	for year, persons in persons_sets.items():
		if persons:
			update_persons_score(year=year, persons_to_update=persons, update_runners=update_runners)

def check_wrong_results(year): # Are there any illegal results in KLBMatch?
	person_ids = set(models.Klb_result.objects.filter(race__event__start_date__year=year).values_list('klb_person_id', flat=True))
	for person in models.Klb_person.objects.filter(pk__in=person_ids).order_by('pk'):
		participants = {}
		for participant in person.klb_participant_set.all():
			participants[participant.match_year] = participant
		for klb_result in person.klb_result_set.select_related('race__event').filter(race__event__start_date__year=year):
			race = klb_result.race
			event = race.event
			race_date = race.start_date if race.start_date else event.start_date
			participant = participants.get(race_date.year)
			if participant is None:
				print(u'Вообще не участвовал в этом году: {} {} (id {}), забег {}, {} (id {})'.format(person.fname,
					person.lname, person.id, event.name, race_date, event.id))
				continue
			if participant.date_registered and (participant.date_registered > race_date):
				print(u'{} {} ({}{}) заявлен в матч {}, а забег {} ({}{}) прошёл {}'.format(
					person.fname, person.lname, models.SITE_URL, person.get_absolute_url(), participant.date_registered,
					event.name, models.SITE_URL, event.get_absolute_url(), race_date))
				continue
			if participant.date_removed and (participant.date_removed < race_date):
				print(u'{} {} ({}{}) удалён из матча {}, а забег {} ({}{}) прошёл {}'.format(
					person.fname, person.lname, models.SITE_URL, person.get_absolute_url(), participant.date_removed,
					event.name, models.SITE_URL, event.get_absolute_url(), race_date))
				continue
	print('Finished!')

def check_deleted_results():
	for year in range(2015, 2016):
		for participant in models.Klb_participant.objects.filter(match_year=year):
			person = participant.klb_person
			n_results_in_db = person.klb_result_set.filter(race__event__start_date__year=year).count()
			if n_results_in_db != participant.n_starts:
				print(year, person.id, person.runner.name(), n_results_in_db, participant.n_starts)
	print('Done!')

def check_bonuses(year, from_thousand=0):
	klb_results = models.Klb_result.objects.filter(klb_participant__match_year=year).select_related(
			'klb_person', 'race__distance').exclude(race_id__in=[41527,])
	n_thousands = klb_results.count() // 1000
	for thousand in range(from_thousand, n_thousands + 1):
	# for thousand in range(0, 1):
		print(thousand)
		for klb_result in klb_results.order_by('pk')[thousand * 1000 : (thousand + 1) * 1000]:
			new_score = get_klb_scores_for_result(klb_result)[2]
			if klb_result.bonus_score != round_decimal(new_score):
				print (klb_result.id, klb_result.bonus_score, new_score)
	print('Done!')

def match_participations_by_year(year):
	n_starts = Counter()
	for participant in models.Klb_participant.objects.filter(match_year=year):
		n_starts[participant.n_starts] += 1
	for key, val in n_starts.items():
		print(key, val)

def create_age_groups(year):
	if year < 2010:
		print('{} is too small year'.format(year))
		return
	if models.Klb_age_group.objects.filter(match_year=year).exists():
		print('Looks like groups for year {} already exist'.format(year))
		return
	prev_year_groups = models.Klb_age_group.objects.filter(match_year=year - 1)
	if not prev_year_groups.exists():
		print('Looks like groups for previous year {} do not exist'.format(year))
		return
	n_groups = 0
	for prev_year_group in prev_year_groups:
		models.Klb_age_group.objects.create(
			match_year = year,
			birthyear_min = (prev_year_group.birthyear_min + 1) if prev_year_group.birthyear_min else None,
			birthyear_max = (prev_year_group.birthyear_max + 1) if prev_year_group.birthyear_max else None,
			gender = prev_year_group.gender,
			name = prev_year_group.name,
			order_value = prev_year_group.order_value,
		)
		n_groups += 1
	print("Done! We created {} groups for Match-{} on the model of Match-{}".format(n_groups, year, year - 1))

def create_match_categories(year):
	if year < 2010:
		print('{} is too small year'.format(year))
		return
	if models.Klb_match_category.objects.filter(year=year).exists():
		print('Looks like match categories for year {} already exist'.format(year))
		return
	prev_year_groups = models.Klb_match_category.objects.filter(year=year - 1)
	if not prev_year_groups.exists():
		print('Looks like match categories for previous year {} do not exist'.format(year))
		return
	n_groups = 0
	for prev_year_group in prev_year_groups:
		models.Klb_match_category.objects.create(
			year = year,
			stat_type = prev_year_group.stat_type,
		)
		n_groups += 1
	print("Done! We created {} match categories for Match-{} on the model of Match-{}".format(n_groups, year, year - 1))

def create_all_for_new_match(year):
	if year < 2010:
		print('{} is too small year'.format(year))
		return
	if models.Klb_team.objects.filter(year=year, number=models.INDIVIDUAL_RUNNERS_CLUB_NUMBER).exists():
		print('Team for individuals already exists')
	else:
		team = models.Klb_team.objects.filter(number=models.INDIVIDUAL_RUNNERS_CLUB_NUMBER).order_by('-year').first()
		if team:
			team.id = None
			team.year = year
			team.save()
			print('Team for individuals was created!')
		else:
			print('We did not find team for individuals to clone')
	create_age_groups(year)
	create_match_categories(year)

def create_klb_coefs_for_2018():
	year_old = 2017
	year_new = 2018
	wrong_coefs = models.Sport_class.objects.filter(year=year_new)
	print('Wrong coefs to delete:', wrong_coefs.count())
	wrong_coefs.delete()
	old_coefs = models.Sport_class.objects.filter(year=year_old)
	print(year_old, "coefs total:", old_coefs.count())
	for coef in list(old_coefs.filter(length__gte=9500)):
		coef.id = None
		coef.year = 2018
		coef.save()
	print("Copied old to {}. Now {} coefs total:".format(year_new, year_old), models.Sport_class.objects.filter(year=year_old).count(),
		', {} coefs total:'.format(year_new), models.Sport_class.objects.filter(year=year_new).count())
	# In 2017 the step is 100 until 20000 and 200 after. We want to make step 10 until 25000
	new_step = 10
	classes = models.Sport_class.objects.filter(year=year_new)
	for start, stop, step in [(9500, 20000, 100), (20000, 25000, 200)]:
		for gender in (models.GENDER_FEMALE, models.GENDER_MALE):
			for length1 in range(start, stop, step):
				length2 = length1 + step
				class1 = classes.get(gender=gender, length=length1)
				class2 = classes.get(gender=gender, length=length2)
				# print('Class 1:', class1)
				# print('Class 2:', class2)
				for new_length in range(length1 + new_step, length2, new_step):
					new_class = models.Sport_class.objects.create(
						year=year_new,
						gender=gender,
						length=new_length,
						master_value=class1.master_value + int(round((class2.master_value - class1.master_value) * (new_length - length1) / (length2 - length1))),
						third_class_value=class1.third_class_value +
							int(round((class2.third_class_value - class1.third_class_value) * (new_length - length1) / (length2 - length1))),
					)
					# print('New class:', new_class)
	print('Done! {} classes now: '.format(year_new), models.Sport_class.objects.filter(year=year_new).count())

def fix_team_numbers(year):
	n_fixed = 0
	for p in models.Klb_participant.objects.filter(match_year=year):
		if p.calculate_team_number() != p.team_number:
			p.clean()
			p.save()
			n_fixed += 1
	print('Fixed numbers:', n_fixed)

def move_results_to_another_person(old_person_id, new_person_id): # Old person is a good one, new person is the one we're going to delete
	old_person = models.Klb_person.objects.get(pk=old_person_id)
	new_person = models.Klb_person.objects.get(pk=new_person_id)
	
	new_participants = new_person.klb_participant_set
	if new_participants.count() > 1:
		print('New person has too much participations:', new_participants.count())
		return
	if new_participants.count() == 0:
		print('New person has no participations')
		return
	new_participant = new_participants.first()
	year = new_participant.match_year
	if not models.is_active_klb_year(year):
		print('New participants year is not active now:', year)
		return
	if old_person.klb_participant_set.filter(match_year=year).exists():
		print('Both old and new persons participated in Match', year)
		return
	new_participant.klb_person = old_person
	new_participant.save()
	klb_results_touched = new_participant.klb_result_set.update(klb_person=old_person)
	results_touched = new_person.runner.result_set.update(runner=old_person.runner, user=old_person.runner.user)
	update_runner_stat(old_person.runner)
	print('Done! KLB results updated: {}, regular results updated: {}'.format(klb_results_touched, results_touched))

def print_different_scores():
	year = 2018
	for team in models.Klb_team.objects.filter(year=year).order_by('-score'):
		print(team.name + '\t' + unicode(team.score) + '\t',)
		for n_bonuses in (18, 15, 12, 10, 6):
			sum_bonuses = 0
			for participant in team.klb_participant_set.all():
				res = participant.klb_result_set.order_by('-bonus_score')[:n_bonuses].aggregate(Sum('bonus_score'))['bonus_score__sum']
				if res:
					sum_bonuses += res
			print(unicode(team.score - team.bonus_score + sum_bonuses) + '\t',)
		print()

def get_test_team_score(team, n_best_sport_results, bonuses_part):
	participants = team.klb_participant_set.all()
	participants_dict = {}
	for participant in participants:
		participants_dict[participant] = 0
		for result in participant.klb_result_set.order_by('-klb_score')[:n_best_sport_results]:
			participants_dict[participant] += result.klb_score
	clean_score = sum(sorted(participants_dict.values(), reverse=True)[:15])
	return clean_score, team.bonus_score / bonuses_part

def try_different_match_formulas():
	now = datetime.datetime.now()
	fname = models.XLSX_FILES_DIR + '/klb_formulas_{}.xlsx'.format(datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
	workbook = xlsxwriter.Workbook(fname)
	for n_best_sport_results in (3, 4, 5, 6):
		for bonuses_part in (1, 2, 3):
			worksheet = workbook.add_worksheet(u'{} лучших, бонусы делим на {}'.format(n_best_sport_results, bonuses_part))
			bold = workbook.add_format({'bold': True})
			number_format = workbook.add_format({'num_format': '0.000'})

			team_scores = {}
			for team in models.Klb_team.objects.filter(year=2018):
				team_scores[team] = get_test_team_score(team, n_best_sport_results, bonuses_part)

			for max_n_participants, first_row, place_field in ((100, 0, 'place'), (40, 15, 'place_small_teams'), (18, 30, 'place_medium_teams')):
				good_team_scores = [(k, v[0], v[1], v[0] + v[1]) for k, v in team_scores.items() if k.n_members <= max_n_participants]

				first_teams = sorted(good_team_scores, key= lambda x: -x[3])[:10]

				row = first_row

				worksheet.write(row, 0, u'Место', bold)
				worksheet.write(row, 1, u'ID', bold)
				worksheet.write(row, 2, u'Команда', bold)
				worksheet.write(row, 3, u'Участников', bold)
				worksheet.write(row, 4, u'Спортивные', bold)
				worksheet.write(row, 5, u'Бонусы', bold)
				worksheet.write(row, 6, u'Сумма', bold)
				worksheet.write(row, 7, u'Текущее место', bold)
				worksheet.write(row, 8, u'Спортивные', bold)
				worksheet.write(row, 9, u'Бонусы', bold)
				worksheet.write(row, 10, u'Сумма', bold)

				# worksheet.set_column(0, 1, 3.29)
				# worksheet.set_column(2, 3, 17.29)
				# worksheet.set_column(4, 5, 31.86)
				# worksheet.set_column(6, 6, 40)
				# worksheet.set_column(7, 8, 10)
				# worksheet.set_column(9, 9, 11.57)
				# worksheet.set_column(10, 10, 9.29)

				# Iterate over the data and write it out row by row.
				for i, data in enumerate(first_teams):
					team = data[0]
					row += 1
					worksheet.write(row, 0, i + 1)
					worksheet.write(row, 1, team.id)
					worksheet.write(row, 2, team.name)
					worksheet.write(row, 3, team.n_members)
					worksheet.write(row, 4, data[1], number_format)
					worksheet.write(row, 5, data[2], number_format)
					worksheet.write(row, 6, data[3], number_format)
					worksheet.write(row, 7, getattr(team, place_field))
					worksheet.write(row, 8, team.score - team.bonus_score, number_format)
					worksheet.write(row, 9, team.bonus_score, number_format)
					worksheet.write(row, 10, team.score, number_format)

	workbook.close()
	return fname

@group_required('admins')
def get_test_formulas_file(request):
	fname = try_different_match_formulas()
	response = FileResponse(open(fname, 'rb'), content_type='application/vnd.ms-excel')
	response['Content-Disposition'] = 'attachment; filename="{}"'.format(fname.split('/')[-1])
	return response

def get_best_participants_dict(participants, year):
	participants_cur_year = participants.filter(match_year=year)
	participants_male = participants_cur_year.filter(klb_person__gender=models.GENDER_MALE)
	participants_female = participants_cur_year.filter(klb_person__gender=models.GENDER_FEMALE)
	data = {}
	data['n_participants'] = participants_cur_year.count()
	data['n_participants_male'] = participants_male.count()
	data['n_participants_female'] = participants_female.count()
	data['best_male'] = participants_male.order_by('place').first()
	data['best_female'] = participants_female.order_by('place').first()
	data['n_participants_prev_year'] = participants.filter(match_year=year - 1).count()
	return data

def generate_klb_winners_by_regions(year):
	context = {}
	context['year'] = year
	context['page_title'] = u'КЛБМатч-{}: Итоги по регионам и странам'.format(year)
	context['n_results_for_bonus_score'] = models_klb.get_n_results_for_bonus_score(year)
	context['main_countries'] = OrderedDict()
	COUNTRIES_WITH_REGIONS = ('RU', 'UA', 'BY')
	all_participants = models.Klb_participant.objects.filter(n_starts__gt=0).select_related('klb_person__runner__user__user_profile')
	for country_id in COUNTRIES_WITH_REGIONS:
		country_data = OrderedDict()
		country = models.Country.objects.get(pk=country_id)
		for region in country.region_set.filter(active=True).order_by('name'):
			country_data[region] = get_best_participants_dict(all_participants.filter(klb_person__city__region_id=region.id), year)

		total = get_best_participants_dict(all_participants.filter(klb_person__city__region__country_id=country_id), year)
		context['main_countries'][country] = {'regions': country_data, 'total': total}

	context['other_countries'] = OrderedDict()
	other_countries_ids = set(all_participants.filter(match_year=year).exclude(klb_person__city__region__country_id__in=COUNTRIES_WITH_REGIONS).values_list(
		'klb_person__city__region__country_id', flat=True))
	for country in models.Country.objects.filter(pk__in=other_countries_ids).order_by('name'):
		context['other_countries'][country] = get_best_participants_dict(all_participants.filter(klb_person__city__region__country_id=country.id), year)

	context['districts'] = OrderedDict()
	context['clubs_by_districts'] = OrderedDict()
	for district in models.District.objects.filter(country_id='RU').order_by('name'):
		context['districts'][district] = get_best_participants_dict(all_participants.filter(klb_person__city__region__district_id=district.id), year)
		context['clubs_by_districts'][district] = models.Klb_team.objects.filter(year=year, club__city__region__district_id=district.id).select_related(
			'club__city__region').order_by('place')
	generate_html('generators/klb_winners_by_region.html', context, '{}.html'.format(year),
		dir='results/templates/klb/winners_by_region')

def generate_reg_activity():
	dates = []
	years = list(range(2017, 2020))
	first_days = [datetime.date(year - 1, 12, 1) for year in years]
	gap = 5
	dates = []
	data = []
	last_day = datetime.date(years[0], 4, 1)
	while first_days[0] <= last_day:
		dates.append(first_days[0])
		print(first_days[0], end=" ")
		row = []
		for i in range(len(years)):
			row.append(models.Klb_participant.objects.filter(match_year=years[i], date_registered__gte=first_days[i],
				date_registered__lte=first_days[i] + datetime.timedelta(days=gap - 1)).count())
			first_days[i] += datetime.timedelta(days=gap)
		data.append(row)
		print(row)

def print_teams_without_captains(year=models.CUR_KLB_YEAR):
	club_in_match_ids = set(models.Klb_team.objects.filter(year=year).values_list('club_id', flat=True))
	clubs_with_captain_ids = set(models.Club_editor.objects.values_list('club_id', flat=True))
	for club_id in club_in_match_ids - clubs_with_captain_ids:
		club = models.Club.objects.get(pk=club_id)
		print(club.id, club.name)

def send_letters_to_not_paid_participants(year=models.CUR_KLB_YEAR, test_mode=True):
	participants = models.Klb_participant.objects.filter(match_year=year, team=None, paid_status=models.PAID_STATUS_NO).select_related(
			'klb_person__runner__user__user_profile').order_by('-score_sum')
	print('Participants who did not pay:', participants.count())
	n_sent = 0
	n_errors = 0
	for participant in participants:
		runner = participant.klb_person.runner
		user = runner.user
		if user is None:
			models.send_panic_email(
				'Individual KLB participant has no user',
				u'Problem occured with klb_participant {}: there is no associated user.'.format(participant.id)
			)
			continue
		if not hasattr(user, 'user_profile'):
			models.send_panic_email(
				'Individual KLB participant has no user_profile',
				u'Problem occured with klb_participant {}, user {}: there is no associated user_profile.'.format(participant.id, user.id)
			)
			continue
		context = {}
		context['test_mode'] = test_mode
		context['participant'] = participant
		context['senior_age'] = results_util.SENIOR_AGE_MALE if (participant.klb_person.gender == results_util.GENDER_MALE) \
			else results_util.SENIOR_AGE_FEMALE
		context['regulations_link'] = models_klb.get_regulations_link(year)
		context['participation_price'] = models_klb.get_participation_price(year)
		context['date_registered'] = models.date2str(participant.date_registered, with_nbsp=False)
		context['registration_deadline'] = u'1 декабря'
		print(u'{} {} {} {}'.format(runner.get_name_and_id(), user.id, user.get_full_name(), user.email))
		result = send_newsletter(user, models.USER_ADMIN, 'klb/individual_not_paid', u'КЛБМатч — оплата участия',
			target='info@probeg.org' if test_mode else '',
			cc='' if test_mode else 'info@probeg.org',
			create_table_update=True, context=context)
		if result['success']:
			n_sent += 1
		else:
			print('Could not send message to participant {}, user {}: {}'.format(participant.id, user.id, result['error']))
			n_errors += 1
	print('Done! Messages sent: {}, errors: {}'.format(n_sent, n_errors))

def send_letters_for_not_paid_teams(year=models.CUR_KLB_YEAR, test_mode=True):
	non_paid_team_ids = set(models.Klb_participant.objects.filter(match_year=year, team__isnull=False, paid_status=models.PAID_STATUS_NO).values_list(
		'team_id', flat=True))
	print('Teams who did not pay:', len(non_paid_team_ids))
	n_captains = 0
	n_sent = 0
	n_errors = 0
	for i, team in enumerate(models.Klb_team.objects.filter(pk__in=non_paid_team_ids).select_related('club').order_by('pk')):
	# for i, team in enumerate(models.Klb_team.objects.filter(pk=966).select_related('club').order_by('pk')):
		context = {}
		context['team'] = team
		context['test_mode'] = test_mode
		context['n_not_paid'] = team.klb_participant_set.filter(paid_status=models.PAID_STATUS_NO).count()
		context['senior_age_male'] = results_util.SENIOR_AGE_MALE
		context['senior_age_female'] = results_util.SENIOR_AGE_FEMALE
		context['regulations_link'] = models_klb.get_regulations_link(year)
		context['participation_price'] = models_klb.get_participation_price(year)
		context['registration_deadline'] = u'14 января'
		context['date_of_deletion'] = u'15 января'
		captains = team.club.editors.order_by('pk')
		if not captains.exists():
			print(u'Team {} (id {}) has no captains!'.format(team.name, team.id))
		for captain in captains:
			print(u'{} {} {} {} {} {}'.format(i, team.id, team.name, captain.id, captain.get_full_name(), captain.email))
			result = send_newsletter(captain, models.USER_ADMIN, 'klb/team_not_paid',
				u'КЛБМатч — оплата участия команды «{}»'.format(team.name),
				target='info@probeg.org' if test_mode else '',
				cc='' if test_mode else 'info@probeg.org',
				create_table_update=not test_mode, context=context)
			if result['success']:
				n_sent += 1
			else:
				print(u'Could not send message to team {}, user {}: {}'.format(team.id, captain.id, result['error']))
				n_errors += 1
	print('Done! Messages sent: {}, errors: {}'.format(n_sent, n_errors))

def teams_with_professionals(year=2019):
	i = 1
	for klb_result in models.Klb_result.objects.filter(klb_participant__match_year=year, klb_score__gte=10, is_in_best=True,
			klb_participant__is_in_best=True).select_related(
			'klb_participant__team', 'klb_person__runner').order_by('klb_participant__team_id'):
		print(i, klb_result.klb_participant.team.name if klb_result.klb_participant.team else '',
			klb_result.klb_score, klb_result.klb_person.get_full_name_with_birthday())
		i += 1

def send_letters_to_unpaid_team_participants(test_mode=True):
	today = datetime.date.today()
	first_legal_reg_date = datetime.date(today.year, today.month, 1)
	clubs_with_captain_ids = set(models.Club_editor.objects.values_list('club_id', flat=True))
	participants = models.Klb_participant.objects.filter(
		Q(date_registered=None) | Q(date_registered__lt=first_legal_reg_date),
		is_senior=False, klb_person__disability_group=0,
		match_year=models.CUR_KLB_YEAR, team__isnull=False, team__club_id__in=clubs_with_captain_ids,
		paid_status=models.PAID_STATUS_NO).exclude(email='').select_related(
		'klb_person__runner__user__user_profile', 'klb_person__runner__city__region__country', 'team').order_by('pk')
	print('Number of unpaid team participants with emails: {}'.format(participants.count()))
	n_sent = 0
	n_errors = 0
	for participant in participants:
	# for i in range(13, 14):
	# 	participant = participants[i * 10]
		context = {}
		context['team'] = participant.team
		context['test_mode'] = test_mode
		context['page_title'] = u'КЛБМатч — оплата участия'
		context['participant'] = participant
		context['club_editors'] = participant.team.club.editors
		context['n_other_not_paid'] = participant.team.klb_participant_set.filter(paid_status=models.PAID_STATUS_NO).count() - 1
		context['registration_deadline'] = u'14 декабря'
		result = send_newsletter(None, models.USER_ADMIN, 'klb/team_member_not_paid', u'КЛБМатч — оплата участия',
			# target='alexey.chernov@gmail.com' if test_mode else participant.email,
			target='info@probeg.org' if test_mode else participant.email,
			cc='' if test_mode else 'info@probeg.org',
			create_table_update=not test_mode,
			context=context, runner=participant.klb_person.runner)
		if result['success']:
			print(u'participant {} (id {}), {}, team {}'.format(participant.klb_person.runner.name(), participant.id, participant.email,
				participant.team.name))
			n_sent += 1
		else:
			print(u'ERROR participant {} (id {}), {}: {}'.format(participant.klb_person.runner.name(), participant.id, participant.email,
				result['error']))
			n_errors += 1
	print('Done! Messages sent: {}, errors: {}'.format(n_sent, n_errors))

def get_participants_for_team_or_year(team, year=None):
	if team:
		return team.klb_participant_set.all()
	# Otherwise, return individual participants for given year
	return models.Klb_participant.objects.filter(team=None, match_year=year)

def create_fake_payment_for_seniors(first_legal_reg_date, team, year):
	unpaid_seniors = get_participants_for_team_or_year(team, year).filter(
		Q(date_registered=None) | Q(date_registered__lt=first_legal_reg_date),
		Q(is_senior=True) | Q(klb_person__disability_group__gt=0),
		paid_status=models.PAID_STATUS_NO).select_related('klb_person__runner').order_by(
		'klb_person__runner__lname', 'klb_person__runner__fname')
	n_unpaid_seniors = unpaid_seniors.count()
	if n_unpaid_seniors:
		payment = models.Payment_moneta.objects.create(
			amount=0,
			is_dummy=True,
			is_paid=True,
			user=models.USER_ROBOT_CONNECTOR,
			description=u'Автоматический платёж при удалении неоплаченных участников команды {}'.format(
				team.name if team else u'«Индивидуальные участники»'),
		)
		payment.transaction_id = models.PAYMENT_DUMMY_PREFIX + unicode(payment.id)
		payment.save()
		message = u'Неоплаченные пенсионеры и инвалиды помечены как участвующие бесплатно:\n'
		for i, participant in enumerate(unpaid_seniors):
			participant.payment = payment
			participant.paid_status = models.PAID_STATUS_FREE
			participant.save()
			models.log_obj_create(models.USER_ROBOT_CONNECTOR, participant.klb_person, models.ACTION_KLB_PARTICIPANT_UPDATE,
				child_object=participant, field_list=['paid_status', 'payment'],
				comment=u'Платёж {}'.format(payment.id), verified_by=models.USER_ROBOT_CONNECTOR)
			message += u'{}. {} {}{}\n'.format(i + 1, participant.klb_person.runner.name(), models.SITE_URL,
				participant.klb_person.get_absolute_url())
		message += u'\nСоздан фиктивный платёж для бесплатного участия неоплаченных пенсионеров и инвалидов: {}{}\n\n'.format(
			models.SITE_URL, payment.get_absolute_url())
	else:
		message = u'Неоплаченных пенсионеров и инвалидов в команде не было.\n\n'
	return message

def delete_unpaid_participants_for_team(first_legal_reg_date, team, test_mode, year=None):
	participants_to_delete = get_participants_for_team_or_year(team, year).filter(
		Q(date_registered=None) | Q(date_registered__lt=first_legal_reg_date),
		is_senior=False, klb_person__disability_group=0,
		paid_status=models.PAID_STATUS_NO).select_related('klb_person__runner').order_by(
		'klb_person__runner__lname', 'klb_person__runner__fname')
	if team:
		message = (u'Сейчас мы попробуем удалить всех участников команды «{}» {} года {}{} , заявленных до {},'
					+ u' которые не могут участвовать бесплатно, и их результаты.\n\n').format(
			team.name, team.year, models.SITE_URL, team.get_absolute_url(), first_legal_reg_date)
	else:
		message = (u'Сейчас мы попробуем удалить всех индивидуальных участников {} года {}{} , заявленных до {},'
					+ u' которые не могут участвовать бесплатно, и их результаты.\n\n').format(
			year, models.SITE_URL, reverse('results:klb_match_summary', kwargs={'year': year}), first_legal_reg_date)
	if test_mode:
		message += u'Это — тестовый запуск, на самом деле ничего не удаляем!\n\n'
	message += u'Участники:\n'
	for i, participant in enumerate(participants_to_delete):
		person = participant.klb_person
		message += u'{}. {} {} {}{} , заявлен {}\n'.format(i + 1, person.fname, person.lname, models.SITE_URL, person.get_absolute_url(),
			participant.date_registered)

	participants_with_results = participants_to_delete.filter(n_starts__gt=0)
	n_participants_with_results = participants_with_results.count()
	results_to_delete = []
	if n_participants_with_results > 0:
		message += u'\nИх результаты:\n\n'
		message += u'№;id участника;имя;фамилия;id старта;дата старта;название;дистанция;id результата;результат;'
		message += u'спортивные очки;бонусы;дата добавления\n'
		for participant in participants_with_results:
			runner = participant.klb_person.runner
			for klb_result in participant.klb_result_set.all().select_related('race__event', 'race__distance', 'result').order_by(
					'race__event__start_date'):
				race = klb_result.race
				results_to_delete.append(klb_result)
				message += u';'.join(unicode(x) for x in
						[len(results_to_delete), participant.klb_person_id, runner.fname, runner.lname, race.id, race.event.date(with_nobr=False),
						race.event.name, race.distance, klb_result.result_id, klb_result.result, klb_result.klb_score,
						klb_result.bonus_score, klb_result.last_update]
					)
				message += u'\n'
	message += u'\nВсего участников: {}, результатов: {}.\n\n'.format(participants_to_delete.count(), len(results_to_delete))
	if not test_mode:
		to_delete_participants = True
		if results_to_delete:
			message += u'Пытаемся удалить результаты... '
			n_deleted = 0
			try:
				for klb_result in results_to_delete:
					models.log_obj_delete(models.USER_ROBOT_CONNECTOR, klb_result.race.event, child_object=klb_result,
						action_type=models.ACTION_KLB_RESULT_DELETE, comment=u'При удалении неоплаченных участников')
					klb_result.delete()
					n_deleted += 1
				message += u'Получилось! Удалено: {}.\n'.format(n_deleted)
			except Exception as e:
				to_delete_participants = False
				message += u'Не получилось; удалилось только {}. Участников не удаляем. Ошибка: {}\n\n'.format(n_deleted, repr(e))
		if to_delete_participants:
			message += u'Пытаемся удалить неоплаченных участников... '
			try:
				for participant in participants_to_delete:
					models.log_klb_participant_delete(models.USER_ROBOT_CONNECTOR, participant, comment=u'При удалении неоплаченных участников')
				participants_to_delete.delete()
				message += u'Получилось!\n'
				if team:
					update_team_score(team, to_calc_sum=True)
					message += u'Очки команды пересчитаны.\n\n'
				message += create_fake_payment_for_seniors(first_legal_reg_date, team, year)
			except Exception as e:
				message += u'Возникла ошибка: {}\n\n'.format(repr(e))

	message += u'\n\nВаш робот'
	if team:
		message_title = u'КЛБМатч-{}: удаление неоплаченных участников из команды {}'.format(team.year, team.name)
	else:
		message_title = u'КЛБМатч-{}: удаление неоплаченных индивидуальных участников'.format(year)
	if test_mode:
		message_title += u' (тест)'
	message_from_site = models.Message_from_site.objects.create(
		sender_name=models.USER_ROBOT_CONNECTOR.get_full_name(),
		sender_email=models.INFO_MAIL_HEADER,
		target_email=models.INFO_MAIL,
		# target_email='alexey.chernov@gmail.com',
		title=message_title,
		body=message,
	)
	message_from_site.try_send(attach_file=False)

def delete_unpaid_participants(year, test_mode=True):
	if year < models.CUR_KLB_YEAR:
		print('Year {} is too early to delete participants. Exiting'.format(year))
		return
	today = datetime.date.today()
	first_legal_reg_date = datetime.date(today.year + 1, today.month, 1)
	team_participants_not_paid = models.Klb_participant.objects.filter(
		Q(date_registered=None) | Q(date_registered__lt=first_legal_reg_date),
		match_year=year, paid_status=models.PAID_STATUS_NO)
	# if today.month not in (1, 12): # We touch seniors and handicapped only in the end of the year
	# 	team_participants_not_paid = team_participants_not_paid.filter(is_senior=False, klb_person__disability_group=0)
	team_ids = set(team_participants_not_paid.values_list('team_id', flat=True))
	print('Teams found: {}'.format(len(team_ids)))
	n_teams_done = 0
	for team_id in sorted(team_ids)[:5]:
		if team_id:
			delete_unpaid_participants_for_team(first_legal_reg_date, models.Klb_team.objects.get(pk=team_id), test_mode=test_mode)
		else: # Individual participants
			delete_unpaid_participants_for_team(first_legal_reg_date, None, test_mode=test_mode, year=year)
		n_teams_done += 1
	print('Done! teams processed: {}'.format(n_teams_done))
