# -*- coding: utf-8 -*-
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.utils.crypto import get_random_string
from django.core.urlresolvers import reverse
from django.core.mail import EmailMessage, send_mail
from django import forms as django_forms
from django.contrib import messages
from django.db.models import Q, F
import datetime
from collections import OrderedDict

from results import models
from results import forms
from results.results_util import maybe_strava_activity_number, plural_ending_new
from views_common import user_edit_vars, paginate_and_render, get_filtered_results_dict, get_lists_for_club_membership, add_race_dependent_attrs
from editor.views.views_klb_stat import update_persons_score
from editor.views.views_user_actions import log_form_change
from editor.views.views_stat import update_runner_stat
from editor.views.views_klb import create_klb_result
from starrating.utils.show_rating import annotate_user_results_with_sr_data

def generate_verification_code():
	chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
	return get_random_string(models.VERIFICATION_CODE_LENGTH, chars)

@login_required
def home(request):
	user = request.user
	profile = models.User_profile.objects.filter(user=user).first()
	if (profile is None) or (user.email == '') or (not profile.email_is_verified):
		return my_details(request)
	return user_details(request, user_id=request.user.id)

def user_details_full(request, user_id):
	return user_details(request, user_id, show_full_page=True)

def user_details(request, user_id, series_id=None, club_id=None, show_full_page=False):
	user = get_object_or_404(User, pk=user_id)
	profile, profile_just_created = models.User_profile.objects.get_or_create(user=user)
	if profile_just_created: # REMOVE ME after 2020-03-31 if there are no emails
		models.send_panic_email(
			'profile_just_created called in wrong place',
			u'profile_just_created was called from views_user.user_details for user {} (id {})'.format(user, user.id)
		)
	frmSeriesEditor = forms.SeriesEditorForm()
	frmClubsEditor = forms.ClubsEditorForm(user=user)
	context = user_edit_vars(request.user)

	if series_id:
		if context['is_admin']:
			series = get_object_or_404(models.Series, pk=series_id)
			series_editor = user.series_editor_set.filter(series=series).first()
			if series_editor:
				series_editor.delete()
				if not user.series_editor_set.exists():
					group = Group.objects.get(name='editors')
					group.user_set.remove(user)
				messages.success(request, u'У пользователя {} отобраны права редактора серии «{}».'.format(
					user.get_full_name(), series.name))
				return redirect(profile)
			else:
				messages.warning(request, u'У пользователя {} уже не было прав редактора на серию «{}».'.format(
					user.get_full_name(), series.name))
		else:
			messages.warning(request, u"У Вас нет прав на это действие.")
	elif club_id:
		if context['is_admin']:
			club = get_object_or_404(models.Club, pk=club_id)
			club_editor = user.club_editor_set.filter(club=club).first()
			if club_editor:
				club_editor.delete()
				messages.success(request, u'У пользователя {} отобраны права редактора на клуб «{}».'.format(
					user.get_full_name(), club.name))
				return redirect(profile)
			else:
				messages.warning(request, u'У пользователя {} уже не было прав редактора на клуб «{}».'.format(
					user.get_full_name(), club.name))
		else:
			messages.warning(request, u"У Вас нет прав на это действие.")
	elif 'frmSeriesEditor_submit' in request.POST:
		if context['is_admin']:
			frmSeriesEditor = forms.SeriesEditorForm(request.POST)
			if frmSeriesEditor.is_valid():
				series_id = frmSeriesEditor.cleaned_data['series_id']
				series = get_object_or_404(models.Series, pk=series_id)
				if user.series_editor_set.filter(series=series).exists():
					messages.warning(request, u'У пользователя {} уже есть права редактора на серию «{}».'.format(
						user.get_full_name(), series.name))
				else:
					models.Series_editor.objects.create(series=series, user=user, added_by=request.user)
					group = Group.objects.get(name='editors')
					user.groups.add(group)
					messages.success(request, u'Пользователю {} добавлены права на редактуру серии «{}».'.format(
						user.get_full_name(), series.name))
					return redirect(profile)
			else:
				messages.warning(request, u"Права не добавлены. Пожалуйста, исправьте ошибки в форме.")
		else:
			messages.warning(request, u"У Вас нет прав на это действие.")
	elif 'frmClubsEditor_submit' in request.POST:
		if context['is_admin']:
			frmClubsEditor = forms.ClubsEditorForm(request.POST, user=user)
			if frmClubsEditor.is_valid():
				club = frmClubsEditor.cleaned_data['club']
				if user.club_editor_set.filter(club=club).exists():
					messages.warning(request, u'У пользователя {} уже есть права редактора на клуб «{}».'.format(
						user.get_full_name(), club.name))
				else:
					models.Club_editor.objects.create(club=club, user=user, added_by=request.user)
					messages.success(request, u'Пользователю {} добавлены права редактора на клуб «{}».'.format(
						user.get_full_name(), club.name))
					return redirect(profile)
			else:
				messages.warning(request, u"Права не добавлены. Пожалуйста, исправьте ошибки в форме.")
		else:
			messages.warning(request, u"У Вас нет прав на это действие.")

	context['user'] = user
	context['profile'] = profile
	if hasattr(user, 'runner'):
		context.update(get_lists_for_club_membership(request.user, user.runner, context['is_admin']))
		context['runner'] = user.runner
		if user.runner.klb_person:
			person = user.runner.klb_person
			context['klb_person'] = person
			context['klb_participations'] = OrderedDict()
			for year in [models.CUR_KLB_YEAR, models.NEXT_KLB_YEAR]:
				if models.is_active_klb_year(year, context['is_admin']):
					participant = person.klb_participant_set.filter(match_year=year).first()
					if participant:
						context['klb_participations'][year] = participant
	context.update(get_filtered_results_dict(request, user, profile.has_many_distances, 'klb_person' in context, show_full_page))

	context['user_is_admin'] = models.is_admin(user)
	context['is_user_homepage'] = request.user.is_authenticated and (user == request.user)
	context['page_title'] = user.get_full_name()
	context['frmSeriesEditor'] = frmSeriesEditor
	context['series_to_edit'] = user.series_to_edit_set.order_by('name')
	context['frmClubsEditor'] = frmClubsEditor
	context['calendar'] = user.calendar_set.filter(event__start_date__gte=datetime.date.today()).select_related(
		'event', 'race__distance').order_by('event__start_date')
	context['SITE_URL'] = models.SITE_URL

	if context['is_admin']:
		context['unclaimed_results'] = user.unclaimed_result_set.select_related('result__race__event', 'result__race__distance').order_by(
			'-result__race__event__start_date')

	# Adding info on how the user have rated the race
	context['results'] = annotate_user_results_with_sr_data(context['results'], context['to_show_rating'])

	return render(request, 'results/user_details.html', context)

def is_result_good_for_klb(result, participant_set):
	if participant_set and (result.get_klb_status() == models.KLB_STATUS_OK) and not hasattr(result, 'klb_result'):
		race = result.race
		race_date = race.start_date if race.start_date else race.event.start_date
		participant = participant_set.filter(match_year=race_date.year).first()
		if participant and ( (participant.date_registered is None) or (participant.date_registered <= race_date) ) \
				and ( (participant.date_removed is None) or (participant.date_removed >= race_date) ):
			return True, participant
	return False, None

def try_claim_results(request, runner, is_admin):
	results_claimed = 0
	results_for_klbmatch = 0
	results_errors = 0
	results_unclaimed = 0

	user = runner.user
	person = None
	participant_set = None
	if runner.klb_person:
		person = runner.klb_person
		active_klb_years = [models.CUR_KLB_YEAR]
		if models.NEXT_KLB_YEAR_AVAILABLE_FOR_ALL or is_admin:
			active_klb_years.append(models.NEXT_KLB_YEAR)
		participant_set = person.klb_participant_set.filter(was_deleted_from_team=False, match_year__in=active_klb_years)
		# if person.klb_participant_set.filter(was_deleted_from_team=False, match_year__in=(models.CUR_KLB_YEAR, models.NEXT_KLB_YEAR)).exists():
		# 	participant_set = person.klb_participant_set

	for key, val in request.POST.items():
		if key.startswith("claim_"):
			result_id = models.int_safe(key[len("claim_"):])
			result = models.Result.objects.filter(id=result_id, user=None).first()
			if result is None:
				continue

			is_for_klb, participant = is_result_good_for_klb(result, participant_set)
			year = None
			if is_for_klb:
				year = result.race.event.start_date.year
				if not models.is_active_klb_year(year, is_admin):
					is_for_klb = False
			res, msgError = result.claim_for_runner(request.user, runner, comment=u'Со страницы "Поискать результаты"',
				is_for_klb=is_for_klb, allow_merging_runners=True)
			if res:
				results_claimed += 1
				if is_for_klb:
					results_for_klbmatch += 1
			else:
				results_errors += 1
				if msgError:
					messages.warning(request, msgError)
		elif key.startswith("unclaim_forever_"):
			result_id = models.int_safe(key[len("unclaim_forever_"):])
			result = models.Result.objects.filter(id=result_id, user__isnull=True).first()
			if result:
				if not user.unclaimed_result_set.filter(result=result).exists():
					models.Unclaimed_result.objects.create(user=user, result=result, added_by=request.user)
					results_unclaimed += 1
	return results_claimed, results_for_klbmatch, results_unclaimed, results_errors

@login_required
def find_results(request, user_id=None, runner_id=None):
	context = user_edit_vars(request.user)
	user = None
	runner = None

	if context['is_admin'] and user_id:
		user = get_object_or_404(User, pk=user_id)
		context['user_id'] = user_id
		person_name = u'Пользователю {}'.format(user.get_full_name())
	elif context['is_admin'] and runner_id:
		runner = get_object_or_404(models.Runner, pk=runner_id)
		context['runner_id'] = runner_id
		person_name = u'Бегуну {}'.format(runner.name())
	else:
		user = request.user
		person_name = u'Вам'

	if runner is None:
		if not hasattr(user, 'runner'):
			messages.warning(request, u'У пользователя {} (id {}) нет бегуна. За таких нельзя искать результаты.'.format(
				user.get_full_name(), user.id))
			return redirect(user.user_profile)
		runner = user.runner
	context['user'] = user
	context['runner'] = runner

	if 'frmResults_claim' in request.POST:
		results_claimed, results_for_klbmatch, results_unclaimed, results_errors = try_claim_results(request, runner, context['is_admin'])
		if results_claimed > 0:
			runner.refresh_from_db()
			update_runner_stat(runner=runner)
			if runner.user:
				update_runner_stat(user=user, update_club_members=False)
			messages.success(request, u'{} добавлен{} {} результат{}'.format(
				person_name, plural_ending_new(results_claimed, 17), results_claimed, plural_ending_new(results_claimed, 1)))
		if results_for_klbmatch > 0:
			messages.success(request, u'В том числе отправлено на модерацию в КЛБМатч: {}'.format(results_for_klbmatch))
		if results_unclaimed > 0:
			messages.success(request, u'Больше не будем показывать Вам результатов Ваших тёзок: {}'.format(results_unclaimed))
		if results_errors > 0:
			messages.warning(request, u'Возникли ошибки c {} результатами. Редакторы уже знают о проблеме.'.format(results_errors))

		if user_id:
			return redirect('results:user_details', user_id=user_id)
		if runner_id:
			return redirect(runner)
		return redirect('results:home')

	context['names'] = runner.extra_name_set.all()
	context['results'] = runner.get_possible_results()
	if runner.klb_person:
		person = runner.klb_person
		if person.klb_participant_set.filter(match_year__in=(models.CUR_KLB_YEAR, models.NEXT_KLB_YEAR)).exists():
			participant_set = person.klb_participant_set
			context['result_for_klb_ids'] = set()
			for result in context['results']:
				if (result.get_klb_status() == models.KLB_STATUS_OK) and (not hasattr(result, 'klb_result')) \
						and participant_set.filter(match_year=result.race.event.start_date.year).exists():
					event_date = result.race.event.start_date
					participant = participant_set.filter(match_year=event_date.year).first()
					if ( (participant.date_registered is None) or (participant.date_registered <= event_date) ) \
							and ( (participant.date_removed is None) or (participant.date_removed >= event_date) ):
						context['result_for_klb_ids'].add(result.id)
						if participant.team_id:
							context['needs_klb_confirmation'] = True
	context['page_title'] = u'Поиск своих результатов'

	return render(request, 'results/find_results.html', context=context)

@login_required
def send_confirmation_letter(request):
	return my_details(request, resend_message=True)

@login_required
def my_details(request, user_id=0, resend_message=False, frmName=forms.UserNameForm()):
	context = user_edit_vars(request.user)
	user_id = models.int_safe(user_id)
	if context['is_admin'] and user_id:
		user = get_object_or_404(User, pk=user_id)
	else:
		user = request.user
	context['user'] = user
	context['user_id'] = user.id
	message_prefix = ''
	to_redirect = False

	profile, context['profile_just_created'] = models.User_profile.objects.get_or_create(user=user)
	context['url_for_update'] = reverse('results:my_details')
	if context['is_admin'] and (user != request.user):
		context['url_for_update'] = profile.get_our_editor_url()
	if context['profile_just_created']:
		models.log_obj_create(request.user, profile, models.ACTION_CREATE, comment=u'При регистрации на сайте')
		message_prefix = u'Регистрация прошла успешно! '
		profile.create_runner(request.user, comment=u'При регистрации пользователя')
		if user.email:
			resend_message = True
	if user.is_active and not hasattr(user, 'runner'):
		profile.create_runner(user, comment=u'На странице my_details')
		models.send_panic_email(
			'Active user had no runner',
			u'User {} (id {}) had no runner. We have just created one.'.format(user, user.id)
		)
		# We reload the user so that she gets her runner
		user = User.objects.get(pk=user.id)

	city = profile.city
	if 'frmProfile_submit' in request.POST:
		form = forms.UserProfileForm(request.POST, request.FILES, instance=profile, user=user, city=city)
		if form.is_valid():
			user.first_name = form.cleaned_data['fname'].strip()
			user.last_name = form.cleaned_data['lname'].strip()
			user.email = form.cleaned_data['email'].strip()
			if 'email' in form.changed_data:
				form.instance.email_is_verified = False
				if user.email:
					resend_message = True
			profile = form.save()
			log_form_change(request.user, form, action=models.ACTION_UPDATE, exclude=['country', 'region'])
			user.save()
			if 'avatar' in form.changed_data:
				if not profile.make_thumbnail():
					messages.warning(request, u'Не получилось уменьшить фото для аватара.')

			changed_fields_for_runner = []
			if hasattr(user, 'runner'):
				runner = user.runner
				for field in ['midname', 'gender', 'city_id', 'club']:
					if (field in form.changed_data) and not getattr(runner, field):
						setattr(runner, field, getattr(profile, field))
						changed_fields_for_runner.append(field)
				if ('birthday' in form.changed_data) and not runner.birthday_known:
					runner.birthday = profile.birthday
					runner.birthday_known = True
					changed_fields_for_runner.append('birthday')
					changed_fields_for_runner.append('birthday_known')
				if changed_fields_for_runner:
					runner.save()
					models.log_obj_create(request.user, runner, models.ACTION_UPDATE, field_list=changed_fields_for_runner, comment=u'При правке пользователя')

			messages.success(request, u'Данные сохранены.')
			to_redirect = True
		else:
			messages.warning(request, u'Данные не сохранены. Пожалуйста, исправьте ошибки в форме.')
	else:
		form = forms.UserProfileForm(instance=profile, user=user, city=city)

	if not profile.email_is_verified:
		if resend_message:
			if profile.email_verification_code == '':
				profile.email_verification_code = generate_verification_code()
				profile.save()
			if models.is_email_correct(user.email):
				res = send_letter_with_code(user, profile)
				if res:
					messages.success(request, message_prefix
						+ u'Письмо для подтверждения электронного адреса отправлено на адрес {}.'.format(user.email))
				else:
					messages.warning(request, (message_prefix
						+ u'К сожалению, письмо на адрес {} отправить не удалось. Мы уже разбираемся'
						+ u' в причинах. Вы можете написать нам на <a href="mailto:{}">{}</a>,'
						+ u' чтобы ускорить решение проблемы.').format(user.email, models.INFO_MAIL, models.INFO_MAIL))
			else:
				messages.warning(request, message_prefix
					+ u'Пожалуйста, укажите корректный электронный адрес. Мы пришлём на него письмо для подтверждения.')
		elif user.email == '':
			messages.warning(request, message_prefix
				+ u'Пожалуйста, укажите Ваш электронный адрес. Мы пришлём на него письмо для подтверждения.')
		else:
			messages.warning(request, (u'Вы ещё не подтвердили свой электронный адрес. Перейдите по ссылке из присланного Вам '
					+ u'письма, или <a href="{}">закажите ещё одно письмо</a> на адрес {}, или измените свой адрес.').format(
				reverse('results:send_confirmation_letter'), user.email))

	if to_redirect:
		return redirect(context['url_for_update'])

	context['frmProfile'] = form
	context['profile'] = profile

	name_for_title = (user.first_name + " " + user.last_name) if user.last_name else u'Следующий шаг:'
	context['page_title'] = name_for_title + u': личные данные'

	if (not context['profile_just_created']) and (not user_id):
		context['showNames'] = True
		context['names'] = user.runner.extra_name_set.order_by('lname', 'fname', 'midname')
		context['frmName'] = frmName

	return render(request, "results/my_details.html", context)

@login_required
def my_strava_links(request, user_id=None):
	context = user_edit_vars(request.user)
	user_id = models.int_safe(user_id)
	if context['is_admin'] and user_id:
		user = get_object_or_404(User, pk=user_id)
		context['page_title'] = u'Ссылки на забеги в Strava у пользователя {}'.format(user.get_full_name())
	else:
		user = request.user
		context['page_title'] = u'Ссылки на ваши забеги в Strava'
	context['user'] = user
	context['user_id'] = user.id
	results_data = {}

	if 'btnStravaLinks' in request.POST:
		results = user.result_set.select_related('result_on_strava')
		for result in results:
			data = {}
			strava_link = request.POST.get('strava_for_{}'.format(result.id), '')
			result_on_strava = result.result_on_strava if hasattr(result, 'result_on_strava') else None
			if strava_link:
				data['link'] = strava_link
				strava_number = maybe_strava_activity_number(strava_link)
				if strava_number:
					if result_on_strava and (result_on_strava.link != strava_number):
						result_on_strava.link = strava_number
						result_on_strava.save()
						models.log_obj_create(user, result_on_strava, models.ACTION_UPDATE, field_list=['link'], comment=u'При обновлении всех ссылок сразу')
						data['is_saved'] = True
					elif result_on_strava is None:
						result_on_strava = models.Result_on_strava.objects.create(
							result=result,
							link=strava_number,
							added_by=request.user,
						)
						models.log_obj_create(user, result_on_strava, models.ACTION_CREATE, comment=u'При обновлении всех ссылок сразу')
						data['is_saved'] = True
					data['link'] = unicode(result_on_strava)
				else:
					messages.warning(request, u'Strava link: {}'.format(strava_link))
					data['error'] = True
			else:
				if result_on_strava:
					models.log_obj_create(user, result_on_strava, models.ACTION_DELETE, comment=u'При обновлении всех ссылок сразу')
					result_on_strava.delete()
					data['is_removed'] = True
			results_data[result] = data
		messages.success(request, u'Введённые данные обработаны')

	context['results'] = []
	for result in add_race_dependent_attrs(user.result_set).order_by('-race__event__start_date'):
		if result in results_data: # So we've just worked with it, nothing else is needed in dict
			context['results'].append((result, results_data[result]))
		elif hasattr(result, 'result_on_strava'):
			context['results'].append((result, {'link': unicode(result.result_on_strava)}))
		else:
			context['results'].append((result, {}))

	return render(request, "results/user_strava_links.html", context)

@login_required
def my_name_add(request):
	user = request.user
	runner = user.runner
	extra_name = models.Extra_name(runner=runner, added_by=request.user)
	if 'frmName_submit' in request.POST:
		form = forms.UserNameForm(request.POST, instance=extra_name)
		if form.is_valid():
			form.save()
			log_form_change(user, form, action=models.ACTION_CREATE)
			messages.success(request, u'Новое имя успешно добавлено')
			return redirect('results:my_details')
		else:
			messages.warning(request, u'Данные для нового имени указаны с ошибкой. Пожалуйста, исправьте ошибки в форме.')
	else:
		form = forms.UserNameForm()
	return my_details(request, frmName=form)

@login_required
def my_name_delete(request, name_id):
	name = models.Extra_name.objects.filter(pk=name_id, runner=request.user.runner).first()
	if name:
		models.log_obj_create(request.user, name, models.ACTION_DELETE, comment=u'Удалено пользователем со своей страницы')
		name.delete()
		messages.success(request, u'Имя успешно удалено.')
		return redirect('results:my_details')
	else:
		messages.warning(request, u'Имя для удаления не найдено. Ничего не удалено.')
		return my_details(request)

@login_required
def verify_email(request, code):
	user = request.user
	profile = user.user_profile
	if profile is None:
		messages.warning(request, u'Что-то пошло не так. Пожалуйста, пройдите по ссылке из письма ещё раз, или напишите нам.')
		return redirect('results:my_details')
	if profile.email_is_verified:
		messages.success(request, u'Ваш почтовый адрес уже был подтверждён раньше, всё в порядке!')
		return redirect('results:my_details')
	if code == profile.email_verification_code:
		profile.email_is_verified = True
		profile.email_verification_code = ''
		profile.save()
		messages.success(request, u'Ваш почтовый адрес {} успешно подтверждён. Теперь Вам доступны все возможности сайта!'.format(
			user.email))
		return redirect('results:my_details')
	else:
		messages.warning(request, (u'Вы указали неверный код авторизации. Попробуйте ещё раз перейти по ссылке, '
					+ u'или <a href="{}">закажите ещё одно письмо</a> на адрес {}, или измените почтовый адрес.').format(
			reverse('results:send_confirmation_letter'), user.email))
		return redirect('results:my_details')

def send_letter_with_code(user, profile):
	message_from_site = models.Message_from_site.objects.create(
		title=u'ПроБЕГ: подтверждение электронного адреса',
		body=(u'Добрый день!\n\nКто-то – возможно, Вы – указал на сайте {} электронный адрес {} '
			+ u'в качестве своего.\nЕсли это были Вы, перейдите по ссылке ниже для подтверждения. Если нет, '
			+ u'просто удалите это письмо.\n\nСсылка для подтверждения: {}{}\n\n'
			+ u'---\nС уважением,\nКоманда сайта «ПроБЕГ»').format(
			models.SITE_URL, user.email, models.SITE_URL, reverse('results:verify_email', kwargs={'code': profile.email_verification_code})),
		target_email=user.email,
		created_by=user,
		)
	message = EmailMessage(
		subject=message_from_site.title,
		body=message_from_site.body,
		# from_email=message_from_site.sender_email,
		to=[message_from_site.target_email],
		)
	res = message.send()
	if res:
		message_from_site.is_sent = True
		message_from_site.save()
	return res

# On 2020-01-13 several messages weren't sent because of mistake. Let's resend them
def send_letters_with_code():
	for user_id in range(5693, 5703):
		user = User.objects.get(pk=user_id)
		res = send_letter_with_code(user, user.user_profile)
		print('{} {}'.format(user_id, res))
	print('Done!')

def get_avatar_page(request, user_id):
	user = get_object_or_404(User, pk=user_id)
	context = {}
	context['image_url'] = user.user_profile.get_avatar_url()
	return render(request, "results/modal_image.html", context)
