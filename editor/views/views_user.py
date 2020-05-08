# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.models import User, Group
from django.db.models.query import Prefetch
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count

from collections import Counter
from calendar import monthrange
from collections import OrderedDict
import datetime

from results import models
from editor import forms
from results.views.views_common import user_edit_vars
from .views_common import group_required, changes_history
from .views_stat import update_runner_stat
from .views_klb import create_klb_result
from .views_klb_stat import update_persons_score
from .views_mail import send_user_results_letter, get_context_for_user_letter

N_USERS_BY_DEFAULT = 100
@group_required('admins')
def users(request):
	context = {}
	list_title = u"Пользователи "
	conditions = []

	users = User.objects.select_related('user_profile').prefetch_related('social_auth').order_by('-pk')

	country = None
	region = None
	city = None
	kwargs = {}
	initial = {}

	if 'frmSearchUser_submit' in request.GET:
		form = forms.UserSearchForm(request.GET)
		if form.is_valid():
			lname = form.cleaned_data['lname']
			fname = form.cleaned_data['fname']
			midname = form.cleaned_data['midname']
			email = form.cleaned_data['email']
			birthday_from = form.cleaned_data['birthday_from']
			birthday_to = form.cleaned_data['birthday_to']

			if lname:
				users = users.filter(last_name__icontains=lname)
				conditions.append(u"с «{}» в фамилии".format(lname))
			if fname:
				users = users.filter(first_name__icontains=fname)
				conditions.append(u"с «{}» в имени".format(fname))
			if midname:
				users = users.filter(user_profile__midname__icontains=midname)
				conditions.append(u"с «{}» в отчестве".format(midname))
			if email:
				users = users.filter(email__icontains=email)
				conditions.append(u"с «{}» в электронном адресе".format(email))
			if birthday_from:
				users = users.filter(user_profile__birthday__gte=birthday_from)
				conditions.append(u"родившиеся не раньше {}".format(birthday_from))
			if birthday_to:
				users = users.filter(user_profile__birthday__lte=birthday_to)
				conditions.append(u"родившиеся не раньше {}".format(birthday_to))
	else:
		form = forms.UserSearchForm()
		users = users[:N_USERS_BY_DEFAULT]
		list_title = u'Последние {} зарегистрированных пользователей'.format(N_USERS_BY_DEFAULT)

	context['admin_ids'] = set(Group.objects.get(name="admins").user_set.values_list('id', flat=True))
	context['editor_ids'] = set(Group.objects.get(name="editors").user_set.values_list('id', flat=True))

	context['users'] = users # ('last_name', 'first_name')
	context['frmSearchUser'] = form
	context['list_title'] = list_title + ", ".join(conditions)
	context['page_title'] = u'Пользователи сайта'
	return render(request, 'editor/users.html', context=context)

@group_required('admins')
def user_changes_history(request, user_id):
	user = get_object_or_404(User, pk=user_id)
	profile = get_object_or_404(models.User_profile, user=user)
	context = user_edit_vars(request.user)
	return changes_history(request, context, profile, profile.get_absolute_url(), obj_id=user.id)

def make_klb_result(table_update, user, only_bonus_score=False): # Only if is_for_klb=True
	result = models.Result.objects.filter(pk=table_update.child_id).first()
	if not result:
		return False, u'Результат с id {} не найден'.format(table_update.child_id), None
	runner = result.runner
	if not runner:
		return False, u'Бегун у результата с id {} не найден'.format(result.id), None
	person = runner.klb_person
	if not person:
		return False, u'Бегун {} {} (id {}) не участвовал в КЛБМатчах'.format(runner.fname, runner.lname, runner.id), None

	race = result.race
	event = race.event
	race_date = race.start_date if race.start_date else event.start_date
	year = race_date.year
	if not models.is_active_klb_year(year, True):
		return False, u'Забег {} (id {}) относится к году {}. Забеги этого года не могут быть учтены в КЛБМатче'.format(event.name, event.id, year), None
	participant = person.klb_participant_set.filter(match_year=year).first()
	if not participant:
		return False, u'Участник КЛБМатчей {} {} (id {}) не участвует в текущем КЛБМатче'.format(person.fname, person.lname, person.id), None
	if not ( ((participant.date_registered is None) or (participant.date_registered <= race_date)) \
			and ((participant.date_removed is None) or (participant.date_removed >= race_date)) ):
		return False, u'Участник КЛБМатчей {} {} (id {}) не участвовал в КЛБМатче в день забега {} (id {})'.format(
			person.fname, person.lname, person.id, event.name, event.id), None
	if models.Klb_result.objects.filter(race__event=result.race.event, klb_person=person).exists():
		return False, u'У участника КЛБМатчей {} {} (id {}) уже есть в зачёте результат на забеге «{}» (id {})'.format(
			person.fname, person.lname, person.id, event.name, event.id), None
	klb_result = create_klb_result(result, person, user, only_bonus_score=only_bonus_score, participant=participant,
		comment=u'При одобрении действия с id {} администратором'.format(table_update.id))
	return True, '', (result.race, race_date.year, person, participant.team)

def are_words_equivalent(a, b):
	return a.lower().replace(u'ё', u'е') == b.lower().replace(u'ё', u'е')

# Returns True if the name is a default one, 2 if the name is one of extra names, False otherwise
def is_name_ok(runner, fname, lname):
	if are_words_equivalent(fname, runner.fname) and are_words_equivalent(lname, runner.lname):
		return True, ''
	if are_words_equivalent(lname, runner.fname) and are_words_equivalent(fname, runner.lname):
		return 2, u'переставлены имя и фамилия'
	if runner.extra_name_set.filter(fname=fname, lname=lname).exists() or runner.extra_name_set.filter(fname=lname, lname=fname).exists():
		return 2, u'дополнительное имя'
	return False, ''

def is_age_ok(result_age, runner_age):
	if result_age == runner_age:
		return True, ''
	if abs(result_age - runner_age) == 1:
		return 2, u'почти'
	return False, ''

def get_table_updates_by_model(model, exclude_types=[], updates_limit=0, **kwargs):
	kwargs['model_name'] = model.__name__
	res = models.Table_update.objects.filter(**kwargs).select_related('user').prefetch_related('field_update_set').annotate(
		n_messages=Count('message_from_site')).order_by('-is_for_klb', 'row_id', 'added_time')
	if exclude_types:
		res = res.exclude(action_type__in=exclude_types)
	if updates_limit:
		res = res[:2 * updates_limit]
	return res

def get_table_update_tuples_filtered_by_model(model, args_for_model=[], exclude_types=[], kwargs_for_model={},
		related_for_model=[], updates_limit=0, **kwargs):
	model_name = model.__name__.lower()
	res = []
	for table_update in get_table_updates_by_model(model, exclude_types, updates_limit=updates_limit, **kwargs):
		obj = model.objects.filter(pk=table_update.row_id, *args_for_model, **kwargs_for_model).select_related(*related_for_model).first()
		if obj:
			row = {'table_update': table_update, model_name: obj}
			if table_update.action_type in [models.ACTION_UNOFF_RESULT_CREATE, models.ACTION_RESULT_UPDATE]:
				result = models.Result.objects.filter(pk=table_update.child_id).select_related('runner__city').first()
				row['result'] = result
				if result:
					runner = result.runner
					if runner:
						row['runner'] = runner
						row['name_is_ok'], row['name_message'] = is_name_ok(runner, result.fname, result.lname)
						if result.birthday_known:
							if runner.birthday_known:
								row['birthday_is_ok'] = (result.birthday == runner.birthday)
							elif runner.birthday:
								row['birthday_is_ok'] = (result.birthday.year == runner.birthday.year)
						elif result.birthday and runner.birthday:
							row['birthday_is_ok'] = (result.birthday.year == runner.birthday.year)
						if result.age and runner.birthday_known:
							row['age_is_ok'], row['age_message'] = is_age_ok(result.age, result.get_runner_age())
					if table_update.is_for_klb:
						start_date = result.race.event.start_date
						if table_update.added_time.date() >= (start_date + datetime.timedelta(days=91)):
							row['too_late'] = True
						if runner and runner.klb_person:
							klb_person = runner.klb_person
							klb_participant = klb_person.get_participant(start_date.year)
							if klb_participant:
								team = klb_participant.team
								row['team'] = team
								if team and result.club_name:
									row['user_set_correct_club'], row['user_club'], row['date_joined'] = \
										klb_participant.did_user_set_correct_club(start_date)
									if not row['user_set_correct_club']:
										row['club_is_ok'] = team.string_contains_team_or_club_name(result.club_name)
										row['has_problem_with_club'] = not row['club_is_ok']
										if row['date_joined']:
											row['registered_late'] = (row['date_joined'] > start_date)
						if table_update.action_type == models.ACTION_UNOFF_RESULT_CREATE:
							if not result.race.event.document_set.filter(document_type__in=models.DOC_PROTOCOL_TYPES).exists():
								row['has_no_protocol'] = True
			res.append(row)
			if updates_limit and len(res) >= updates_limit:
				break
	return res

N_RESULTS_TO_SHOW = 100
@group_required('admins')
def action_history(request):
	unverified = True
	context = {}
	context['N_RESULTS_TO_SHOW'] = N_RESULTS_TO_SHOW
	kwargs = {}
	kwargs_series = {}
	args_event = []
	kwargs_news = {}
	country = region = city = None
	list_title = u"Действия"
	conditions = []
	all_types = True
	object_type = ''
	action_type = ''
	if request.method == 'POST':
		form = forms.ActionSearchForm(request.POST)
		if 'frmActions_submit' in request.POST:
			objects_verified = 0
			objects_errors = 0
			klb_results_created = 0
			extra_names_added = 0
			teams_by_race = {}
			persons_by_year = {}
			for key, val in request.POST.items():
				model_name = 'table_update'
				if key.startswith(model_name + "_"):
					table_update_id = models.int_safe(key[(len(model_name) + 1):])
					table_update = models.Table_update.objects.filter(pk=table_update_id, is_verified=False).first()
					if table_update:
						res, msgError = table_update.verify(request.user)
						if res:
							objects_verified += 1
							if table_update.is_for_klb and ('update_for_klb_{}'.format(table_update.id) in request.POST):
								only_bonus_score = ('klb_only_bonus_{}'.format(table_update.id) in request.POST)
								is_created, msgError, klb_vars = make_klb_result(table_update, request.user, only_bonus_score=only_bonus_score)
								if is_created:
									klb_results_created += 1
									race, year, person, team = klb_vars
									if year in persons_by_year:
										persons_by_year[year].add(person)
									else:
										persons_by_year[year] = set([person])
									if team:
										if race not in teams_by_race:
											teams_by_race[race] = Counter()
										teams_by_race[race][team] += 1
								else:
									messages.warning(request, u'Результат в КЛБМатч по изменению с id {} не создан. Причина: {}'.format(
										table_update.id, msgError))
							if 'add_extra_name_{}'.format(table_update.id) in request.POST:
								result = models.Result.objects.filter(pk=table_update.child_id).first()
								if result:
									runner = result.runner
									if runner:
										if not runner.extra_name_set.filter(fname=result.fname, lname=result.lname).exists():
											models.Extra_name.objects.create(
												runner=runner,
												fname=result.fname.strip().title(),
												lname=result.lname.strip().title(),
												comment=u'Автоматически при одобрении результата',
												added_by=request.user,
											)
											extra_names_added += 1
										else:
											messages.warning(request, u'Не получилось добавить доп. имя {} {} — оно у бегуна {} {} (id {}) уже есть'.format(
												result.fname, result.lname, runner.fname, runner.lname, runner.id))
									else:
										messages.warning(request, u'Не получилось добавить доп. имя — бегун у результата с id {} не найден'.format(result.id))
								else:
									messages.warning(request, u'Не получилось добавить доп. имя — результат с id {} не найден'.format(table_update.child_id))
						else:
							objects_errors += 1
							messages.warning(request, msgError)
					else:
						objects_errors += 1
						messages.warning(request, u'Изменение таблиц с id {} не найдено. Пропускаем'.format(table_update_id))
			if objects_verified:
				messages.success(request, u'Одобрено объектов: {}'.format(objects_verified))
			if extra_names_added:
				messages.success(request, u'Создано дополнительных имён бегунам: {}'.format(extra_names_added))
			if klb_results_created:
				messages.success(request, u'Создано результатов в КЛБМатч: {}'.format(klb_results_created))
				for year in persons_by_year:
					update_persons_score(year=year, persons_to_update=persons_by_year[year])
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
							comment=u'Одобрение заявок на результаты в КЛБМатч',
							added_by=request.user,
						)
			# if objects_errors:
			# 	messages.warning(request, u'Возникли ошибки c {} объектами – вероятно, их уже кто-то одобрил'.format(
			# 		objects_errors))
			return redirect('editor:action_history')
		elif 'frmSearchActions_submit' in request.POST: # We are just filtering tables changes
			if form.is_valid():
				city = form.cleaned_data['city']
				if city:
					kwargs_series['city'] = city
					args_event.append(Q(city=city) | (Q(city=None) & Q(series__city=city)))
					kwargs_news['event__city'] = city
					conditions.append(u"в городе {}".format(city))

				region = form.cleaned_data['region']
				if region and not city:
					kwargs_series['city__region'] = region
					args_event.append(Q(city__region=region) | (Q(city=None) & Q(series__city__region=region)))
					kwargs_news['event__city__region'] = region
					conditions.append(u"в регионе {}".format(region.name_full))

				country = form.cleaned_data['country']
				if country and (not city) and (not region):
					kwargs_series['city__region__country'] = country
					args_event.append(Q(city__region__country=country)
						| (Q(city=None) & Q(series__city__region__country=country)))
					kwargs_news['event__city__region__country'] = country
					conditions.append(u"в стране {}".format(country))

				unverified = form.cleaned_data['unverified']

				user = form.cleaned_data['user']
				if user:
					kwargs['user'] = user
					list_title += u" пользователя {}".format(user.get_full_name())

				date_from = form.cleaned_data['date_from']
				if date_from:
					kwargs['added_time__gte'] = date_from
					conditions.append(u"не раньше {}".format(date_from.isoformat()))
				date_to = form.cleaned_data['date_to']
				if date_to:
					kwargs['added_time__lte'] = date_to
					conditions.append(u"не позже {}".format(date_to.isoformat()))

				object_type = form.cleaned_data['object_type']
				if object_type:
					all_types = False
					conditions.append(u"с объектами {}".format(forms.OBJECT_TYPES[object_type]))

				action_type = form.cleaned_data['action_type']
	else:
		form = forms.ActionSearchForm()

	if unverified:
		kwargs['is_verified'] = False
		list_title = u"Ещё не одобренные д" + list_title[1:]
	if action_type != '':
		action_type = models.int_safe(action_type)
		conditions.append(u"типа «{}»".format(models.ACTION_TYPES[action_type + 1][1]))
		kwargs['action_type'] = action_type

	context['frmActions'] = form
	context['page_title'] = list_title + " " + ", ".join(conditions)

	if (not country) and (not region) and (not city):
		if all_types or (object_type == "City"):
			context['cities'] = get_table_update_tuples_filtered_by_model(models.City, related_for_model=['region__country'], **kwargs)
		if all_types or (object_type == "Distance"):
			context['distances'] = get_table_update_tuples_filtered_by_model(models.Distance, **kwargs)
		if all_types or (object_type == "Extra_name"):
			context['extra_names'] = get_table_update_tuples_filtered_by_model(models.Extra_name, **kwargs)
			# context['extra_names'] = models.Extra_name.objects.filter(**kwargs).select_related('user').order_by('added_time')

	if all_types or (object_type == "Series"):
		context['seria'] = get_table_update_tuples_filtered_by_model(models.Series, kwargs_for_model=kwargs_series, **kwargs)
	if all_types or (object_type == "Event"):
		context['events'] = get_table_update_tuples_filtered_by_model(models.Event, args_for_model=args_event,
			related_for_model=['series'], exclude_types=[models.ACTION_UNOFF_RESULT_CREATE, models.ACTION_RESULT_UPDATE], **kwargs)

		if action_type in ['', models.ACTION_UNOFF_RESULT_CREATE]:
			kwargs_for_results = kwargs.copy()
			kwargs_for_results['action_type'] = models.ACTION_UNOFF_RESULT_CREATE
			events_unoff_results = get_table_update_tuples_filtered_by_model(models.Event, args_for_model=args_event,
				related_for_model=['series'], updates_limit=N_RESULTS_TO_SHOW, **kwargs_for_results)
			context['n_events_unoff_results'] = len(events_unoff_results)
			context['events_unoff_results'] = events_unoff_results #[:N_RESULTS_TO_SHOW]

		if action_type in ['', models.ACTION_RESULT_UPDATE]:
			kwargs_for_results = kwargs.copy()
			kwargs_for_results['action_type'] = models.ACTION_RESULT_UPDATE
			events_off_results = get_table_update_tuples_filtered_by_model(models.Event, args_for_model=args_event,
				related_for_model=['series'], updates_limit=N_RESULTS_TO_SHOW, **kwargs_for_results)
			context['n_events_off_results'] = len(events_off_results)
			context['events_off_results'] = events_off_results #[:N_RESULTS_TO_SHOW]
	if all_types or (object_type == "News"):
		context['newses'] = get_table_update_tuples_filtered_by_model(models.News, kwargs_for_model=kwargs_news, **kwargs)
	if all_types or (object_type == "User_profile"):
		context['user_profiles'] = get_table_update_tuples_filtered_by_model(models.User_profile, **kwargs)
	if all_types or (object_type == "Runner"):
		context['runners'] = get_table_update_tuples_filtered_by_model(models.Runner, **kwargs)
	if all_types or (object_type == "Club"):
		context['clubs'] = get_table_update_tuples_filtered_by_model(models.Club, **kwargs)
	if all_types or (object_type == "Klb_team"):
		context['teams'] = get_table_update_tuples_filtered_by_model(models.Klb_team, **kwargs)
	if all_types or (object_type == "Klb_person"):
		context['klb_persons'] = get_table_update_tuples_filtered_by_model(models.Klb_person, **kwargs)
	return render(request, 'editor/action_history.html', context=context)

@group_required('admins')
def action_details(request, table_update_id):
	table_update = get_object_or_404(models.Table_update, pk=table_update_id)
	context = {}
	context['obj'] = getattr(models, table_update.model_name).objects.filter(pk=table_update.row_id).first()
	context['table_update'] = table_update
	context['field_updates'] = table_update.field_update_set.order_by('field_name')
	context['messages'] = table_update.message_from_site_set.order_by('-date_posted')

	context['page_title'] = u'Действие с id {}'.format(table_update_id)
	
	return render(request, "editor/action_details.html", context)

@group_required('admins')
def user_update_stat(request, user_id):
	user = get_object_or_404(User, pk=user_id)
	update_runner_stat(user=user)
	messages.success(request, u'Статистика успешно обновлена')
	return redirect('results:user_details', user_id=user.id)

FORMAT_HTML = 0
FORMAT_TXT = 1
@group_required('admins')
def user_mail_txt(request, user_id):
	return user_mail(request, user_id, format_type=FORMAT_TXT)

@group_required('admins')
def user_mail(request, user_id, format_type=FORMAT_HTML):
	user = get_object_or_404(User, pk=user_id)
	admin = User.objects.get(pk=1)
	profile = user.user_profile
	context = get_context_for_user_letter(user=user)
	template = "letters/letter_results.txt" if format_type == FORMAT_TXT else "letters/letter_results.html"
	# template = "letters/new_results.txt" if format_type == FORMAT_TXT else "letters/new_results_from_www.html"
	target = request.GET.get('target')
	if target:
		result = send_user_results_letter(user, admin, context)
		if result['success']:
			messages.success(request, u'Отправлено писем: {}'.format(result['success']))
		else:
			messages.warning(request, u'Ошибка при отправке письма: {}'.format(result['error']))
	return render(request, template, context)

def send_messages_with_results():
	user_ids = set(models.Result_for_mail.objects.filter(is_sent=False).values_list('user_id', flat=True))

	yesterday = timezone.now() - datetime.timedelta(days=1)

	checked_users_added_to_teams = set()
	users_added_to_teams = {}
	for added_data in models.User_added_to_team_or_club.objects.filter(added_time__gte=yesterday, team__isnull=False).select_related(
			'user', 'team', 'added_by__user_profile').order_by('-added_time'):
		if added_data.user in checked_users_added_to_teams:
			continue
		participant = added_data.team.klb_participant_set.filter(klb_person__runner__user=added_data.user).first()
		if participant:
			users_added_to_teams[added_data.user] = {
				'team': added_data.team,
				'added_by': added_data.added_by,
				'added_data': added_data,
				'date_registered': participant.date_registered,
				'added_by_admin': models.is_admin(added_data.added_by),
			}
			user_ids.add(added_data.user.id)
			# print 'Adding for user', added_data.user.id, ':', users_added_to_teams[added_data.user]
			checked_users_added_to_teams.add(added_data.user)

	checked_users_added_to_clubs = set()
	users_added_to_clubs = {}
	for added_data in models.User_added_to_team_or_club.objects.filter(added_time__gte=yesterday, club__isnull=False).select_related(
			'user', 'club', 'added_by__user_profile').order_by('-added_time'):
		if (added_data.user.id, added_data.club.id) in checked_users_added_to_clubs:
			continue
		club_member = added_data.club.club_member_set.filter(runner__user=added_data.user).first()
		if club_member:
			if added_data.user not in users_added_to_clubs:
				users_added_to_clubs[added_data.user] = []
			users_added_to_clubs[added_data.user].append({
				'added_data': added_data,
				'club_member': club_member,
				'added_by_admin': models.is_admin(added_data.added_by),
			})
			user_ids.add(added_data.user.id)
			checked_users_added_to_clubs.add((added_data.user.id, added_data.club.id))

	n_messages_sent = 0
	n_messages_error = 0
	for user_id in user_ids: # ['37']:
	# for user_id in ['1']:
		# if not models.is_admin(user):
		# 	continue
		user = User.objects.get(pk=user_id)
		if not hasattr(user, 'user_profile'):
			continue
		profile = user.user_profile
		if user.email == '':
			continue
		if not user.is_active:
			continue
		if not profile.email_is_verified:
			continue
		if not profile.ok_to_send_results:
			continue
		added_to_team_data = users_added_to_teams.get(user)
		added_to_club_data = users_added_to_clubs.get(user)
		result = send_user_results_letter(user, models.USER_ROBOT_CONNECTOR,
			get_context_for_user_letter(user=user, added_to_team_data=added_to_team_data, added_to_club_data=added_to_club_data))
		if result['success']:
			n_messages_sent += 1
			user.result_for_mail_set.filter(is_sent=False).update(is_sent=True, sent_time=timezone.now())
			if added_to_team_data:
				added_to_team_data['added_data'].sent_time = timezone.now()
				added_to_team_data['added_data'].save()
			# if added_to_club_data:
			# 	for item in added_to_club_data:
			# 		item['added_data'].sent_time = timezone.now()
			# 		item['added_data'].save()
		else:
			print u'Error with sending message to user {} (id {}): {}'.format(user.get_full_name(), user.id, result['error'])
			n_messages_error += 1
	print '{} Messages with results sent: {}, errors: {}'.format(datetime.datetime.now(), n_messages_sent, n_messages_error)

def create_user_profiles_once(): # For those users who didn't have them. As of 2018-07-23, All new users should have them
	count = 0
	count_wo_gender = 0
	count_not_created = 0
	for user in User.objects.filter(user_profile=None).order_by('pk'):
		profile, profile_just_created = models.User_profile.objects.get_or_create(user=user)
		if profile_just_created:
			models.log_obj_create(models.USER_ROBOT_CONNECTOR, profile, models.ACTION_CREATE, comment=u'Запоздало добавляем профили, у кого их нет')
			count += 1
			runner_name = models.Runner_name.objects.filter(name__iexact=user.first_name).first()
			if runner_name:
				profile.gender = runner_name.gender
				profile.save()
			else:
				print user.id, user.first_name, user.last_name
				count_wo_gender += 1
		else:
			count_not_created
		if (user.id % 200) == 0:
			print user.id, count, count_wo_gender, count_not_created
	print 'Done!', count, count_wo_gender, count_not_created

def fill_user_genders_once():
	count = 0
	count_wo_gender = 0
	for profile in models.User_profile.objects.filter(gender=models.GENDER_UNKNOWN).select_related('user').order_by('pk'):
		runner_name = models.Runner_name.objects.filter(name__iexact=profile.user.first_name).first()
		if runner_name:
			profile.gender = runner_name.gender
			profile.save()
			count += 1
		else:
			print profile.user.id, profile.user.first_name, profile.user.last_name
			count_wo_gender += 1
	print 'Done!', count, count_wo_gender

def create_user_runners_once(): # For those users who didn't have them. As of 2018-07-23, All new users should have them
	count = 0
	for profile in models.User_profile.objects.filter(user__runner=None).select_related('user').order_by('pk'):
		profile.create_runner(models.USER_ROBOT_CONNECTOR, comment=u'Запоздало создаём бегунов пользователям, у кого их нет')
		count += 1
	print 'Done!', count

def fill_runners_for_user_names_once():
	count = 0
	for name in models.Extra_name.objects.filter(runner=None).select_related('user__runner').order_by('pk'):
		runner = name.user.runner
		if runner is None:
			print 'Runner is none:', name.user.id
		else:
			name.runner = runner
			name.save()
			count += 1
	print 'Done!', count

def count_inactive_users_with_runner():
	count = 0
	print User.objects.exclude(runner=None).filter(is_active=False).count()
	for user in User.objects.exclude(runner=None).filter(is_active=False).select_related('runner'):
		if user.runner.result_set.exists():
			print user.id, user.runner.id, user.runner.result_set.count()
		else:
			user.runner.delete()
			count += 1
	print 'Done!', count

@group_required('admins')
def admin_work_stat(request, year=models.CUR_KLB_YEAR):
	context = {}
	context['page_title'] = u'Кто сколько чего сделал в последний год'.format(year)
	today = datetime.date.today()
	cur_year = today.year
	context['months'] = []
	for year in [cur_year, cur_year - 1]:
		last_month = today.month if (cur_year == year) else 12
		users = Group.objects.get(name="admins").user_set.exclude(pk__in=(230, 3384)).order_by('last_name')
		month_names = [u'', u'Январь', u'Февраль', u'Март', u'Апрель', u'Май', u'Июнь', u'Июль', u'Август', u'Сентябрь', u'Октябрь', u'Ноябрь', u'Декабрь']
		for month in range(last_month, 0, -1):
			month_data = {}
			month_data['month'] = u'{} {}'.format(month_names[month], year)
			date_start = datetime.datetime(year, month, 1, tzinfo=timezone.utc)
			date_end = datetime.datetime(year, month + 1, 1, tzinfo=timezone.utc) if (month < 12) else datetime.datetime(year + 1, 1, 1, tzinfo=timezone.utc)
			month_updates = models.Table_update.objects.filter(added_time__range=(date_start, date_end))
			month_data['users'] = []
			for user in users:
				user_updates = month_updates.filter(user=user)
				d = {}
				d['user'] = user
				d['series_created'] = user_updates.filter(model_name='Series', action_type=models.ACTION_CREATE).count()
				d['series_updated'] = user_updates.filter(model_name='Series', action_type=models.ACTION_UPDATE).count()
				d['events_created'] = user_updates.filter(model_name='Event', action_type=models.ACTION_CREATE).count()
				d['events_updated'] = user_updates.filter(model_name='Event', action_type=models.ACTION_UPDATE).count()
				d['races_created'] = user_updates.filter(model_name='Event', action_type=models.ACTION_RACE_CREATE).count()
				d['races_updated'] = user_updates.filter(model_name='Event', action_type=models.ACTION_RACE_UPDATE).count()
				d['runners_created'] = user_updates.filter(model_name='Runner', action_type=models.ACTION_CREATE).count()
				d['runners_updated'] = user_updates.filter(model_name='Runner', action_type=models.ACTION_UPDATE).count()
				d['documents_created'] = user_updates.filter(model_name='Event', action_type=models.ACTION_DOCUMENT_CREATE).count()
				d['documents_updated'] = user_updates.filter(model_name='Event', action_type=models.ACTION_DOCUMENT_UPDATE).count()
				d['news_created'] = user_updates.filter(model_name='Event', action_type=models.ACTION_NEWS_CREATE).count()
				d['news_updated'] = user_updates.filter(model_name='Event', action_type=models.ACTION_NEWS_UPDATE).count()
				d['off_results_created'] = user_updates.filter(model_name='Event', action_type=models.ACTION_RESULTS_LOAD).count()
				d['off_results_uploaded'] = models.Result.objects.filter(added_time__range=(date_start, date_end), source=models.RESULT_SOURCE_DEFAULT,
					loaded_by=user).count()
				d['off_results_updated'] = user_updates.filter(model_name='Event', action_type=models.ACTION_RESULT_UPDATE).count()
				d['unoff_results_created'] = user_updates.filter(model_name='Event', action_type=models.ACTION_UNOFF_RESULT_CREATE).count()
				d['klb_participants_created'] = user_updates.filter(model_name='Klb_person', action_type=models.ACTION_KLB_PARTICIPANT_CREATE).count()
				d['klb_participants_updated'] = user_updates.filter(model_name='Klb_person', action_type=models.ACTION_KLB_PARTICIPANT_UPDATE).count()
				d['social_posts_created'] = user_updates.filter(action_type=models.ACTION_SOCIAL_POST).count()
				d['off_results_approved'] = month_updates.filter(action_type=models.ACTION_RESULT_UPDATE, verified_by=user).count()
				d['unoff_results_approved'] = month_updates.filter(action_type=models.ACTION_UNOFF_RESULT_CREATE, verified_by=user).count()
				d['klb_results_created'] = user_updates.filter(action_type=models.ACTION_KLB_RESULT_CREATE).count()
				d['created_total'] = user_updates.count()
				d['verified_total'] = month_updates.filter(verified_by=user).count()

				month_data['users'].append(d)

			context['months'].append(month_data)

	return render(request, "editor/admin_work_stat.html", context)