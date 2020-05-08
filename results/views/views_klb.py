# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q, F, Sum, Count, Value, CharField
from django.core.urlresolvers import reverse
from django.db.models.query import Prefetch
from django.contrib import messages
from collections import OrderedDict
import datetime

from results import models, forms, models_klb
from results.results_util import plural_ending_11
from .views_common import user_edit_vars, paginate_and_render
from editor.views.views_common import group_required
from editor.views.views_klb_stat import get_klb_score, update_participant_score, update_team_score, fill_match_places
from editor.views.views_stat import get_stat_value

import os.path

def add_races_annotations(races):
	return races.select_related('distance').order_by('distance__distance_type', '-distance__length')

def event_races_for_context(event):
	return add_races_annotations(event.race_set)

def get_cur_participant_ids(user): # Returns current user's participant IDs in active matches
	result = []
	if user.is_authenticated:
		if hasattr(user, 'runner'):
			person = user.runner.klb_person
			if person:
				years = [models.CUR_KLB_YEAR]
				if models.NEXT_KLB_YEAR:
					years.append(models.NEXT_KLB_YEAR)
				for year in years:
					participant = person.klb_participant_set.filter(match_year=year).first()
					if participant and (participant.team is None):
						result.append(participant.id)
	return result

def klb_person_details(request, person_id):
	person = get_object_or_404(models.Klb_person, pk=person_id)
	user = request.user
	context = user_edit_vars(user)
	context['person'] = person
	context['participations'] = person.klb_participant_set.order_by('-match_year').select_related(
		'team__club__city__region__country').prefetch_related('klb_participant_stat_set')
	klb_results = OrderedDict()
	for klb_result in person.klb_result_set.select_related('race__event', 'result').order_by('-race__event__start_date'):
		year = klb_result.race.event.start_date.year
		if year in klb_results:
			klb_results[year]['results'].append(klb_result)
		else:
			klb_results[year] = {'old_link': person.get_old_url(year), 'results': [klb_result]}
	context['klb_results'] = klb_results
	context['page_title'] = u'Участник КЛБМатчей: {} {}'.format(person.fname, person.lname)
	context['cur_year_participant'] = person.klb_participant_set.filter(match_year=models.CUR_KLB_YEAR).first()
	context['cur_year'] = models.CUR_KLB_YEAR
	context['cur_participant_ids'] = get_cur_participant_ids(user)
	context['diplom_year'] = models.KLB_DIPLOM_YEAR if \
		(models.KLB_DIPLOM_YEAR and person.klb_participant_set.filter(match_year=models.KLB_DIPLOM_YEAR).exists()) else False
	return render(request, 'klb/person_details.html', context)

KLB_TABS = ['all', 'medium', 'small']
KLB_TAB_DEFAULT = 'all'
def klb_match_summary(request, year=models.CUR_KLB_YEAR, tab=KLB_TAB_DEFAULT):
	user = request.user
	context = user_edit_vars(user)
	year = models.int_safe(year)
	if (year < 2010) or (year > max(models.CUR_KLB_YEAR, models.NEXT_KLB_YEAR)):
		year = models.CUR_KLB_YEAR
	if (year == models.NEXT_KLB_YEAR) and not (models.NEXT_KLB_YEAR_AVAILABLE_FOR_ALL or context['is_admin']):
		year = models.CUR_KLB_YEAR
	context['active_tab'] = tab if (tab in KLB_TABS) else KLB_TAB_DEFAULT
	N_PERSONS_PER_TABLE = 3
	teams = models.Klb_team.objects.filter(year=year).exclude(number=models.INDIVIDUAL_RUNNERS_CLUB_NUMBER).select_related(
		'club__city__region__country')
	if context['is_admin']:
		context['teams_not_paid_ids'] = set(models.Klb_participant.objects.exclude(team=None).filter(match_year=year,
			paid_status=models.PAID_STATUS_NO).values_list('team_id', flat=True))
	else:
		teams = teams.filter(n_members__gt=0)

	context['teams_all'] = teams.order_by('place', 'name')
	context['teams_medium'] = teams.filter(place_medium_teams__isnull=False).order_by('place_medium_teams', 'name')
	context['teams_small'] = teams.filter(place_small_teams__isnull=False).order_by('place_small_teams', 'name')
	if year >= 2019:
		context['teams_secondary'] = teams.filter(place_secondary_teams__isnull=False).order_by('place_secondary_teams', 'name')

	context['groups'] = []
	all_participants = models.Klb_participant.objects.filter(match_year=year, place__isnull=False)
	for group in list(models.Klb_age_group.get_groups_by_year(year)):
		if group.gender == models.GENDER_UNKNOWN:
			participants = all_participants.order_by('place')
		elif group.birthyear_min is None:
			participants = all_participants.filter(klb_person__gender=group.gender, place_gender__isnull=False).order_by('place_gender')
		else:
			participants = group.klb_participant_set.filter(place_group__isnull=False).order_by('place_group')
		context['groups'].append({
			'group': group,
			'participants': participants.exclude(n_starts=0).select_related('klb_person__city__region__country', 'team')[:N_PERSONS_PER_TABLE]
		})

	context['stats'] = []
	for category in models.Klb_match_category.objects.filter(year=year).order_by('stat_type'):
		context['stats'].append({
			'category': category,
			'stats': models.Klb_participant_stat.objects.filter(klb_participant__match_year=year, stat_type=category.stat_type, place__isnull=False
				).select_related('klb_participant__klb_person__city', 'klb_participant__team').order_by('place')[:N_PERSONS_PER_TABLE]
		})

	context['page_title'] = u'КЛБМатч–{}: Текущие результаты'.format(year)
	context['year'] = year
	context['is_active_klb_year'] = models.is_active_klb_year(year, context['is_admin'])
	context['individual_participants'] = models.Klb_participant.objects.filter(match_year=year, team=None).select_related(
		'klb_person__city').order_by('-score_sum', 'klb_person__lname', 'klb_person__fname')
	context['cur_participant_ids'] = get_cur_participant_ids(user)
	context['small_team_size'] = models_klb.get_small_team_limit(year)
	context['medium_team_size'] = models_klb.get_medium_team_limit(year)
	context['regulations_link'] = models_klb.get_regulations_link(year)
	context['old_match_link'] = models_klb.get_old_match_link(year)
	context['show_link_on_winners_by_regions'] = (models.FIRST_YEAR_WITH_KLBMATCH_STAT_BY_REGIONS <= year < models.CUR_KLB_YEAR)

	context['large_teams_count'] = models.Klb_team.get_large_teams_number(year)
	context['medium_teams_count'] = models.Klb_team.get_medium_teams_number(year)
	context['small_teams_count'] = models.Klb_team.get_small_teams_number(year)
	return render(request, 'klb/match_summary.html', context)

FIRST_YEAR_WITH_INVITATION = 2017
def about_match(request, year=models.CUR_KLB_YEAR):
	year = models.int_safe(year)
	context = user_edit_vars(request.user)
	if (year < FIRST_YEAR_WITH_INVITATION) or ((year > models.CUR_KLB_YEAR) and not models.is_active_klb_year(year, context['is_admin'])):
		year = models.CUR_KLB_YEAR
	elif year < models.CUR_KLB_YEAR:
		context['this_is_old_match'] = True

	year_for_results = models.CUR_KLB_YEAR
	N_PERSONS_PER_TABLE = 3
	teams = models.Klb_team.objects.filter(year=year_for_results).exclude(number=models.INDIVIDUAL_RUNNERS_CLUB_NUMBER).select_related('club')
	if not context['is_admin']:
		teams = teams.filter(n_members_started__gt=0)
	context['teams_all'] = teams.order_by('place')
	context['teams_medium'] = teams.filter(place_medium_teams__isnull=False).order_by('place_medium_teams')
	context['teams_small'] = teams.filter(place_small_teams__isnull=False).order_by('place_small_teams')
	context['groups'] = []
	all_participants = models.Klb_participant.objects.filter(match_year=year_for_results, place__isnull=False)
	for group in list(models.Klb_age_group.get_groups_by_year(year_for_results)):
		if group.gender == models.GENDER_UNKNOWN:
			participants = all_participants.order_by('place')
		elif group.birthyear_min is None:
			participants = all_participants.filter(klb_person__gender=group.gender, place_gender__isnull=False).order_by('place_gender')
		else:
			participants = group.klb_participant_set.filter(place_group__isnull=False).order_by('place_group')
		context['groups'].append({
			'group': group,
			'participants': participants.select_related('klb_person__city', 'team')[:N_PERSONS_PER_TABLE]
		})
	context['page_title'] = u'Приглашение на КЛБМатч–{}'.format(year)
	context['year'] = year
	context['year_for_results'] = year_for_results
	context['small_team_size'] = models_klb.get_small_team_limit(year_for_results)
	context['medium_team_size'] = models_klb.get_medium_team_limit(year_for_results)
	context['regulations_link'] = models_klb.get_regulations_link(year)
	context['regulations_changes_link'] = models_klb.get_regulations_changes_link(year)
	context['n_results'] = get_stat_value('n_results')
	return render(request, 'klb/about_match_{}.html'.format(year), context)

def application(request, year=models.CUR_KLB_YEAR):
	context = user_edit_vars(request.user)
	year = models.int_safe(year)
	if (year < datetime.date.today().year) or not models.is_active_klb_year(year, context['is_admin']):
		year = models.CUR_KLB_YEAR
	if (year < datetime.date.today().year) and models.NEXT_KLB_YEAR:
		year = models.NEXT_KLB_YEAR
	context['year'] = year
	context['was_participant'] = False
	user = request.user
	absent_fields = []
	to_create_runner = to_create_person = to_create_participant = False

	if user.is_authenticated:
		context['authenticated'] = True
		if hasattr(user, 'runner'):
			runner = user.runner
			person = runner.klb_person
			if person:
				if person.klb_participant_set.filter(match_year=year).exists():
					messages.warning(request, u'Вы уже заявлены в КЛБМатч–{}. Успешных стартов!'.format(year))
					return redirect(reverse('results:klb_match_summary', kwargs={'year': year}))
				if person.klb_participant_set.exists():
					context['was_participant'] = True
			else:
				to_create_person = True
		else:
			to_create_runner = True
		if not user.last_name.strip():
			absent_fields.append(u'Фамилия')
		if not user.first_name.strip():
			absent_fields.append(u'Имя')
		if not user.email.strip():
			absent_fields.append(u'Адрес электронной почты')
		if hasattr(user, 'user_profile'):
			profile = user.user_profile
			if not profile.email_is_verified:
				context['email_not_verified'] = True
			if not profile.midname.strip():
				absent_fields.append(u'Отчество')
			if profile.gender == models.GENDER_UNKNOWN:
				absent_fields.append(u'Пол')
			if profile.birthday is None:
				absent_fields.append(u'Дата рождения')
			if profile.city is None:
				absent_fields.append(u'Город')
		else:
			absent_fields += [u'Отчество', u'Пол', u'Дата рождения', u'Город']
		context['absent_fields'] = ', '.join(absent_fields)
		if len(absent_fields) == 1:
			context['absent_field'] = absent_fields[0]
	else:
		context['authenticated'] = False

	if context['authenticated'] and (not absent_fields) and ('submit_register' in request.POST):
		comment = u'При индивидуальной заявке в КЛБМатч–{}'.format(year)
		if to_create_runner:
			runner = profile.create_runner(user, comment=comment)
			to_create_person = True
		if to_create_person:
			person = runner.create_klb_person(user, comment=comment)
		if (request.POST.get('was_participant', '') == 'yes') and (not context['was_participant']):
			comment += u'. Пишет, что уже участвовал!'
		elif (request.POST.get('was_participant', '') == 'no') and (context['was_participant']):
			comment += u'. Пишет, что раньше не участвовал!'

		disability_group = models.int_safe(request.POST.get('disability_group', 0))
		if not (0 <= disability_group <= 3):
			disability_group = 0
		participant, _, _ = person.create_participant(None, user, year=year, comment=comment, email=user.email, phone_number=profile.phone_number,
			disability_group=disability_group)
		# if context['is_admin'] or (request.user.id == 3231):
		return redirect(reverse('results:klb_application_payment', kwargs={'year': year}))
		# messages.success(request, u'Вы успешно заявлены в КЛБМатч–{}. Мы напишем Вам письмо до конца января, как оплатить участие в матче'.format(year))
		# return redirect(reverse('results:klb_match_summary', kwargs={'year': year}))
	context['page_title'] = u'Подача индивидуальной заявки в КЛБМатч–{}'.format(year)
	context['regulations_link'] = models_klb.get_regulations_link(year)
	context['disability_groups'] = models.DISABILITY_GROUPS
	return render(request, 'klb/application_{}.html'.format(year), context)

@login_required
def application_payment(request, year=models.CUR_KLB_YEAR):
	context = user_edit_vars(request.user)
	year = models.int_safe(year)
	if not models.is_active_klb_year(year, context['is_admin']):
		year = models.CUR_KLB_YEAR
	context['year'] = year
	context['price'] = models_klb.get_participation_price(year)

	participant = models.Klb_participant.objects.filter(klb_person__runner__user_id=request.user.id, match_year=year).first()
	if not participant:
		messages.warning(request, u'Вы ещё не заявлены в КЛБМатч–{}'.format(year))
		return redirect(reverse('results:klb_application', kwargs={'year': year}))

	person = participant.klb_person
	if participant.paid_status != models.PAID_STATUS_NO:
		messages.warning(request, u'Ваше участие в КЛБМатче–{} уже оплачено. Отлично!'.format(year))
		return redirect(person)
	if participant.team:
		club = participant.team.club
		if not club.members_can_pay_themselves:
			messages.warning(request, u'Ваше участие в КЛБМатче может оплатить только капитан команды; Вам достаточно передать деньги ему.')
			return redirect(person)
		context['club'] = club

	if participant.is_senior:
		context['can_pay_zero'] = True
		age = year - person.birthday.year
		context['reason'] = u'на конец {} года Вам будет {} {}'.format(year, age, plural_ending_11(age))
	elif person.disability_group != 0:
		context['can_pay_zero'] = True
		context['reason'] = u'у Вас {} группа инвалидности'.format(person.disability_group)
	else:
		context['can_pay_zero'] = False
	return render(request, 'klb/application_payment.html', context)

@login_required
def individual_pay_nothing(request, year=models.CUR_KLB_YEAR):
	context = user_edit_vars(request.user)
	year = models.int_safe(year)
	if not models.is_active_klb_year(year, context['is_admin']):
		year = models.CUR_KLB_YEAR
	context['year'] = year
	participant = models.Klb_participant.objects.filter(klb_person__runner__user_id=request.user.id, match_year=year).first()
	if not participant:
		messages.warning(request, u'Вы ещё не заявлены в КЛБМатч–{}'.format(year))
		return redirect(reverse('results:klb_application', kwargs={'year': year}))
	if participant.paid_status != models.PAID_STATUS_NO:
		messages.warning(request, u'Вы уже оплатили участие в КЛБМатче–{}'.format(year))
		return redirect(participant.klb_person)
	if 'btnJoinForFree' not in request.POST:
		return redirect(participant.klb_person)
	payment = models.Payment_moneta.objects.create(
		amount=0,
		is_dummy=True,
		is_paid=True,
		user=request.user,
	)
	payment.transaction_id = models.PAYMENT_DUMMY_PREFIX + unicode(payment.id)
	payment.save()

	participant.payment = payment
	participant.paid_status = models.PAID_STATUS_FREE
	participant.save()
	models.log_obj_create(request.user, participant.klb_person, models.ACTION_KLB_PARTICIPANT_UPDATE, child_object=participant,
		field_list=['payment', 'paid_status'], comment=u'Индивидуальная оплата')
	messages.success(request, u'Отлично, с оплатой разобрались. Пора стартовать!')
	return redirect(participant.klb_person)

@login_required
def remove_from_match(request, year):
	year = models.int_safe(year)
	target = redirect(reverse('results:klb_match_summary', kwargs={'year': year}))
	if not models.is_active_klb_year(year, models.is_admin(request.user)):
		messages.warning(request, u'Участников КЛБМатча–{} сейчас нельзя редактировать'.format(year))
		return target
	participant = None
	user = request.user
	if hasattr(user, 'runner'):
		person = user.runner.klb_person
		if person:
			participant = person.klb_participant_set.filter(match_year=year).first()
	if participant is None:
		messages.warning(request, u'Вы и не были заявлены в КЛБМатч–{}'.format(year))
		return target
	if person.klb_result_set.filter(race__event__start_date__year=year).exists():
		messages.warning(request, (u'У Вас уже есть результаты в зачёт КЛБМатча–{}. Если Вы всё равно хотите отказаться от участия, '
					+ u'пожалуйста, напишите нам на {}').format(year, models.KLB_MAIL))
		return target
	if participant.team:
		messages.warning(request, (u'Вы заявлены в КЛБМатч–{} за команду «{}». '
			+ u'Для отзаявки обратитесь, пожалуйста, к руководителю клуба').format(
			year, participant.team.name))
		return target
	models.log_klb_participant_delete(user, participant)
	participant.delete()
	messages.warning(request, u'Вы успешно отзаявлены из КЛБМатча–{}'.format(year))
	return target

def get_vars_and_participants_with_filter(POST, participants, region_id=None, country_id=None):
	context = {}
	context['group_has_people'] = participants.exists() # When filters show 0 results, we need to show filters anyway!
	if ('frmSearch_submit' in POST) or ('page' in POST) or ('new_ordering' in POST):
		filterForm = forms.KlbParticipantFilterForm(POST, participants=participants)
		if filterForm.is_valid():
			template = filterForm.cleaned_data['template']
			if template:
				participants = participants.filter(
					Q(klb_person__city__name__istartswith=template)
					| Q(klb_person__lname__istartswith=template)
					| Q(klb_person__fname__istartswith=template)
					| Q(team__name__istartswith=template)
				)

			region = filterForm.cleaned_data['region']
			if region:
				participants = participants.filter(klb_person__city__region_id=region)

			country = filterForm.cleaned_data['country']
			if country:
				participants = participants.filter(klb_person__city__region__country_id=country)
			# filterForm.cleaned_data['ordering'] = ordering
			# context['ordering_to_display'] = filterForm.cleaned_data['ordering']
	elif region_id:
		region = get_object_or_404(models.Region, pk=region_id)
		filterForm = forms.KlbParticipantFilterForm(participants=participants, initial={'region': region_id})
		participants = participants.filter(klb_person__city__region_id=region)
	elif country_id:
		country = get_object_or_404(models.Country, pk=country_id)
		filterForm = forms.KlbParticipantFilterForm(participants=participants, initial={'country': country_id})
		participants = participants.filter(klb_person__city__region__country_id=country)
	else:
		filterForm = forms.KlbParticipantFilterForm(participants=participants)#(initial={'ordering': ordering})
	context['filterForm'] = filterForm
	return context, participants

def klb_age_group_details(request, age_group_id=None, year=None, region_id=None, country_id=None, show_all=0):
	show_all = models.int_safe(show_all)
	frmAgeGroup = None
	if age_group_id:
		age_group = get_object_or_404(models.Klb_age_group, pk=age_group_id)
	else:
		age_group = get_object_or_404(models.Klb_age_group, match_year=year, birthyear_min=None, birthyear_max=None, gender=models.GENDER_UNKNOWN)
	year = age_group.match_year
	context = user_edit_vars(request.user)
	context['age_group'] = age_group
	context['year'] = year
	context['page_title'] = u'Участники: {}'.format(age_group.name)

	context['frmAgeGroup'] = forms.KlbAgeGroupForm(initial={'age_group': age_group})
	context['frmMatchCategory'] = forms.KlbMatchCategoryForm(year=year)

	ordering_list = []
	ordering = ''
	if 'new_ordering' in request.POST:
		ordering = request.POST['new_ordering']
	elif 'ordering' in request.POST:
		ordering = request.POST['ordering']
	else:
		ordering = 'place'
	context['ordering'] = ordering
	if ordering == 'name':
		ordering_list.append('klb_person__lname')
		ordering_list.append('klb_person__fname')
	elif ordering == 'city':
		ordering_list.append('klb_person__city__name')
	elif ordering == 'birthday':
		ordering_list.append('klb_person__birthday')
	elif ordering == 'team':
		ordering_list.append('team__name')
	elif ordering == 'n_starts':
		ordering_list.append('-n_starts')
	elif ordering == 'clean_sum':
		ordering_list.append('-clean_sum')
	elif ordering == 'bonus_sum':
		ordering_list.append('-bonus_sum')
	for x in ['-score_sum', 'klb_person__lname', 'klb_person__fname']:
		if x not in ordering_list:
			ordering_list.append(x)

	if age_group.birthyear_min is None:
		participants = models.Klb_participant.objects.filter(match_year=year)
		if age_group.gender != models.GENDER_UNKNOWN:
			participants = participants.filter(klb_person__gender=age_group.gender)
	else:
		participants = age_group.klb_participant_set
	if '-clean_sum' in ordering_list:
		participants = participants.annotate(clean_sum=F('score_sum')-F('bonus_sum'))

	if age_group.gender == models.GENDER_UNKNOWN:
		participants = participants.annotate(cur_place=F('place'))
	elif age_group.birthyear_min is None:
		participants = participants.annotate(cur_place=F('place_gender'))
	else:
		participants = participants.annotate(cur_place=F('place_group'))
	
	new_vars, participants = get_vars_and_participants_with_filter(request.POST, participants, region_id, country_id)
	context.update(new_vars)

	participants = participants.select_related('klb_person__city__region__country',
		'klb_person__runner__user__user_profile', 'team').order_by(*ordering_list)
	return paginate_and_render(request, 'klb/age_group_details.html', context, participants, show_all=show_all)

def klb_match_category_details(request, match_category_id=None):
	frmMatchCategory = None
	match_category = get_object_or_404(models.Klb_match_category, pk=match_category_id)
	year = match_category.year
	context = user_edit_vars(request.user)
	context['match_category'] = match_category
	context['year'] = year
	context['page_title'] = u'Участники: {}'.format(match_category.get_stat_type_display())

	context['frmAgeGroup'] = forms.KlbAgeGroupForm(year=year)
	context['frmMatchCategory'] = forms.KlbMatchCategoryForm(initial={'match_category': match_category})

	ordering_list = []
	ordering = ''
	if 'new_ordering' in request.POST:
		ordering = request.POST['new_ordering']
	elif 'ordering' in request.POST:
		ordering = request.POST['ordering']
	else:
		ordering = 'place'
	context['ordering'] = ordering
	if ordering == 'name':
		ordering_list.append('klb_participant__klb_person__lname')
		ordering_list.append('klb_participant__klb_person__fname')
	elif ordering == 'city':
		ordering_list.append('klb_participant__klb_person__city__name')
	elif ordering == 'birthday':
		ordering_list.append('klb_participant__klb_person__birthday')
	elif ordering == 'team':
		ordering_list.append('klb_participant__team__name')
	elif ordering == 'n_starts':
		ordering_list.append('-klb_participant__n_starts')
	for x in ['place', 'klb_participant__klb_person__lname', 'klb_participant__klb_person__fname']:
		if x not in ordering_list:
			ordering_list.append(x)

	participant_stats = models.Klb_participant_stat.objects.filter(stat_type=match_category.stat_type,
		klb_participant__match_year=match_category.year, place__gt=0)

	participants = models.Klb_participant.objects.filter(id__in=participant_stats.values_list('klb_participant_id', flat=True))

	new_vars, participants = get_vars_and_participants_with_filter(request.POST, participants)
	context.update(new_vars)

	participant_stats = participant_stats.filter(klb_participant_id__in=participants.values_list('id', flat=True)).select_related(
		'klb_participant__klb_person__city__region__country',
		'klb_participant__klb_person__runner__user__user_profile', 'klb_participant__team').order_by(*ordering_list)
	return paginate_and_render(request, 'klb/match_category_details.html', context, participant_stats)

def calculator(request):
	context = user_edit_vars(request.user)
	context['page_title'] = u'Расчёт очков для КЛБМатча'
	if 'btnCalc' in request.GET:
		form = forms.CalculatorForm(request.GET)
		if form.is_valid():
			birthyear = form.cleaned_data['birthyear']
			gender = form.cleaned_data['gender']
			distance = form.cleaned_data['distance']
			result = form.cleaned_data['result']
			context['distance'] = form.cleaned_data['distance_text']
			context['itra_score'] = models.int_safe(form.cleaned_data['itra_score'])
			context['time'] = models.centisecs2time(result)
			# context['print_about_year_2016'] = not (20 <= (2016 - birthyear) <= 35)
			# context['distance_too_small'] = (distance < models_klb.get_min_distance_for_score(models.CUR_KLB_YEAR))

			context['years'] = {}
			for year in [2019, 2020]:
				data = {}
				time_with_coef, data['score'], data['bonus_score'] = get_klb_score(year, birthyear, gender, distance, result,
					itra_score=context['itra_score'])
				data['time_with_coef'] = models.centisecs2time(time_with_coef)
				if data['score'] >= models_klb.MAX_CLEAN_SCORE:
					context['too_large'] = 1
				context['years'][year] = data
	else:
		form = forms.CalculatorForm()
	context['form'] = form
	return render(request, 'klb/calculator.html', context)

def get_events_not_in_klb(year):
	events_not_in_klb = models.Event.objects.filter(start_date__year=year, invisible=False, cancelled=False, not_in_klb=True).prefetch_related(
		Prefetch('race_set', queryset=models.Race.objects.select_related('distance').order_by('distance__distance_type', '-distance__length'))
	).select_related('series__city__region__country', 'city__region__country').annotate(reason=F('comment'))
	
	countries = ('BY', 'RU', 'UA') if (year <= 2018) else ('BY', 'RU')
	possible_match_event_ids = models.Race.objects.filter(
		Q(distance__distance_type=models.TYPE_MINUTES)
		| (
			Q(distance__distance_type=models.TYPE_METERS,
				distance__length__gte=models_klb.get_min_distance_for_score(year),
				distance__length__lte=models_klb.get_max_distance_for_score(year),
			)
			& ( Q(distance_real__length__gte=models_klb.get_min_distance_for_bonus(year)) | Q(distance_real=None) )
		),
		event__start_date__year=year
	).values_list('event_id', flat=True).distinct()
	events_added_late = models.Event.objects.filter(
		Q(city__region__country_id__in=countries) | Q(series__city__region__country_id__in=countries),
		invisible=False,
		cancelled=False,
		pk__in=possible_match_event_ids,
		start_date__year=year,
		start_date__lt=F('date_added_to_calendar') + datetime.timedelta(days=30)
	).annotate(reason=Value('Добавлен в календарь меньше, чем за 30 дней до события', output_field=CharField()))
	return sorted(list(events_not_in_klb) + list(events_added_late), key=lambda x: x.start_date, reverse=True)

def events_not_in_match(request, year=0):
	year = models.int_safe(year)
	if year < 2017:
		year = models.CUR_KLB_YEAR
	user = request.user
	context = user_edit_vars(user)
	context['year'] = year
	context['page_title'] = u'Забеги, не учитывающиеся в КЛБМатче'
	context['events'] = get_events_not_in_klb(year)
	return render(request, 'klb/events_not_in_match.html', context)

def winners_by_regions(request, year):
	year = models.int_safe(year)
	if not (models.FIRST_YEAR_WITH_KLBMATCH_STAT_BY_REGIONS <= year < models.CUR_KLB_YEAR):
		year = models.CUR_KLB_YEAR - 1
	context = user_edit_vars(request.user)
	context['page_title'] = u'КЛБМатч–{}: Итоги по регионам, федеральным округам и странам'.format(year)
	context['template_name'] = 'klb/winners_by_region/{}.html'.format(year)
	return render(request, 'results/base_template.html', context)

def reports(request, year=0):
	stat_types = (
			models.KLB_REPORT_STAT_TEAMS,
			models.KLB_REPORT_STAT_PARTICIPANTS,
			models.KLB_REPORT_STAT_RESULTS,
			models.KLB_REPORT_STAT_GOOD_DISTANCES
		)
	year = models.int_safe(year)
	if year < 2018:
		year = models.CUR_KLB_YEAR
	user = request.user
	context = user_edit_vars(user)
	context['year'] = year
	context['page_title'] = u'КЛБМатч–{}: Слепки'.format(year)
	
	qs = models.Klb_report.objects.all().order_by('-time_created', 'id')
	if not context['is_admin']:
		qs = qs.filter(is_public=True)
	
	context['reports'] = []
	for item in qs:
		one_report_info = [
			item.year,
			os.path.basename(str(item.file)),
			'{}/{}'.format(models.SITE_URL_OLD, str(item.file)),
			u'Да' if item.is_public else u'Нет',
			item.created_by,
			item.time_created,
			item.id,
		]
		try:
			stat_qs = item.klb_report_stat_set.all()
			for stat_type, _ in models.KLB_REPORT_STATS:
				one_report_info.append(stat_qs.get(stat_type=stat_type).value)
		except models.Klb_report_stat.DoesNotExist:
			one_report_info.extend(['']*4)

		context['reports'].append(one_report_info)

	return render(request, 'klb/reports.html', context)
