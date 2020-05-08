# -*- coding: utf-8 -*-
from __future__ import division
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import permission_required, login_required
from django.db.models.query import Prefetch
from django.contrib import messages
from collections import OrderedDict
import datetime

from results import models, models_klb
from editor import forms
from results.views.views_common import user_edit_vars
from .views_common import group_required, check_rights, changes_history
from .views_user_actions import log_form_change
from .views_klb_stat import update_participant_score, update_team_score, fill_match_places
from .views_klb import recalc_klb_result
from .views_stat import update_runner_stat

@group_required('admins')
def klb_person_details(request, person_id=None, person=None, frmPerson=None, frmParticipant=None, runner=None):
	context = {}
	if not person: # False if we are creating new person
		person = get_object_or_404(models.Klb_person, pk=person_id)
	if frmPerson is None:
		initial = {}
		if person.city:
			initial['city'] = person.city
			initial['region'] = person.city.region.id
		frmPerson = forms.KlbPersonForm(instance=person, initial=initial)
	years = OrderedDict()
	for year in [models.NEXT_KLB_YEAR, models.CUR_KLB_YEAR]:
		if year:
			participant_dict = {}
			participant = person.klb_participant_set.filter(match_year=year).first()
			if participant:
				klb_results = person.klb_result_set.filter(race__event__start_date__year=year)
				participant_dict['n_results'] = klb_results.count()
				participant_dict['first_run'] = klb_results.order_by('race__event__start_date').first()
				participant_dict['last_run'] = klb_results.order_by('-race__event__start_date').first()
			if frmParticipant and frmParticipant.year == year:
				participant_dict['form'] = frmParticipant
			else:
				if participant:
					participant_dict['form'] = forms.KlbParticipantForm(instance=participant, year=year)
				else:
					participant_dict['form'] = forms.KlbParticipantForm(initial={'date_registered': datetime.date.today()}, year=year)
			years[year] = participant_dict
	context['person'] = person
	context['form'] = frmPerson
	context['years'] = years
	context['page_title'] = u'КЛБМатч: участник {} (id {})'.format(person, person.id) if person.id else u'Создание нового участника КЛБМатчей'
	if runner:
		context['runner'] = runner
	return render(request, "editor/klb/person_details.html", context)

@group_required('admins')
def klb_person_update(request, person_id):
	person = get_object_or_404(models.Klb_person, pk=person_id)
	if 'frmPerson_submit' in request.POST:
		form = forms.KlbPersonForm(request.POST, instance=person)
		if form.is_valid():
			person = form.save()
			log_form_change(request.user, form, action=models.ACTION_UPDATE, exclude=['country', 'region'])
			messages.success(request, u'Участник КЛБМатча {} {} успешно обновлён. Изменены следующие поля: {}'.format(
				person.fname, person.lname, ", ".join(form.changed_data)))
			return redirect(person)
		else:
			messages.warning(request, u"Участник КЛБМатча не обновлён. Пожалуйста, исправьте ошибки в форме.")
	else:
		form = None
	return klb_person_details(request, person_id=person_id, person=person, frmPerson=form)

@group_required('admins')
def klb_person_participant_update(request, person_id, year):
	person = get_object_or_404(models.Klb_person, pk=person_id)
	year = models.int_safe(year)
	if not models.is_active_klb_year(year, True):
		messages.warning(request, u'Участников КЛБМатча-{} сейчас нельзя редактировать')
		return redirect(person)
	participant = person.klb_participant_set.filter(match_year=year).first()
	if 'frmParticipant_submit' in request.POST:
		if participant: # We just update participant's fields
			form = forms.KlbParticipantForm(request.POST, instance=participant, year=year)
			if form.is_valid():
				participant = form.save()
				team = participant.team
				log_form_change(request.user, form, models.ACTION_KLB_PARTICIPANT_UPDATE, obj=person, child_id=participant.id)
				messages.success(request, u'Данные об участии в КЛБМатче-{} успешно обновлены. Изменены следующие поля: {}'.format(year, ", ".join(form.changed_data)))
				person.update_person_contact_fields_and_prepare_letter(request.user, team, participant.email, participant.phone_number)
				deleted_race_ids = []
				klb_results = person.klb_result_set.filter(race__event__start_date__year=year)
				if ('date_registered' in form.changed_data) and participant.date_registered:
					for klb_result in klb_results.filter(race__event__start_date__lt=participant.date_registered):
						models.log_obj_delete(request.user, klb_result.race.event, child_object=klb_result,
							action_type=models.ACTION_KLB_RESULT_DELETE, comment=u'При изменении дат участия в КЛБМатче')
						deleted_race_ids.append(klb_result.race.id)
						if team:
							prev_score = team.score
							team.refresh_from_db()
							models.Klb_team_score_change.objects.create(
								team=team,
								race=klb_result.race,
								clean_sum=team.score - team.bonus_score,
								bonus_sum=team.bonus_score,
								delta=team.score - prev_score,
								n_persons_touched=1,
								comment=u'Изменение даты включения участника {} {} в команду на {}'.format(
									person.fname, person.lname, participant.date_registered.isoformat()),
								added_by=request.user,
							)
						klb_result.delete()
				if ('date_removed' in form.changed_data) and participant.date_removed:
					for klb_result in klb_results.filter(race__event__start_date__gt=participant.date_removed):
						models.log_obj_delete(request.user, klb_result.race.event, child_object=klb_result,
							action_type=models.ACTION_KLB_RESULT_DELETE, comment=u'При изменении дат участия в КЛБМатче')
						deleted_race_ids.append(klb_result.race.id)
						if team:
							prev_score = team.score
							team.refresh_from_db()
							models.Klb_team_score_change.objects.create(
								team=team,
								race=klb_result.race,
								clean_sum=team.score - team.bonus_score,
								bonus_sum=team.bonus_score,
								delta=team.score - prev_score,
								n_persons_touched=1,
								comment=u'Изменение даты исключения участника {} {} из команды на {}'.format(person.fname, person.lname, participant.date_removed.isoformat()),
								added_by=request.user,
							)
						klb_result.delete()
				if deleted_race_ids:
					messages.warning(request, u'Удалены КЛБ-результаты со стартов со следующими id: {}'.format(', '.join(unicode(x) for x in deleted_race_ids)))
					update_participant_score(participant, to_update_team=True)
					if participant.team:
						fill_match_places(year=year, fill_age_places=False)
				return redirect(person.get_editor_url())
			else:
				messages.warning(request, u"Данные об участии в КЛБМатче-{} не обновлены. Пожалуйста, исправьте ошибки в форме.".format(year))
		else: # We should create new participant
			participant = models.Klb_participant(added_by=request.user, klb_person=person, match_year=year)
			form = forms.KlbParticipantForm(request.POST, instance=participant, year=year)
			if form.is_valid():
				team = form.instance.team
				team_limit = models_klb.get_team_limit(year)
				if (team is None) or (team.n_members < team_limit):
					participant = form.save()
					participant.fill_age_group()
					log_form_change(request.user, form, models.ACTION_KLB_PARTICIPANT_CREATE, obj=person, child_id=participant.id)
					person.update_person_contact_fields_and_prepare_letter(request.user, team, participant.email, participant.phone_number,
						prepare_letter=True, year=year)

					if ('and_to_club_members' in request.POST) and team:
						if participant.date_registered:
							date_from = max(participant.date_registered, datetime.date(year, 1, 1))
						else:
							date_from = datetime.date(year, 1, 1)
						if participant.date_removed:
							date_to = min(participant.date_removed, datetime.date(year, 12, 31))
						else:
							date_to = datetime.date(year, 12, 31)
						club_member, is_changed = person.runner.add_to_club(request.user, team.club, participant, date_from, date_to)
						if is_changed:
							update_runner_stat(club_member=club_member)

					messages.success(request, u'Участник успешно добавлен в КЛБМатч-{}'.format(year))
					if participant.team:
						update_team_score(participant.team, to_calc_sum=True)
					return redirect(person.get_editor_url())
				else:
					messages.warning(request, u"В команде «{}» достигнут лимит участников ({} человек).".format(team.name, team_limit))
			else:
				messages.warning(request, u"Данные об участии в КЛБМатче-{} не обновлены. Пожалуйста, исправьте ошибки в форме.".format(year))
	elif 'frmParticipant_delete' in request.POST:
		if participant:
			deleted_race_ids = []
			team = participant.team
			for klb_result in person.klb_result_set.filter(race__event__start_date__year=year):
					models.log_obj_delete(request.user, klb_result.race.event, child_object=klb_result,
						action_type=models.ACTION_KLB_RESULT_DELETE, comment=u'При удалении человека из КЛБМатча')
					deleted_race_ids.append(klb_result.race.id)
					klb_result.delete()
			if deleted_race_ids:
				messages.warning(request, u'Удалены КЛБ-результаты со стартов со следующими id: {}'.format(
					', '.join(unicode(x) for x in deleted_race_ids)))
			models.log_klb_participant_delete(request.user, participant)
			participant.delete()
			messages.success(request, u'Участник удалён из КЛБМатча')
			if team:
				update_team_score(team, to_calc_sum=(len(deleted_race_ids) > 0))
				fill_match_places(year=year, fill_age_places=False)
			return redirect(person.get_editor_url())
		else: # We should create new participant
			messages.warning(request, u"Этот человек и так не участвует в КЛБМатче-{}".format(year))
	else:
		form = None
	return klb_person_details(request, person_id=person_id, person=person, frmParticipant=form)

@group_required('admins')
def klb_person_create(request, runner_id):
	runner = get_object_or_404(models.Runner, pk=runner_id)
	if runner.klb_person:
		messages.warning(request, u'К бегуну {} {} (id {}) уже привязан участник КЛБМатча. Вот его страница'.format(
			runner.fname, runner.lname, runner.id))
		return redirect(runner.klb_person)
	person = models.Klb_person(
		added_by=request.user,
		gender=runner.gender,
		city=runner.city,
		lname=runner.lname,
		fname=runner.fname,
		midname=runner.midname,
		birthday=runner.birthday if runner.birthday_known else None,
	)
	if (request.method == 'POST') and 'frmPerson_submit' in request.POST:
		form = forms.KlbPersonForm(request.POST, instance=person)
		if form.is_valid():
			person = form.save()
			runner.klb_person = person
			runner.save()
			log_form_change(request.user, form, action=models.ACTION_CREATE)
			messages.success(request, u'Участник КЛБМатча {} {} успешно создан. Проверьте, всё ли правильно.'.format(
				person.fname, person.lname))
			return redirect(person)
		else:
			messages.warning(request, u"Участник КЛБМатча не создан. Пожалуйста, исправьте ошибки в форме.")
	else:
		form = None
	return klb_person_details(request, person=person, frmPerson=form, runner=runner)

@group_required('admins')
def klb_person_refresh_stat(request, person_id):
	person = get_object_or_404(models.Klb_person, pk=person_id)
	n_results_changed_total = 0
	for participant in person.klb_participant_set.all():
		year = participant.match_year
		if models.is_active_klb_year(year, True):
			age_group_res = participant.fill_age_group()
			if age_group_res == -1:
				messages.warning(request, u'Не удалось заполнить участнику группу за {} год!'.format(year))
			else:
				if age_group_res:
					messages.success(request, u'Группа участника в КЛБМатче–{} изменена'.format(year))
				n_results_changed = 0
				team = participant.team
				for klb_result in person.klb_result_set.filter(race__event__start_date__year=year):
					if recalc_klb_result(klb_result, request.user, comment=u'При пересчёте всех результатов участника КЛБМатча'):
						n_results_changed += 1
						if team:
							prev_score = team.score
							team.refresh_from_db()
							models.Klb_team_score_change.objects.create(
								team=team,
								race=klb_result.race,
								clean_sum=team.score - team.bonus_score,
								bonus_sum=team.bonus_score,
								delta=team.score - prev_score,
								n_persons_touched=1,
								comment=u'Пересчёт администратором всех очков участника {} {}'.format(person.fname, person.lname),
								added_by=request.user,
							)
				if n_results_changed:
					n_results_changed_total += n_results_changed
					update_participant_score(participant, to_calc_sum=True, to_update_team=True)
				messages.success(request, u"Статистика участника и его команды в КЛБМатче–{} обновлена.".format(year))
	if n_results_changed_total:
		messages.success(request, u'Изменилось результатов у бегуна: {}'.format(n_results_changed_total))
	else:
		messages.warning(request, u'Ни одного результата не изменилось')
	return redirect(person)

@group_required('admins')
def klb_person_changes_history(request, person_id):
	person = get_object_or_404(models.Klb_person, pk=person_id)
	context = user_edit_vars(request.user)
	return changes_history(request, context, person, person.get_absolute_url())

# Tries to move all participations and results of person1 to person 2.
# Returns <success?>, <error message if not>
def try_only_merge_klb_persons(user, person1, person2):
	years1 = set(person1.klb_participant_set.values_list('match_year', flat=True))
	years2 = set(person2.klb_participant_set.values_list('match_year', flat=True))
	common_years = years1 & years2
	if common_years:
		return False, u'Участники КЛБМатчей с id {} и {} оба участвовали в КЛБМатче-{}. Не объединяем'.format(
			person1.id, person2.id, u', '.join(common_years))
	FIRST_YEAR_NOT_USING_OLD_TABLES = 2015
	if min(years1) < FIRST_YEAR_NOT_USING_OLD_TABLES:
		if min(years2) < FIRST_YEAR_NOT_USING_OLD_TABLES:
			return False, u'Участники КЛБМатчей с id {} и {} оба участвовали в КЛБМатчах до {} года. Таких объединять не умеем'.format(
				person1.id, person2.id, FIRST_YEAR_NOT_USING_OLD_TABLES)
		person1, person2 = person2, person1
	# So person1 has no participations before 2015 and can be deleted
	person1.klb_participant_set.update(klb_person=person2)
	person1.klb_result_set.update(klb_person=person2)
	return True, ''

def try_merge_klb_persons_and_runners(user, person1, person2):
	success, msg = try_only_merge_klb_persons(user, person1, person2)
	if not success:
		return False, msg
	if person1.klb_participant_set.exists():
		return False, u'Возникла ошибка: у участника КЛБМатчей с id {} остались записи в Klb_participant! Ничего не делаем'.format(person1.id)
	if person1.klb_result_set.exists():
		return False, u'Возникла ошибка: у участника КЛБМатчей с id {} остались записи в Klb_result! Ничего не делаем'.format(person1.id)
	models.log_obj_delete(user, person1)
	runner1 = person1.runner
	runner2 = person2.runner
	person1_id = person1.id
	person1.delete()
	runner1.refresh_from_db()
	success, msg = runner2.merge(runner1, user)
	if not success:
		return False, u'Мы удалили участника КЛБМатчей с id {}, но не смогли заменить бегуна с id {} на бегуна {}: {}. Сделайте это!'.format(
			person1_id, runner1.id, runner2.id, msg)
	return True, ''

@group_required('admins')
def klb_person_delete(request, person_id):
	person = get_object_or_404(models.Klb_person, pk=person_id)
	has_dependent_objects = person.has_dependent_objects()
	ok_to_delete = False
	form = None
	if 'frmForPerson_submit' in request.POST:
		if has_dependent_objects:
			new_person_id = models.int_safe(request.POST.get('new_person_id'))
			if new_person_id:
				if new_person_id != person.id:
					new_person = models.Klb_person.objects.filter(pk=new_person_id).first()
					if new_person:
						success, msg = try_merge_klb_persons_and_runners(request.user, person, new_person)
						if success:
							messages.success(request, u'Участники КЛБМатчей успешно объединены')
							return redirect(new_person)
						else:
							messages.warning(request, u'Не удалось объединить бегунов. Ошибка: {}'.format(msg))
					else:
						messages.warning(request, u'Бегун, на которого нужно заменить текущего, не найден.')
				else:
					messages.warning(request, u'Нельзя заменить участника КЛБМатчей на него же.')
			else:
				messages.warning(request, u'Участник КЛБМатчей, на которого нужно заменить текущего, не указан.')
		else: # There are no results for person, so we just delete him
			ok_to_delete = True
	else:
		messages.warning(request, u"Вы не указали бегуна для удаления.")

	if ok_to_delete:
		# if has_dependent_objects:
		# 	update_person(request, person, new_person)
		models.log_obj_delete(request.user, person)
		runner = person.runner if hasattr(person, 'runner') else None
		messages.success(request, u'Участник КЛБМатчей «{}» успешно удалён.'.format(person))
		person.delete()
		if has_dependent_objects:
			return redirect(new_person)
		elif runner:
			return redirect(runner)
		else:
			return redirect('results:klb_match_summary')
	return klb_person_details(request, person_id=person_id, person=person)

@login_required
def klb_participant_for_captain_details(request, participant_id):
	participant = get_object_or_404(models.Klb_participant, pk=participant_id, team__isnull=False)
	person = participant.klb_person
	team = participant.team
	club = team.club
	context, has_rights, target = check_rights(request, club=club)
	if not has_rights:
		return target
	if not models.is_active_klb_year(team.year, context['is_admin']):
		messages.warning(request, u'Вы уже не можете изменять контактные данные членов команды {} года. Тот матч давно в прошлом.'.format(team.year))
		return redirect(team)

	if 'frmParticipant_submit' in request.POST:
		form = forms.KlbParticipantForTeamCaptainForm(request.POST, instance=participant)
		if form.is_valid():
			participant = form.save()
			log_form_change(request.user, form, models.ACTION_KLB_PARTICIPANT_UPDATE, obj=participant.klb_person, child_id=participant.id)
			messages.success(request, u'Данные об участнике {} {} в КЛБМатче-{} успешно обновлены. Изменены следующие поля: {}'.format(
				person.fname, person.lname, team.year, ", ".join(form.changed_data)))
			person.update_person_contact_fields_and_prepare_letter(request.user, team, participant.email, participant.phone_number)
			return redirect(team.get_contact_info_url())
		else:
			messages.warning(request, u"Данные об участнике {} {} в КЛБМатче-{} не обновлены. Пожалуйста, исправьте ошибки в форме.".format(
				person.fname, person.lname, team.year))
	else:
		form = forms.KlbParticipantForTeamCaptainForm(instance=participant)

	context['form'] = form
	context['team'] = team
	context['person'] = person
	context['participant'] = participant
	context['page_title'] = u'Изменение контактных данных участника {} {} в КЛБМатче-{}'.format(person.fname, person.lname, team.year)
	context = team.update_context_for_team_page(context, request.user)
	return render(request, "klb/participant_for_captain_details.html", context)
