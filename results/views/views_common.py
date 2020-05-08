# -*- coding: utf-8 -*-
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.auth.models import User
from django.db.models import Q, Count
from django.shortcuts import render
import datetime

from results import models
from results.forms import RunnerResultFilterForm

RECORDS_ON_PAGE = 100

def get_page_num(request):
	page_vals = (request.POST if request.method == 'POST' else request.GET).getlist('page')
	for page_val in page_vals:
		if page_val.strip() != '':
			return models.int_safe(page_val)
	return 1

def get_results_with_splits_ids(results):
	result_ids = set(results.values_list('pk', flat=True))
	return set(models.Split.objects.filter(result_id__in=result_ids).values_list('result_id', flat=True).order_by().distinct())

def paginate_and_render(request, template, context, queryset, show_all=False, page=None, add_results_with_splits=False):
	if show_all:
		qs = list(queryset)
		context['page_enum'] = zip(range(1, len(qs) + 1), qs)
	else:
		paginator = Paginator(queryset, RECORDS_ON_PAGE)
		if page is None:
			page = get_page_num(request)
		# context['page_number'] = (unicode(request.POST.lists()) + ' page: {}'.format(page)) if request.method == 'POST' else '@'
		try:
			qs_page = paginator.page(page)
		except PageNotAnInteger:
			# If page is not an integer, deliver first page.
			qs_page = paginator.page(1)
		except EmptyPage:
			# If page is out of range (e.g. 9999), deliver last page of results.
			qs_page = paginator.page(paginator.num_pages)
		first_index = (qs_page.number - 1) * RECORDS_ON_PAGE + 1
		last_index = min(qs_page.number * RECORDS_ON_PAGE, paginator.count)
		context.update({
			'page_enum': zip(range(first_index, last_index + 1), qs_page),
			'page': qs_page,
			'paginator': paginator,
			'first_index': unicode(first_index),
			'last_index': unicode(last_index),
			'show_first_page': (qs_page.number > 3),
			'show_last_page': (qs_page.number < paginator.num_pages - 2),
			'show_left_ellipsis': (qs_page.number > 4),
			'show_right_ellipsis': (qs_page.number < paginator.num_pages - 3),
			'show_minus_two_page': (qs_page.number > 2),
			'show_plus_two_page': (qs_page.number < paginator.num_pages - 1),
		})
		if add_results_with_splits:
			context['results_with_splits'] = get_results_with_splits_ids(queryset)
	return render(request, template, context)

def user_edit_vars(user, series=None, club=None):
	context = {}
	context['is_admin'] = False
	context['is_editor'] = False
	context['is_extended_editor'] = False
	context['to_show_rating'] = True
	if user.is_authenticated:
		if models.is_admin(user):
			context['is_admin'] = True
		else:
			if series:
				if models.Series_editor.objects.filter(user=user, series=series).exists():
					context['is_editor'] = True
					if hasattr(user, 'user_profile'):
						context['is_extended_editor'] = user.user_profile.is_extended_editor
			elif club:
				context['is_editor'] = models.Club_editor.objects.filter(user=user, club=club).exists()
			else:
				context['is_editor'] = user.groups.filter(name="editors").exists()
			context['is_club_leader'] = user.club_editor_set.exists()
	return context

def get_first_form_error(form): # In case that there are errors
	key, val = form.errors.items()[0]
	if key in form.fields:
		key = form.fields[key].label
		return u'{}: {}'.format(key, val[0])
	else:
		return unicode(val[0])

def add_race_dependent_attrs(results):
	return results.select_related('race__distance', 'race__distance_real', 'category_size', 'result_on_strava',
		'race__event__series__city__region__country', 'race__event__series__city_finish__region__country', 'race__event__series__country',
		'race__event__city__region__country', 'race__event__city_finish__region__country')

N_RESULTS_ON_USER_PAGE_DEFAULT = 100
def get_filtered_results_dict(request, runner_or_user, has_many_distances, is_in_klb, show_full_page):
	results = add_race_dependent_attrs(runner_or_user.result_set).select_related('klb_result').order_by('-race__event__start_date')
		# 'klb_result__klb_person__runner', - was needed when there was discrepancy between result.runner and result.klb_result.klb_person.runner

	context = {}
	context['n_results_total'] = results.count() # When filters show 0 results, we need to show filters anyway!

	filtered_results = results
	if context['n_results_total'] > 0:
		initial = {}
		if request.GET.get('series'):
			initial['series'] = request.GET.get('series')
			filtered_results = filtered_results.filter(race__event__series_id=request.GET.get('series'))
		if request.GET.get('distance'):
			initial['distance'] = request.GET.get('distance')
			filtered_results = filtered_results.filter(race__distance_id=request.GET.get('distance'))
		if request.GET.get('name'):
			name = request.GET.get('name').strip()
			initial['name'] = name
			filtered_results = filtered_results.filter(
				Q(race__event__name__icontains=name) | Q(race__event__series__name__icontains=name))
		context['resultFilterForm'] = RunnerResultFilterForm(results, initial=initial)

	if is_in_klb:
		result_ids = filtered_results.values_list('pk', flat=True)
		context['klb_pending_result_ids'] = set(models.Table_update.objects.filter(
			action_type__in=(models.ACTION_UNOFF_RESULT_CREATE, models.ACTION_RESULT_UPDATE),
			is_verified=False, is_for_klb=True, child_id__in=result_ids).values_list('child_id', flat=True))

	context['results_with_splits'] = get_results_with_splits_ids(filtered_results)

	context['show_full_page'] = show_full_page
	if (not show_full_page) and (context['n_results_total'] > N_RESULTS_ON_USER_PAGE_DEFAULT) and ('btnFilter' not in request.GET):
		context['show_full_page_link'] = True
		filtered_results = filtered_results.all()[:N_RESULTS_ON_USER_PAGE_DEFAULT]
		context['N_RESULTS_ON_USER_PAGE_DEFAULT'] = N_RESULTS_ON_USER_PAGE_DEFAULT

	stat_set = runner_or_user.user_stat_set.filter(year=None)
	context['distances'] = stat_set.select_related('distance').order_by('distance__distance_type', '-distance__length')
	if has_many_distances and not show_full_page:
		context['distances'] = context['distances'].filter(is_popular=True)
	context['best_result_ids'] = set(stat_set.values_list('best_result_id', flat=True))

	context['results'] = filtered_results

	return context

def get_lists_for_club_membership(user, runner, user_is_admin):
	context = {}
	runner_clubs = runner.club_member_set.all()
	runner_current_club_ids = set()
	if runner_clubs:
		today = datetime.date.today()
		runner_current_club_ids = set(runner_clubs.filter(Q(date_removed=None) | Q(date_removed__gte=today)).values_list('club_id', flat=True))
		context['clubs'] = models.Club.objects.filter(pk__in=runner_current_club_ids).order_by('name')

	if user.is_authenticated:
		user_club_ids = set(user.club_editor_set.values_list('club_id', flat=True))
		if user_is_admin: # FIXME
			user_club_ids |= set([63, 66])
		if user_club_ids:
			runner_all_club_ids = set(runner_clubs.values_list('club_id', flat=True))
			context['clubs_to_add'] = models.Club.objects.filter(pk__in=user_club_ids - runner_all_club_ids).order_by('name')
			clubs_was_member_before = runner_clubs.filter(
				club_id__in=runner_all_club_ids - runner_current_club_ids).select_related('club').order_by('club__name')

			if clubs_was_member_before:
				context['clubs_was_member_before'] = [] # Pairs (club member; can current user change his dates in that club?)
				for club_member in clubs_was_member_before:
					context['clubs_was_member_before'].append((club_member, user_is_admin or (club_member.club_id in user_club_ids)))
	return context