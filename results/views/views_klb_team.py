# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q, F, Sum, Count
from django.contrib import messages
import datetime
from calendar import monthrange

from results import models, forms, results_util
from .views_common import user_edit_vars, paginate_and_render
from editor.views.views_common import group_required, get_team_club_year_context_target
from editor.views.views_klb_stat import get_klb_score, update_participant_score, update_team_score, fill_match_places
from results.models_klb import get_participation_price, get_last_month_to_pay_for_teams

def get_last_day_to_pay(year):
	today = datetime.date.today()
	if today.year > year:
		month = 12
	elif today.year < year:
		month = get_last_month_to_pay_for_teams(year)
	else:
		month = max(get_last_month_to_pay_for_teams(year), today.month)
	return datetime.date(year, month, monthrange(year, month)[1])

def klb_team_details_full(request, team_id):
	return klb_team_details(request, team_id, show_all_results=True)

def klb_team_details(request, team_id, show_all_results=False, ordering=models.ORDERING_CLEAN_SCORE):
	ordering = models.int_safe(ordering)
	team = get_object_or_404(models.Klb_team, pk=team_id)
	context = user_edit_vars(request.user, club=team.club)
	participants = team.klb_participant_set.select_related('klb_person')
	context['klb_results'] = []
	for participant in participants.order_by('klb_person__lname', 'klb_person__fname'):
		person = participant.klb_person
		results = person.klb_result_set.filter(event_raw__start_date__year=team.year).select_related('race__event', 'event_raw', 'result')
		if show_all_results:
			results = results.order_by('-event_raw__start_date')
		else:
			results = results.order_by('-klb_score', '-event_raw__start_date')
		if not show_all_results:
			results = results.filter(is_in_best=True)
		context['klb_results'] += [{'participant': participant, 'klb_result': klb_result} for klb_result in results]
	context['page_title'] = u'Команда в КЛБМатче: {}, {} год'.format(team.name, team.year)
	context['show_all_results'] = show_all_results
	if context['is_admin']:
		context['n_seniors'] = participants.filter(is_senior=True).count()
		first_participant = participants.exclude(date_registered=None).order_by('date_registered').first()
		if first_participant:
			context['first_participant_date'] = first_participant.date_registered

	context = team.update_context_for_team_page(context, request.user, ordering=ordering)

	if models.is_active_klb_year(team.year, context['is_admin']) and (context['is_admin'] or context['is_editor']):
		context['n_unpaid_participants'] = team.klb_participant_set.filter(paid_status=models.PAID_STATUS_NO).count()
		if context['n_unpaid_participants']:
			context['last_day_to_pay'] = get_last_day_to_pay(team.year)
			context['n_unpaid_from_all_club_teams'] = models.Klb_participant.objects.filter(team__club=team.club, match_year=team.year,
				paid_status=models.PAID_STATUS_NO).count()
	return render(request, 'klb/team_details.html', context)

def klb_team_score_changes(request, team_id):
	team = get_object_or_404(models.Klb_team, pk=team_id)
	context = user_edit_vars(request.user, club=team.club)
	context['page_title'] = u'Команда «{}» в КЛБМатче–{}: последние изменения очков'.format(team.name, team.year)
	context['team'] = team
	context['score_changes'] = models.Klb_team_score_change.objects.filter(team=team).order_by('-added_time').select_related(
		'race__event__city__region__country', 'race__event__series__city__region__country', 'added_by', 'race__distance')
	return render(request, 'klb/team_score_changes.html', context)

def klb_team_results_for_moderation(request, team_id):
	team = get_object_or_404(models.Klb_team, pk=team_id)
	context = user_edit_vars(request.user, club=team.club)
	context['page_title'] = u'Команда «{}» в КЛБМатче–{}: результаты, ждущие проверки администраторами'.format(team.name, team.year)
	context['team'] = team
	result_actions = models.Table_update.objects.filter(
		action_type__in=(models.ACTION_UNOFF_RESULT_CREATE, models.ACTION_RESULT_UPDATE),
		is_verified=False, is_for_klb=True).select_related('user')
	result_ids = set(result_actions.values_list('child_id', flat=True))
	runner_ids = set(team.klb_participant_set.values_list('klb_person__runner', flat=True))
	context['results_for_moderation'] = []
	for result in models.Result.objects.filter(pk__in=result_ids, runner_id__in=runner_ids).order_by('race__event__start_date', 'race__event__name').select_related(
			'race__event__city__region__country', 'race__event__series__city__region__country', 'loaded_by', 'race__distance', 'runner'):
		context['results_for_moderation'].append((result, result_actions.filter(child_id=result.id).first()))
	context = team.update_context_for_team_page(context, request.user)
	return render(request, 'klb/results_for_moderation.html', context)

@group_required('admins')
def klb_team_refresh_stat(request, team_id):
	team = get_object_or_404(models.Klb_team, pk=team_id)
	if not models.is_active_klb_year(team.year, True):
		messages.warning(request, u"Сейчас нельзя обновлять статистику команд за {} год".format(team.year))
		return redirect(team)
	participants = models.Klb_participant.objects.filter(team=team)
	person_ids = set(participants.values_list('klb_person_id', flat=True))
	models.Klb_result.objects.filter(event_raw__start_date__year=team.year, klb_person_id__in=person_ids).update(is_in_best=False, is_in_best_bonus=False)
	for participant in participants:
		update_participant_score(participant, to_clean=False)
	update_team_score(team, to_calc_sum=True)
	fill_match_places(year=team.year, fill_age_places=False)
	messages.success(request, u"Статистика команды обновлена")
	return redirect(team)

# MAX_N_PARTICIPANTS_PER_PAYMENT = 80

@login_required
def team_or_club_payment(request, team_id=None, club_id=None):
	team, club, team_or_club, year, context, target, participants = get_team_club_year_context_target(request, team_id, club_id)
	if target:
		return target

	unfinished_payment_ids = set(participants.exclude(payment=None).filter(payment__is_paid=False).values_list('payment_id', flat=True))
	context['unfinished_payments'] = models.Payment_moneta.objects.filter(is_active=True, pk__in=unfinished_payment_ids).select_related(
		'user__user_profile').order_by('-added_time')

	context['participants'] = participants.filter(paid_status=models.PAID_STATUS_NO, payment=None).select_related('klb_person').order_by(
		'klb_person__lname', 'klb_person__fname', 'klb_person__midname')
	context['n_participants'] = context['participants'].count()

	if (context['n_participants'] == 0) and (context['unfinished_payments'].count() == 0):
		messages.success(request, u'Участие в матче уже оплачено за {}. Ура!'.format(u'всю команду' if team else u'все команды клуба'))
		return redirect(team_or_club)

	context['page_title'] = u'{} «{}» в КЛБМатче–{}: оплата участия'.format(u'Команда' if team else u'Клуб', team_or_club.name, year)
	context['team'] = team
	context['club'] = club
	context['year'] = year
	context['price'] = get_participation_price(year)
	context['n_paid_participants'] = participants.exclude(paid_status=models.PAID_STATUS_NO).count()
	context['initial_total'] = context['n_participants'] * context['price']
	context['SENIOR_AGE_MALE'] = results_util.SENIOR_AGE_MALE
	context['SENIOR_AGE_FEMALE'] = results_util.SENIOR_AGE_FEMALE
	return render(request, 'klb/team_payment.html', context)
