# -*- coding: utf-8 -*-
from __future__ import division
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import permission_required
from django.forms import modelformset_factory
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.contrib import messages
import datetime

from results import models
from editor import forms
from .views_common import group_required, check_rights
from .views_stat import update_runner_stat, update_course_records
from .views_klb import create_klb_result, update_klb_result_meters, update_klb_result_time
from .views_klb_stat import update_persons_score

from .views_user_actions import log_form_change, log_document_formset

def get_first_name_position(raw_names): # Name Surname or Surname Name or ...?
	popular_names = set([
		u'александр', u'алексей', u'даниил', u'дмитрий', u'евгений', u'иван', u'максим', u'михаил', u'никита', u'сергей',
		u'александра', u'анастасия', u'анна', u'виктория', u'дарья', u'екатерина', u'елизавета', u'мария', u'софия', u'юлия',
		u'елена', u'татьяна', u'ольга', u'наталья', u'ирина', u'светлана', u'людмила',
		u'владимир', u'андрей', u'николай', u'степан', u'роман', u'iван'])
	first_name_positions = [0, 0, 0]
	for name in raw_names[:50]:
		name_split = name.lower().split()
		if len(name_split) > 0:
			if name_split[0] in popular_names:
				first_name_positions[0] += 1
			if len(name_split) > 1:
				if name_split[1] in popular_names:
					first_name_positions[1] += 1
				if len(name_split) > 2:
					if name_split[2] in popular_names:
						first_name_positions[2] += 1
	if first_name_positions[0] >= first_name_positions[1]:
		if first_name_positions[0] >= first_name_positions[2]:
			return 0
		else:
			return 2
	elif first_name_positions[1] >= first_name_positions[2]:
		return 1
	else:
		return 2

def split_name(name_raw, first_name_position): # Return triple: lname, fname, midname
	name_split = name_raw.split()
	if len(name_split) == 0: # Something strange
		return '', '', ''
	elif len(name_split) == 1: # Only one word - let it be last name
		return name_split[0], '', ''
	elif len(name_split) == 2:
		if first_name_position == 0: # Игорь Нетто
			return name_split[1], name_split[0], ''
		else: # Нетто Игорь
			return name_split[0], name_split[1], ''
	else: # len(name_split) > 2
		if first_name_position == 0: # Семён Семёнович Горбунков
			return " ".join(name_split[2:]), name_split[0], name_split[1]
		else: # Горбунков Семён Семёнович
			return name_split[0], name_split[1], " ".join(name_split[2:])

def fill_places(race):
	results = race.result_set.filter(result__gt=0, status=models.STATUS_FINISHED, source=models.RESULT_SOURCE_DEFAULT).select_related(
		'category_size').order_by('-result' if race.distance.distance_type == 2 else 'result')
	n_results = results.count()

	# How many people we already passed
	overall_place = 0
	gender_places = [0, 0, 0]
	category_places = dict()

	# Place of last passed result
	overall_place_last = 0
	gender_places_last = [0, 0, 0]
	category_places_last = dict()

	# Lasted passed result
	prev_overall_result = None
	prev_gender_results = [None, None, None]
	prev_category_results = dict()
	for result in results:
		overall_place += 1
		if result.result == prev_overall_result:
			result.place = overall_place_last
		else:
			result.place = overall_place
			overall_place_last = overall_place
			prev_overall_result = result.result

		if result.gender != models.GENDER_UNKNOWN:
			gender_places[result.gender] += 1
			if result.result == prev_gender_results[result.gender]:
				result.place_gender = gender_places_last[result.gender]
			else:
				result.place_gender = gender_places[result.gender]
				gender_places_last[result.gender] = gender_places[result.gender]
				prev_gender_results[result.gender] = result.result

		if result.category_size:
			category = result.category_size.name.lower()
			category_places[category] = category_places.get(category, 0) + 1
			if result.result == prev_category_results.get(category, None):
				result.place_category = category_places_last[category]
			else:
				result.place_category = category_places[category]
				category_places_last[category] = category_places[category]
				prev_category_results[category] = result.result
		result.save()

	race.category_size_set.all().update(size=0)
	for category, size in category_places.items():
		category_size, created = models.Category_size.objects.get_or_create(race=race, name=category)
		if created:
			models.send_panic_email(
				'Results with category have no category_size link',
				u'At race {} (id {}) there are results with category {} (size {}) but without a link to category size'.format(
					race, race.id, category, size)
			)
		category_size.size = size
		category_size.save()

	race.result_set.filter(Q(result=0) | Q(status__gt=models.STATUS_FINISHED), source=models.RESULT_SOURCE_DEFAULT).update(
		place=None, place_gender=None, place_category=None)
	for category_size in list(race.category_size_set.filter(size=0)):
		if not category_size.result_set.exists():
			category_size.delete()

	return n_results, len(category_places)

# Distances to create
@group_required('editors', 'admins')
def race_fill_places(request, race_id):
	race = get_object_or_404(models.Race, pk=race_id)
	context, has_rights, target = check_rights(request, event=race.event)
	if not has_rights:
		return target
	n_results, n_categories = fill_places(race)
	messages.success(request, u'Места для забега «{}» на {} успешно проставлены. Всего {} результатов, {} категорий.'.format(
		race.event, race.distance, n_results, n_categories))
	return redirect(race)

# Different actions with results
def fill_race_headers(race):
	results = race.get_official_results()
	if results.exists():
		participants = results.exclude(status=models.STATUS_DNS)
		race.n_participants = participants.count()
		race.n_participants_men = participants.filter(gender=models.GENDER_MALE).count()
		finishers = results.filter(status=models.STATUS_FINISHED)
		race.n_participants_finished = finishers.count()
		race.n_participants_finished_men = finishers.filter(gender=models.GENDER_MALE).count()
	else:
		race.n_participants = None
		race.n_participants_men = None
		race.n_participants_finished = None
		race.n_participants_finished_men = None
	race.fill_winners_info(to_save=False)
	race.save()
	update_course_records(race.event.series)

def reset_race_headers(race):
	race.n_participants = None
	race.n_participants_men = None
	race.n_participants_finished = None
	race.n_participants_finished_men = None
	race.reset_winners_info(to_save=False)
	race.save()
	update_course_records(race.event.series)

@group_required('editors', 'admins')
def update_race_headers(request, race_id):
	race = get_object_or_404(models.Race, pk=race_id)
	context, has_rights, target = check_rights(request, event=race.event)
	if not has_rights:
		return target
	fill_race_headers(race)
	messages.success(request, u'Информация о победителях успешно обновлена')
	return redirect(race)

# Different actions with results
@group_required('admins')
def race_swap_names(request, race_id, swap_type):
	race = get_object_or_404(models.Race, pk=race_id)
	results = race.result_set.all()
	n_touched = 0
	swap_type = models.int_safe(swap_type)
	for result in results:
		if swap_type == 1:
			tmp = result.fname
			result.fname = result.lname
			result.lname = tmp
			result.save()
			n_touched += 1
		elif swap_type == 2:
			tmp = result.fname
			result.fname = result.midname
			result.midname = tmp
			result.save()
			n_touched += 1
	if swap_type in [1,2]:
		messages.success(request, u'Успешно обновлено имён: {}.'.format(n_touched))
	else:
		messages.warning(request, u'Неправильный тип перестановки имён:{}.'.format(swap_type))
	if n_touched:
		race.fill_winners_info()
	return redirect(race)

N_EXTRA_SPLITS = 5
def getSplitFormSet(result, data=None):
	SplitFormSet = modelformset_factory(models.Split, form=forms.SplitForm, formset=forms.SplitFormSet, can_delete=True, extra=N_EXTRA_SPLITS)
	distance = result.race.distance
	return SplitFormSet(
		data=data,
		queryset=result.split_set.order_by('distance__length'),
		initial=[{'result':result}] * N_EXTRA_SPLITS,
		form_kwargs={
			'distance': distance,
		},
	)

@group_required('admins')
def result_details(request, result_id=None, result=None, frmResult=None, create_new=False, frmSplits=None):
	if not result: # False if we are creating new result
		result = get_object_or_404(models.Result, pk=result_id)
	if result and not frmResult:
		frmResult = forms.SmallResultForm(instance=result)
	race = result.race
	event = race.event
	context = {}
	context['result'] = result
	context['race'] = race
	context['event'] = event
	context['year'] = event.start_date.year
	context['form'] = frmResult
	context['create_new'] = create_new
	context['type_minutes'] = (race.distance.distance_type == models.TYPE_MINUTES)

	race_status = race.get_klb_status()
	context['race_is_ok_for_klb'] = (race_status == models.KLB_STATUS_OK)
	context['show_klb_section'] = \
		(
			context['race_is_ok_for_klb']
			or ((race_status == models.KLB_STATUS_ONLY_ONE_PARTICIPANT) and hasattr(result, 'klb_result'))
		) \
		and (
				(result.runner is None) or (
					result.runner.klb_person
					and result.runner.klb_person.klb_participant_set.filter(match_year=event.start_date.year).exists()
				)
			)
	context['page_title'] = u'Создание нового результата' if create_new else u'Результат {}'.format(result)
	if not create_new:
		if frmSplits is None:
			frmSplits = getSplitFormSet(result)
		context['frmSplits'] = frmSplits
	return render(request, "editor/result_details.html", context)

def update_result_connections(user, new_result, changed_data, result=models.Result()):
	""" If needed, recalc klb_result. If needed, update user's and runner's statistic. If possible, use old result fields """
	klb_result_changed = False
	if hasattr(new_result, 'klb_result') and ('result' in changed_data) and (new_result.race.get_klb_status() == models.KLB_STATUS_OK):
		team = new_result.klb_result.klb_participant.team
		if new_result.race.distance.distance_type == models.TYPE_MINUTES:
			update_klb_result_meters(new_result.klb_result, user)
		else:
			update_klb_result_time(new_result.klb_result, user)
		klb_result_changed = True
		person = new_result.klb_result.klb_person
		update_persons_score(year=new_result.race.event.start_date.year, persons_to_update=[person], update_runners=True)
		if team:
			prev_score = team.score
			team.refresh_from_db()
			models.Klb_team_score_change.objects.create(
				team=team,
				race=new_result.race,
				clean_sum=team.score - team.bonus_score,
				bonus_sum=team.bonus_score,
				delta=team.score - prev_score,
				n_persons_touched=1,
				comment=u'Изменение результата участника {} {}'.format(person.fname, person.lname),
				added_by=user,
			)
	users_to_update = set()
	runners_to_update = set()
	if 'result' in changed_data:
		for user in [result.user, new_result.user]:
			if user:
				users_to_update.add(user)
		for runner in [result.runner, new_result.runner]:
			if runner:
				runners_to_update.add(runner)
	else:
		if 'user' in changed_data:
			for user in [result.user, new_result.user]:
				if user:
					users_to_update.add(user)
		if 'runner' in changed_data:
			for runner in [result.runner, new_result.runner]:
				if runner:
					runners_to_update.add(runner)
	for user in users_to_update:
		update_runner_stat(user=user)
	for runner in runners_to_update:
		update_runner_stat(runner=runner)
	if ('user' in changed_data) and new_result.user:
		new_result.add_for_mail()
	return klb_result_changed

@group_required('admins')
def result_update(request, result_id):
	result = get_object_or_404(models.Result, pk=result_id)
	race = result.race
	if ('frmResult_submit' in request.POST) or ('frmResult_submit_gotorace' in request.POST):
		form = forms.SmallResultForm(request.POST, instance=result)
		if form.is_valid():
			new_result = form.save()
			log_form_change(request.user, form, models.ACTION_RESULT_UPDATE, obj=new_result.race.event, child_id=new_result.id)
			klb_result_changed = update_result_connections(request.user, new_result, form.changed_data, result)
			if klb_result_changed:
				messages.success(request, u'Очки за результат в КЛБМатче пересчитаны')
			messages.success(request, u'Результат «{}» успешно обновлён. Изменены следующие поля: {}'.format(
				result, ", ".join(form.changed_data)))
			if (race.get_klb_status() == models.KLB_STATUS_OK) and race.was_checked_for_klb:
				race.was_checked_for_klb = False
				race.save()
			if race.loaded == models.RESULTS_LOADED:
				if ('result' in form.changed_data) or ('status' in form.changed_data):
					fill_places(race)
					fill_race_headers(race)
				elif ('user' in form.changed_data) or ('runner' in form.changed_data):
					race.fill_winners_info()
			if 'frmResult_submit' in request.POST:
				return redirect(result.get_editor_url())
			else:
				return redirect(race)
		else:
			messages.warning(request, u"Результат не обновлён. Пожалуйста, исправьте ошибки в форме.")
	else:
		form = None
	return result_details(request, result_id=result_id, result=result, frmResult=form)

@group_required('admins')
def result_add_to_klb(request, result_id):
	result = get_object_or_404(models.Result, pk=result_id)
	year = result.race.event.start_date.year
	if ('select_participant_for_klb' in request.POST) and (result.get_klb_status() == models.KLB_STATUS_OK):
		participant_id = models.int_safe(request.POST['select_participant_for_klb'])
		participant = get_object_or_404(models.Klb_participant, pk=participant_id, match_year=year)
		person = participant.klb_person
		if participant.match_year != year:
			messages.warning(request, u'Результат относится к {} году, а участник — к {} году'.format(year, participant.match_year))
		if result.race.klb_result_set.filter(klb_person=person).exists():
			messages.warning(request, u'У участника КЛБМатчей с id {} уже есть результат в матче на этом старте'.format(person_id))
		else:
			only_bonus_score = 'only_bonus_score' in request.POST
			team = participant.team if participant else None
			klb_result = create_klb_result(result, person, request.user, only_bonus_score=only_bonus_score, comment=u'Со страницы правки результата')
			update_persons_score(year=year, persons_to_update=[person])
			if team:
				prev_score = team.score
				team.refresh_from_db()
				models.Klb_team_score_change.objects.create(
					team=team,
					race=result.race,
					clean_sum=team.score - team.bonus_score,
					bonus_sum=team.bonus_score,
					delta=team.score - prev_score,
					n_persons_touched=1,
					comment=u'Добавление результата участника {} {}{}'.format(person.fname, person.lname, u' (только бонусы)' if only_bonus_score else ''),
					added_by=request.user,
				)
			messages.success(request, u'Результат успешно засчитан в КЛБМатч. Очки участника {} {} (id {}) обновлены'.format(
				person.fname, person.lname, person.id))
	return redirect(result.get_editor_url())

@group_required('admins')
def result_delete_from_klb(request, result_id):
	result = get_object_or_404(models.Result, pk=result_id)
	if ('frmKlbResult_submit' in request.POST) and hasattr(result, 'klb_result') and \
			(result.race.get_klb_status() in (models.KLB_STATUS_OK, models.KLB_STATUS_ONLY_ONE_PARTICIPANT)):
		person_id = models.int_safe(request.POST.get('select_person_for_klb', 0))
		klb_result = result.klb_result
		person = klb_result.klb_person
		team = klb_result.klb_participant.team
		models.log_obj_delete(request.user, result.race.event, child_object=klb_result, action_type=models.ACTION_KLB_RESULT_DELETE)
		klb_result.delete()
		to_update_runner = False
		if 'to_unclaim' in request.POST:
			result.unclaim_from_runner(request.user)
			to_update_runner = True
		update_persons_score(year=result.race.event.start_date.year, persons_to_update=[person], update_runners=to_update_runner)
		if team:
			prev_score = team.score
			team.refresh_from_db()
			models.Klb_team_score_change.objects.create(
				team=team,
				race=result.race,
				clean_sum=team.score - team.bonus_score,
				bonus_sum=team.bonus_score,
				delta=team.score - prev_score,
				n_persons_touched=1,
				comment=u'Удаление результата участника {} {} из КЛБМатча'.format(person.fname, person.lname),
				added_by=request.user,
			)
		messages.success(request, u'Результат успешно удалён из КЛБМатча. Очки участника {} {} (id {}) обновлены'.format(
			person.fname, person.lname, person.id))
		return redirect(result.get_editor_url())
	return result_details(request, result_id=result_id, result=result)

@group_required('admins')
def result_mark_as_error(request, result_id):
	if not ('frmKlbErrorResult_submit' in request.POST):
		return redirect(result.get_editor_url())
	result = get_object_or_404(models.Result, pk=result_id)
	if not hasattr(result, 'klb_result'):
		messages.warning(request, u'Этот результат и так не учтён в КЛБМатчах')
		return redirect(result.get_editor_url())
	klb_result = result.klb_result
	event = result.race.event 
	year = event.start_date.year
	if models.is_active_klb_year(year):
		messages.warning(request, u'Этот результат относится к продолжающемуся КЛБМатчу. Просто удалите его и, если нужно, отвяжите от бегуна')
		return redirect(result.get_editor_url())
	klb_result.result = None
	klb_result.is_error = True
	klb_result.save()

	touched_fields = []
	runner = result.runner
	if runner:
		touched_fields.append('runner')
		result.runner = None
	user = result.user
	if user:
		touched_fields.append('user')
		result.user = None
	result.save()
	if user:
		update_runner_stat(user=user)
	if runner:
		update_runner_stat(runner=runner)
	models.log_obj_create(request.user, event, models.ACTION_RESULT_UPDATE, field_list=touched_fields, child_object=result,
		comment=u'При помечании КЛБ-результата как ошибочного')
	messages.success(request, u'КЛБ-результат помечен как ошибочный и отвязан от бегуна')
	return redirect(result.get_editor_url())

@group_required('admins')
def result_delete(request, result_id):
	result = get_object_or_404(models.Result, pk=result_id)
	race = result.race
	models.log_obj_delete(request.user, race.event, child_object=result)
	res_str = unicode(result)
	if hasattr(result, 'klb_result'):
		year = race.event.start_date.year
		if models.is_active_klb_year(year):
			person = result.klb_result.klb_person
			team = result.klb_result.klb_participant.team
			result.klb_result.delete()
			update_persons_score(year=year, persons_to_update=[person], update_runners=True)
			if team:
				prev_score = team.score
				team.refresh_from_db()
				models.Klb_team_score_change.objects.create(
					team=team,
					race=result.race,
					clean_sum=team.score - team.bonus_score,
					bonus_sum=team.bonus_score,
					delta=team.score - prev_score,
					n_persons_touched=1,
					comment=u'Удаление результата участника {} {} насовсем'.format(person.fname, person.lname),
					added_by=request.user,
				)
			messages.warning(request, u'Результат из КЛБМатча успешно удалён')
	runner = result.runner
	result.delete()
	if runner:
		update_runner_stat(runner=runner)
		if runner.user:
			update_runner_stat(user=runner.user)
	fill_places(race)
	fill_race_headers(race)
	messages.success(request, u"Результат {} на забеге «{}» успешно удалён. Места проставлены заново, числа участников обновлены".format(
		res_str, race))
	return redirect(race)

@group_required('admins')
def result_splits_update(request, result_id):
	result = get_object_or_404(models.Result, pk=result_id)
	if (request.method == 'POST') and ('frmSplits_submit' in request.POST):
		formset = getSplitFormSet(result, data=request.POST)
		if formset.is_valid():
			formset.save()
			log_document_formset(request.user, result.race.event, formset)
			messages.success(request, (u'Сплиты результата «{}» успешно обновлены: {} сплитов добавлено, {} обновлено, '
				+ u'{} удалено. Проверьте, всё ли правильно.').format(
				result, len(formset.new_objects), len(formset.changed_objects), len(formset.deleted_objects)))
			return redirect('editor:result_details', result_id=result.id)
		else:
			messages.warning(request, u"Сплиты результата «{}» не обновлены. Пожалуйста, исправьте ошибки в форме.".format(result))
	else:
		formset = None
	return result_details(request, result_id=result_id, result=result, frmSplits=formset)

def make_names_title():
	fields = ['lname', 'fname', 'midname']
	to_change = {}
	for field in fields:
		to_change[field] = 0
	for thousand in range(1544):
		for result in models.Result.objects.filter(pk__range=(thousand * 1000 + 1, thousand * 1000 + 1000)):
			for field in fields:
				value = getattr(result, field)
				if value.title() != value:
					setattr(result, field, value.title())
					result.save()
					to_change[field] += 1
	for field in fields:
		print field, to_change[field]
	print 'Done!'

def clean_hundredths(race_id): # Sometimes, due to weird Excel files, we want to remove any fractions of seconds
	race = models.Race.objects.get(pk=race_id)
	n_results_changed = 0
	for result in race.result_set.all():
		new_value = (result.result // 100) * 100
		if new_value != result.result:
			result.result = new_value
			result.save()
			n_results_changed += 1
	print 'Done! Results changed:', n_results_changed

def fill_category_sizes_once(race_id_start_from=31543):
	categories_filled = 0
	categories_deleted = 0
	categories_updated = 0
	results_touched = 0
	race_count = 0
	for race in models.Race.objects.filter(pk__gte=race_id_start_from, loaded=models.RESULTS_LOADED).order_by('pk'):
		results = race.result_set.filter(result__gt=0, status=models.STATUS_FINISHED, source=models.RESULT_SOURCE_DEFAULT)
		for category_size in list(race.category_size_set.all()):
			category_results = results.filter(category=category_size.name)
			count = category_results.count()
			if count:
				results_touched += category_results.exclude(category_size=category_size).update(category_size=category_size)
				categories_filled += 1
				if category_size.size != count:
					print u'Race {}. Category {}. Actual size: {}. We had size {}. Updating'.format(race.id, category_size.name, count, category_size.size)
					category_size.size = count
					category_size.save()
					categories_updated += 1
			else:
				print u'Race {}. Empty category {}. Deleting'.format(race.id, category_size.name)
				category_size.delete()
				categories_deleted += 1
		bad_results = results.filter(category_size=None).exclude(category='')
		count = bad_results.count()
		if count:
			print u'Race {}. Results w/o category: {}. First such category: {}. Filling places again'.format(race.id, count, bad_results.first().category)
			fill_places(race)
		race_count += 1
		# if race_count >= 5000:
		# 	break
	print u'Done. Last race: {}. categories_filled: {}. categories_deleted: {}. categories_updated: {}. results_touched: {}'.format(
		race.id, categories_filled, categories_deleted, categories_updated, results_touched)

def fix_categories_case():
	n_fixed = 0
	largest_cat_size = models.Category_size.objects.order_by('-pk').first().id
	last_thousand = largest_cat_size // 1000
	for thousand in range(28, last_thousand + 1):	
		for category_size in models.Category_size.objects.filter(
				size__gt=0, pk__range=(max(28571, 1000 * thousand), 1000 * (thousand + 1) - 1)).order_by('id'):
			result = category_size.result_set.first()
			if result and result.category and (result.category != category_size.name):
				# print category_size.id, result.category, category_size.name
				category_size.name = result.category
				category_size.save()
				n_fixed += 1
			if (category_size.id % 500) == 0:
			# else:
				print category_size.id
	print 'Done!', n_fixed

# There are some races with loaded=1 that should be with loaded=2.
# By mistake, places for them were generated from results. We want to return raw places there.
def fix_partially_loaded_results(race):
	n_fixed = 0
	race.loaded = models.RESULTS_SOME_OFFICIAL
	race.save()
	reset_race_headers(race)
	for result in race.get_official_results():
		result.place = result.place_raw
		result.place_gender = result.place_gender_raw
		result.place_category = result.place_category_raw
		result.save()
		n_fixed += 1
	race.category_size_set.all().update(size=None)
	return n_fixed

def fix_all_partially_loaded_results():
	for race_id in [
30556,
30555,
	]:
		n_fixed = fix_partially_loaded_results(models.Race.objects.get(pk=race_id))
		print 'Race id:', race_id, 'fixed:', n_fixed
	print 'Finished!'

def fix_hours_minutes(race_id): # When minutes:seconds are written as hours:minutes:00
	race = models.Race.objects.get(pk=race_id)
	distance = race.distance
	if distance.distance_type != models.TYPE_METERS:
		return
	touched_runners = set()
	length = distance.length
	for result in list(race.get_official_results()):
		if models.result_is_too_large(length, result.result):
			result.result //= 60
			result.save()
			if result.runner:
				touched_runners.add(result.runner)
	for runner in touched_runners:
		update_runner_stat(runner=runner)
		if runner.user:
			update_runner_stat(user=runner.user, update_club_members=False)
	if race.loaded == models.RESULTS_LOADED:
		fill_places(race)
		fill_race_headers(race)
	print 'Done! Runners touched:', len(touched_runners)
