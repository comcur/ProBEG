# -*- coding: utf-8 -*-
from __future__ import division
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.forms import formset_factory
from django.contrib import messages
from django.db.models import Q

from collections import Counter
import math

from results import models, models_klb
from results.views.views_common import user_edit_vars
from editor.forms import KlbResultForm
from .views_common import group_required
from .views_klb import create_klb_result
from .views_klb_stat import update_persons_score
from .views_stat import update_runner_stat

COMPARED_BY_NOTHING = 0
COMPARED_BY_AGE = 1
COMPARED_BY_BIRTHYEAR = 2
COMPARED_BY_BIRTHDAY = 3

COMPARED_TYPES = (
	(COMPARED_BY_NOTHING, u'только&nbsp;имя'),
	(COMPARED_BY_AGE, u'примерный возраст'),
	(COMPARED_BY_BIRTHYEAR, u'год рождения'),
	(COMPARED_BY_BIRTHDAY, u'день рождения'),
)

MIN_RESULTS_TO_USE_PAGES = 501
RESULTS_PER_PAGE = 500

def get_pages_number(n_results):
	return int(math.ceil(n_results / RESULTS_PER_PAGE))

def check_distance_and_result(request, distance, person, result, year):
	if (distance.distance_type == models.TYPE_MINUTES) and (result.result < models_klb.get_min_distance_for_bonus(year)):
		messages.warning(request, u'Результат бегуна {} {}, {}, слишком мал для КЛБМатча. Пропускаем'.format(person.fname, person.lname, result))
		return False
	return True

def check_results_with_same_time(request, race, event, person, result):
	if person.klb_result_set.filter(race=race).exists(): 
		messages.warning(request,
			u'У участника {} {} (id {}) уже есть учтенный в Матче результат на этом старте. Не учитываем в Матче'.format(
			result.fname, result.lname, person.id))
		return False
	if person.klb_result_set.filter(race__event=event, race__start_date=race.start_date, race__start_time=race.start_time).exists():
		messages.warning(request,
			u'У участника {} {} (id {}) уже есть учтенный в Матче результат в этом забеге с тем же временем старта. Не учитываем в Матче'.format(
			result.fname, result.lname, person.id))
		return False
	return True

def get_runner_ids_for_result(result):
	result_name_condition = Q(lname=result.lname, fname=result.fname) | Q(lname=result.fname, fname=result.lname)
	runners_for_result = models.Runner.objects.filter(result_name_condition)
	extra_names_for_result = models.Extra_name.objects.filter(result_name_condition)
	if result.midname:
		runners_for_result = runners_for_result.filter(midname__in=('', result.midname))
		extra_names_for_result = extra_names_for_result.filter(midname__in=('', result.midname))

	return set(runners_for_result.values_list('id', flat=True)) | set(extra_names_for_result.values_list('runner_id', flat=True))

@group_required('admins')
def klb_race_details(request, race_id, page=0):
	race = get_object_or_404(models.Race, pk=race_id)
	event = race.event
	year = event.start_date.year
	if not models.is_active_klb_year(year):
		messages.warning(request, u'Вы уже не можете изменять результаты забега {} года. Тот матч давно в прошлом.'.format(year))
		return redirect(race)
	user = request.user
	context = {}
	context['race'] = race
	context['event'] = event
	context['results_in_klb'] = 0
	context['results_to_add'] = 0
	context['results_errors'] = 0
	context['page_title'] = u'{}: результаты забега для КЛБМатча'.format(race.name_with_event())
	if race.distance_real and (race.distance_real.length < race.distance.length):
		distance = race.distance_real
	else:
		distance = race.distance
	context['distance'] = distance

	official_results = race.result_set.filter(source=models.RESULT_SOURCE_DEFAULT, status=models.STATUS_FINISHED).select_related('runner').order_by(
		'lname', 'fname', 'pk')
	n_official_results = official_results.count()

	if models.Klb_result.objects.filter(race=race, result=None).exists():
		context['hasUnboundResults'] = 1
		return render(request, 'editor/klb/race_details.html', context)
	if n_official_results and race.get_unofficial_results().exists():
		context['hasOffAndUnoffResults'] = 1
		return render(request, 'editor/klb/race_details.html', context)
	results = []
	race_date = race.start_date if race.start_date else event.start_date
	klb_participant_ids = set(models.Klb_participant.objects.filter(
			Q(date_registered=None) | Q(date_registered__lte=race_date),
			Q(date_removed=None) | Q(date_removed__gte=race_date),
			was_deleted_from_team=False, match_year=year,
		).values_list('klb_person__id', flat=True))
	has_results_to_work = False
	# event_person_ids = set(models.Klb_result.objects.filter(race__event=event).values_list('klb_person_id', flat=True))
	event_person_ids = set(models.Klb_result.objects.filter(
		race__event=event, race__start_date=race.start_date, race__start_time=race.start_time).values_list('klb_person_id', flat=True))

	if n_official_results >= MIN_RESULTS_TO_USE_PAGES:
		context['using_pages'] = True
		pages_number = get_pages_number(n_official_results)
		context['pages'] = range(pages_number)
		page = models.int_safe(page)
		context['page'] = page
		official_results = list(official_results[(page * RESULTS_PER_PAGE):((page + 1) * RESULTS_PER_PAGE)])
		context['n_results_on_cur_page'] = RESULTS_PER_PAGE if (n_official_results >= (page + 1) * RESULTS_PER_PAGE) \
			else n_official_results - page * RESULTS_PER_PAGE
		context['first_lname'] = official_results[0].lname
		context['last_lname'] = official_results[-1].lname
	else:
		context['using_pages'] = False

	for result in official_results:
		errors = []
		person = None
		candidates = []
		compared_type = COMPARED_BY_NOTHING
		has_checkboxes = False
		value_for_order = 0
		if hasattr(result, 'klb_result'):
			context['results_in_klb'] += 1
		elif (distance.distance_type == models.TYPE_MINUTES) and (result.result < models_klb.get_min_distance_for_bonus(year)):
			errors.append(u'Результат слишком мал для КЛБМатча.')
		else: # Let's try to find person in KLBmatch for this result
			value_for_order = 10

			persons = models.Klb_person.objects.filter(
					pk__in=klb_participant_ids,
					runner__id__in=get_runner_ids_for_result(result),
					# lname=result.lname,
					# fname=result.fname
				).select_related('city__region__country')
			if result.birthday:
				if result.birthday_known:
					persons = persons.filter(birthday=result.birthday)
					compared_type = COMPARED_BY_BIRTHDAY
				else:
					persons = persons.filter(birthday__year=result.birthday.year)
					compared_type = COMPARED_BY_BIRTHYEAR
			elif result.age:
				birthyear_around = year - result.age
				persons = persons.filter(birthday__year__range=(birthyear_around - 1, birthyear_around + 1))
				compared_type = COMPARED_BY_AGE
			if not persons.exists():
				continue
			value_for_order += compared_type
			for person in persons:
				has_results_to_work = True
				candidate_errors = []
				candidate_comments = []
				show_checkbox = True
				team = person.get_team(year)
				club = team.club if team else None
				if person.id in event_person_ids:
					candidate_errors.append(u'У этого участника КЛБМатча уже есть зачтенный результат в этом забеге с тем же временем старта')
					show_checkbox = False
				if club and result.club_name:
					club_name_found = False
					for club_name in [club.name, team.name] + list(club.club_name_set.values_list('name', flat=True)):
						if club_name.lower()[:6] in result.club_name.lower():
							club_name_found = True
							break
					if club_name_found:
						candidate_comments.append(u'Клуб указан в протоколе')
						value_for_order += 5
					else:
						candidate_errors.append(u'Клуб бегуна противоречит протоколу')
				runner = result.runner
				if runner:
					if runner.klb_person_id and (runner.klb_person_id != person.id):
						candidate_errors.append(u'В БД результатов указан другой бегун – с id {}'.format(runner.klb_person_id))
						show_checkbox = False
					elif (runner.klb_person_id is None) and hasattr(person, 'runner') and person.runner.klb_person_id:
						candidate_errors.append(u'К результату уже привязан другой бегун')
						show_checkbox = False
				if show_checkbox:
					has_checkboxes = True
				candidates.append({
					'person': person,
					'errors': candidate_errors,
					'comments': candidate_comments,
					'show_checkbox': show_checkbox,
					'team': team,
					'club': club,
				})
			if has_checkboxes:
				context['results_to_add'] += 1
		if hasattr(result, 'klb_result') or candidates or errors:
			results.append({
				'result': result,
				'candidates': candidates,
				'errors': errors,
				'value_for_order': value_for_order,
				'checked_by_default': (len(candidates) == 1) and (not candidates[0]['errors'])
					and ( ((result.club_name != '') and team) or (compared_type >= COMPARED_BY_BIRTHYEAR) ),
				'compared_type': COMPARED_TYPES[compared_type][1],
				'has_checkboxes': has_checkboxes,
			})
		if errors:
			context['results_errors'] += 1
	if (not has_results_to_work) and (not race.was_checked_for_klb) and ( (not context['using_pages']) or (page == pages_number - 1) ):
		race.was_checked_for_klb = True
		race.save()
		models.log_obj_create(user, event, models.ACTION_RACE_UPDATE, field_list=['was_checked_for_klb'], child_object=race)
		context['just_checked'] = 1
	context['results'] = sorted(results, key=lambda x:-x['value_for_order'])
	context['results_total'] = n_official_results
	context['results_unbound'] = race.klb_result_set.filter(result=None)
	context['races'] = event.race_set.select_related('distance').order_by('distance__distance_type', '-distance__length')
	context['KLB_STATUS_OK'] = models.KLB_STATUS_OK
	return render(request, 'editor/klb/race_details.html', context)

@group_required('admins')
def klb_race_process(request, race_id=None):
	race = get_object_or_404(models.Race, pk=race_id)
	event = race.event
	year = event.start_date.year
	user = request.user
	distance, was_real_distance_used = race.get_distance_and_flag_for_klb()
	page = None
	if models.Klb_result.objects.filter(race=race, result=None).exists():
		messages.warning(request, u'На этой дистанции есть результаты, проведённые в КЛБМатч, но не привязанные к загруженным результатам.')
	elif request.method == 'POST':
		results_added = 0
		results_deleted = 0
		results_errors = 0
		touched_persons = set()
		touched_teams = Counter()
		page = models.int_safe(request.POST.get('page', 0))
		pages_number = get_pages_number(race.result_set.filter(source=models.RESULT_SOURCE_DEFAULT, status=models.STATUS_FINISHED).count())
		only_bonus_score = 'only_bonus_score' in request.POST
		for key, val in request.POST.items():
			if key.startswith("person_for_"):
				person_id = models.int_safe(val)
				if person_id == 0:
					continue
				result_id = models.int_safe(key[len("person_for_"):])
				result = models.Result.objects.filter(race=race, id=result_id, klb_result=None).first()
				if result is None:
					messages.warning(request, u'Результат с id {} не найден. Пропускаем'.format(result_id))
					continue
				if hasattr(result, 'klb_result'):
					messages.warning(request, u'Результат с id {} уже учтён в КЛБМатче. Пропускаем'.format(result_id))
					continue
				person = models.Klb_person.objects.filter(pk=person_id).first()
				if not person:
					messages.warning(request, u'{} {}: участник КЛБМатчей с id {} не найден. Пропускаем'.format(
						result.fname, result.lname, person_id))
					continue
				if not check_results_with_same_time(request, race, event, person, result):
					continue
				# We can have two runners: from result and from person
				if result.runner:
					runner = result.runner
					if hasattr(person, 'runner'):
						if runner != person.runner:
							messages.warning(request, (u'{} {}: у результата и участника Матча два разных бегуна, {} и {}. '
								+ u'Сначала объедините их').format(result.fname, result.lname, result.runner, person.runner))
							continue
						# If runner == person.runner, we just do nothing
					elif runner.klb_person_id and (runner.klb_person_id != person.id):
						messages.warning(request, (u'{} {}: В БД результатов указан другой бегун – с id {}. Пропускаем').format(
							result.fname, result.lname, runner.klb_person_id))
						continue
					# So result has its runner, person doesn't have, and either runner.klb_person_id = person.id or runner.klb_person_id=None
					if runner.klb_person_id is None:
						runner.klb_person = person
						runner.save()
						person.refresh_from_db()
				# Great! That's time to create KLBResult
				create_klb_result(result, person, user, distance, was_real_distance_used, only_bonus_score=only_bonus_score,
					comment=u'Со страницы обработки официальных результатов')
				table_update = models.Table_update.objects.filter(
						model_name=event.__class__.__name__,
						row_id=event.id,
						child_id=result.id,
						action_type=models.ACTION_RESULT_UPDATE,
						is_verified=False,
					).first()
				if table_update:
					table_update.verify(request.user, comment=u'одобрено при обработке старта целиком')
				touched_persons.add(person)
				# update_participant_score(person)
				team = person.get_team(year)
				if team:
					touched_teams[team] += 1
				results_added += 1
			elif key.startswith("to_delete_"):
				result_id = models.int_safe(key[len("to_delete_"):])
				result = models.Result.objects.filter(race=race, id=result_id, klb_result__isnull=False).first()
				if not result:
					messages.warning(request, u'Результат с id {} не найден. Пропускаем'.format(result_id))
					continue
				klb_result = result.klb_result
				touched_persons.add(klb_result.klb_person)
				team = klb_result.get_team()
				if team:
					touched_teams[team] += 1
				models.log_obj_delete(user, event, child_object=klb_result, action_type=models.ACTION_KLB_RESULT_DELETE)
				klb_result.delete()
				if 'to_unclaim_{}'.format(result_id) in request.POST:
					result.unclaim_from_runner(user)
				results_deleted += 1
		if results_added:
			messages.success(request, u'В КЛБМатч добавлено результатов: {}'.format(results_added))
			race.fill_winners_info()
		if results_deleted:
			messages.success(request, u'Из КЛБМатча удалено результатов: {}'.format(results_deleted))
		if touched_persons:
			update_persons_score(year=year, persons_to_update=touched_persons, update_runners=True)
			messages.success(request, u'Затронуто участников Матча: {}. Их результаты пересчитаны.'.format(len(touched_persons)))
		if touched_teams:
			messages.success(request, u'Затронуты команды: {}'.format(', '.join(team.name for team in touched_teams)))
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
					comment=u'Обработка всей дистанции в КЛБМатч',
					added_by=user,
				)
		if (not race.was_checked_for_klb) and (page == pages_number - 1):
			race.was_checked_for_klb = True
			race.save()
			models.log_obj_create(user, event, models.ACTION_RACE_UPDATE, field_list=['was_checked_for_klb'], child_object=race)
	return redirect(race.get_klb_editor_url(page=page))

def getKlbResultFormSet(extra, data=None, **kwargs):
	KlbResultFormSet = formset_factory(KlbResultForm, extra=extra)
	return KlbResultFormSet(data=data, form_kwargs=kwargs)

N_PERSONS_DEFAULT = 3
@login_required
def klb_race_add_results(request, race_id):
	race = get_object_or_404(models.Race, pk=race_id)
	event = race.event
	year = event.start_date.year
	user = request.user
	context = user_edit_vars(user, series=event.series)
	race_is_for_klb = race.get_klb_status() == models.KLB_STATUS_OK
	context['race'] = race
	context['event'] = event
	if race_is_for_klb:
		context['page_title'] = u'{}: ввод результатов для КЛБМатча'.format(race)
	else:
		context['page_title'] = u'{}: ввод отдельных результатов'.format(race)
	context['race_is_ok_for_klb'] = race_is_for_klb
	context['KLB_STATUS_OK'] = models.KLB_STATUS_OK
	context['user_is_female'] = user.user_profile.is_female()

	club_id = models.int_safe(request.POST.get('club', 0))
	if context['is_admin']: # Only admins can add results to individual participants here
		club = models.Club.objects.filter(pk=club_id).first()
	else:
		club = get_object_or_404(models.Club, pk=club_id)

	if (not context['is_admin']) and (club not in user.user_profile.get_club_set_to_add_results()):
		messages.warning(request, u'У Вас нет прав на это действие')
		return redirect(race)

	# if club:
	# 	participants = models.Klb_participant.objects.filter(match_year=year, team__club=club)
	# else:
	# 	participants = models.Klb_participant.objects.filter(match_year=year, team=None)
	# possible_person_ids = set(participants.values_list('klb_person_id', flat=True)) - set(race.result_set.values_list('runner__klb_person_id', flat=True))
	runners_for_user = user.user_profile.get_runners_to_add_results(race, race_is_for_klb=race_is_for_klb, club=club, for_given_club_only=True)

	n_persons = models.int_safe(request.POST.get('n_persons', N_PERSONS_DEFAULT))
	formset_kwargs = {
		'race': race,
		'extra': n_persons,
		'is_admin': context['is_admin'],
		'race_is_for_klb': race_is_for_klb,
		'runner_choices': [('', u'(пропускаем)')] + [(runner.id, data['text']) for runner, data in runners_for_user.items()],
		'disabled_choices': set(runner.id for runner, data in runners_for_user.items() if data['is_already_in_race']),
	}
	if 'formset_submit' in request.POST:
		formset = getKlbResultFormSet(data=request.POST, **formset_kwargs)
		if formset.is_valid():
			n_results_created = 0
			n_klb_results_created = 0
			touched_persons = set()
			touched_runners = set()
			touched_teams = Counter()
			loaded_from = request.POST.get('source', '')
			distance, was_real_distance_used = race.get_distance_and_flag_for_klb()

			for form in formset:
				runner = form.cleaned_data.get('runner')
				if runner:
					if runner not in runners_for_user:
						messages.warning(request, u'Участник забегов {} (id {}) не относится к выбранному клубу. Пропускаем'.format(
							runner.name(), runner.id))
						continue
					result = models.Result.objects.create(
						race=race,
						runner=runner,
						user=runner.user,
						loaded_by=user,
						lname=runner.lname,
						fname=runner.fname,
						source=models.RESULT_SOURCE_USER,
						loaded_from=loaded_from,
						result=form.cleaned_data['result'],
					)
					touched_runners.add(runner)
					n_results_created += 1
					# And now try to create result for KLBMatch if needed
					will_be_counted_for_klb = False
					only_bonus_score = False
					if race_is_for_klb and runners_for_user[runner]['is_in_klb'] and form.cleaned_data.get('is_for_klb', False):
						person = runner.klb_person
						if person and check_distance_and_result(request, distance, person, result, year) \
								and check_results_with_same_time(request, race, event, person, result):
							if context['is_admin']:
								create_klb_result(result, person, user, distance, was_real_distance_used,
									only_bonus_score=form.cleaned_data.get('only_bonus_score', False),
									comment=u'Со страницы добавления отдельных результатов')
								touched_persons.add(person)
								team = person.get_team(year)
								if team:
									touched_teams[team] += 1
							else:
								will_be_counted_for_klb = True
							n_klb_results_created += 1
					models.log_obj_create(user, event, models.ACTION_UNOFF_RESULT_CREATE, child_object=result, is_for_klb=will_be_counted_for_klb)
			if n_results_created:
				if race.loaded == models.RESULTS_NOT_LOADED:
					race.loaded = models.RESULTS_SOME_UNOFFICIAL
					race.save()
				for runner in touched_runners:
					update_runner_stat(runner=runner)
					if runner.user:
						update_runner_stat(user=runner.user, update_club_members=False)
				messages.success(request, u'Добавлено результатов: {}. Статистика этих бегунов обновлена'.format(n_results_created))
			if n_klb_results_created:
				messages.success(request, u'В том числе результатов в КЛБМатч: {}.{}'.format(n_klb_results_created,
					'' if context['is_admin'] else u' Очки за них будут добавлены после добавления модератором'))
			if touched_persons:
				update_persons_score(year=year, persons_to_update=touched_persons, update_runners=True)
				messages.success(request, u'Затронуто участников Матча: {}. Их результаты пересчитаны.'.format(len(touched_persons)))
			if touched_teams:
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
						comment=u'Добавление администратором отдельных результатов',
						added_by=user,
					)
			return redirect(race)
		else:
			messages.warning(request, u"Результаты не добавлены. Пожалуйста, исправьте ошибки в форме.")
	else:
		# So we just arrived here or have errors in POST request
		formset = getKlbResultFormSet(**formset_kwargs)
	context['club'] = club
	context['n_persons'] = n_persons
	context['formset'] = formset
	context['hasOfficialResults'] = race.get_official_results().exists()
	context['type_minutes'] = (race.distance.distance_type == models.TYPE_MINUTES)
	return render(request, 'editor/klb/race_add_results.html', context)
