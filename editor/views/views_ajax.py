# -*- coding: utf-8 -*-
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.db.models import Q
import json

from results import models, results_util
from .views_common import group_required

def cities_list(request):
	cities = models.City.objects
	ok_to_return = False

	# Default return list
	# results = OrderedDict()
	results = []
	if request.method == "GET":
		try:
			if 'region' in request.GET:
				region_id = request.GET['region']
				cities = cities.filter(region__id=region_id)
				ok_to_return = True
			if 'country' in request.GET:
				country_id = request.GET['country']
				cities = cities.filter(region__country__id=country_id)
				ok_to_return = True
			if 'cur_city' in request.GET:
				cur_city_id = request.GET['cur_city']
				cities = cities.exclude(pk=cur_city_id)
			if ok_to_return:
				for city in cities.order_by('name'):
					# results[city.id] = city.name_full() if request.GET.has_key('full') else city.name
					results.append({'key': city.id, 'value': (city.name_full() if request.GET.has_key('full') else city.name)})
		except:
			pass
	res = json.dumps({'cities': results})
	return HttpResponse(res, content_type='application/json')

def get_participants_list_for_json(participants, include_year=False):
	results = []
	for participant in participants.order_by('klb_person__lname', 'klb_person__fname')[:MAX_ENTRIES]:
		person = participant.klb_person
		team_name = participant.team.name if participant.team else u'индив. участник'
		str_year = u', {} год'.format(participant.match_year) if include_year else ''
		results.append({
			'id': participant.id,
			'text': u'{} {} {} ({}, {}{})'.format(person.lname, person.fname, person.midname, team_name,
				person.birthday.strftime('%d.%m.%Y'), str_year),
		})
	return results

MAX_ENTRIES = 20
MIN_QUERY_LENGTH = 3
def participants_list(request, race_id):
	results = []
	query = request.GET.get('query', '')
	words = query.split()
	if (len(query) >= MIN_QUERY_LENGTH) and words:
		race = get_object_or_404(models.Race, pk=race_id)
		race_date = race.start_date if race.start_date else race.event.start_date
		participants = models.Klb_participant.objects.select_related('klb_person').filter(
			Q(date_registered=None) | Q(date_registered__lte=race_date),
			Q(date_removed=None) | Q(date_removed__gte=race_date),
			match_year=race_date.year,
			klb_person__lname__istartswith=words[0],
		)
		if len(words) >= 2:
			participants = participants.filter(klb_person__fname__istartswith=words[1])
			if len(words) >= 3:
				participants = participants.filter(klb_person__midname__istartswith=words[2])
		results = get_participants_list_for_json(participants)
	res = json.dumps(results)
	return HttpResponse(res, content_type='application/json')

def unpaid_participants_list(request):
	results = []
	query = request.GET.get('query', '')
	words = query.split()
	if (len(query) >= MIN_QUERY_LENGTH) and words:
		years = [models.CUR_KLB_YEAR]
		if models.NEXT_KLB_YEAR and models.NEXT_KLB_YEAR_AVAILABLE_FOR_ALL:
			years.append(models.NEXT_KLB_YEAR)
		participants = models.Klb_participant.objects.select_related('klb_person').filter(match_year__in=years, paid_status=models.PAID_STATUS_NO,
			klb_person__lname__istartswith=words[0])
		if len(words) >= 2:
			participants = participants.filter(klb_person__fname__istartswith=words[1])
			if len(words) >= 3:
				participants = participants.filter(klb_person__midname__istartswith=words[2])
		results = get_participants_list_for_json(participants, include_year=True)
	res = json.dumps(results)
	return HttpResponse(res, content_type='application/json')

# runners can be a queryset on Runner or Klb_person
def filter_by_name(runners, query):
	words = query.split()
	if len(words) >= 3:
		return runners.filter(lname__istartswith=words[0], fname__istartswith=words[1], midname__istartswith=words[2])
	elif len(words) == 2:
		return runners.filter(lname__istartswith=words[0], fname__istartswith=words[1])
	else:
		return runners.filter(lname__istartswith=words[0])

@login_required
def runners_list(request, runner_id=None, race_id=None):
	results = []
	user = request.user
	query = request.GET.get('query', '').strip()
	runners = models.Runner.objects.select_related('city__region__country')
	if len(query) >= MIN_QUERY_LENGTH:
		if models.is_admin(user):
			query_as_number = results_util.int_safe(query)
			if query_as_number:
				runners = runners.filter(pk=query_as_number)
			else:
				runners = filter_by_name(runners, query)

			if runner_id: # When merging runner with id=runner_id with other runner
				runners = runners.exclude(pk=runner_id)
			elif race_id: # When choosing only runners without results on current race
				race = models.Race.objects.filter(pk=race_id).first()
				if race:
					runners_in_race = set(race.result_set.values_list('runner_id', flat=True))
					runners = runners.exclude(pk__in=runners_in_race)
		elif user.club_editor_set.exists(): # When club manager wants to enter club members' unofficial results
			runners = filter_by_name(runners.filter(pk__in=models.get_runner_ids_for_user(user)), query)
		for runner in runners.order_by('lname', 'fname', 'birthday')[:(2 * MAX_ENTRIES)]:
			results.append({
				'id': runner.id,
				'text': runner.get_name_for_ajax_select(),
			})
	res = json.dumps(results)
	return HttpResponse(res, content_type='application/json')

@group_required('admins')
def persons_list(request, person_id=None):
	results = []
	user = request.user
	query = request.GET.get('query', '').strip()
	persons = models.Klb_person.objects.select_related('runner__city__region__country')
	if len(query) >= MIN_QUERY_LENGTH:
		persons = filter_by_name(persons, query)
		if person_id: # When merging person with id=person_id with other person
			persons = persons.exclude(pk=person_id)
		for person in persons.order_by('lname', 'fname', 'birthday')[:MAX_ENTRIES]:
			results.append({
				'id': person.id,
				'text': person.runner.get_name_for_ajax_select(),
			})
	res = json.dumps(results)
	return HttpResponse(res, content_type='application/json')

@login_required
def cities_list_by_name(request):
	results = []
	query = request.GET.get('query', '').strip()
	if len(query) >= MIN_QUERY_LENGTH:
		for city in models.City.objects.filter(name__istartswith=query).select_related('region__country').order_by('name')[:MAX_ENTRIES]:
			results.append({
				'id': city.id,
				'text': city.nameWithCountry(with_nbsp=False)
			})
	res = json.dumps(results)
	return HttpResponse(res, content_type='application/json')

@group_required("admins")
def organizers_list(request, organizer_id=None):
	results = []
	user = request.user
	query = request.GET.get('query', '').strip()
	if len(query) >= MIN_QUERY_LENGTH:
		organizers = models.Organizer.objects.filter(name__istartswith=query)
		if organizer_id: # When merging organizer with id=organizer_id with other organizer
			organizers = organizers.exclude(pk=organizer_id)
		for organizer in organizers.order_by('name')[:MAX_ENTRIES]:
			results.append({
				'id': organizer.id,
				'text': organizer.name,
			})
	res = json.dumps(results)
	return HttpResponse(res, content_type='application/json')

def get_series_dict_for_select(series):
	return {'id': series.id, 'text': series.name}

def series_list(request, organizer_id=None):
	results = []
	query = request.GET.get('query', '').strip()
	if len(query) >= MIN_QUERY_LENGTH:
		all_good_series = models.Series.objects.all()
		if organizer_id:
			all_good_series = all_good_series.exclude(organizer_id=organizer_id)
		series_id = models.int_safe(query)
		if series_id > 0:
			series = all_good_series.filter(pk=series_id).first()
			if series:
				results.append(get_series_dict_for_select(series))
		for series in all_good_series.filter(name__icontains=query).order_by('name')[:MAX_ENTRIES]:
			results.append(get_series_dict_for_select(series))
	return HttpResponse(json.dumps(results), content_type='application/json')

def race_result_list(request, race_id):
	race = get_object_or_404(models.Race, pk=race_id)
	res = []
	query = request.GET.get('query', '')
	words = query.split()
	if (len(query) >= MIN_QUERY_LENGTH) and (len(words) > 0):
		results = race.result_set.filter(source=models.RESULT_SOURCE_DEFAULT)
		if len(words) >= 3:
			results = results.filter(lname__istartswith=words[0], fname__istartswith=words[1], midname__istartswith=words[2])
		elif len(words) == 2:
			results = results.filter(lname__istartswith=words[0], fname__istartswith=words[1])
		else:
			results = results.filter(lname__istartswith=words[0])
		results = results.order_by('lname', 'fname')[:MAX_ENTRIES]
		for result in results:
			res.append({
				'id': result.id,
				'text': u'{} {} ({})'.format(result.lname, result.fname, unicode(result)),
			})
	res = json.dumps(res)
	return HttpResponse(res, content_type='application/json')
