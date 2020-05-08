# -*- coding: utf-8 -*-
from __future__ import division
from django.shortcuts import get_object_or_404, redirect
from django.core.mail import send_mail
from django.contrib import messages
from django.db.models import Sum

from collections import Counter
import datetime
import time
import re

from results import models
from results import results_util
from .views_common import group_required, generate_html
from .views_result import fill_places, fill_race_headers, split_name
from .views_stat import update_results_count, update_events_count, update_runner_stat

parkrun_result_re = re.compile(r'<tr[^>]*><td[^>]*>(?P<place>\d+)</td><td[^>]*><div[^>]*><a href="athletehistory\?athleteNumber=(?P<parkrun_id>\d+)"[^>]*>(?P<name>[^<]+)</a></div><div[^>]*>[^<]*<span[^>]*><span[^>]*>[^<]*</span><span[^>]*>(?P<gender>[^<]+)</span>\d+<span[^>]*>[^<]*</span></span>(<span[^>]*>[^<]*</span><a [^>]*>[^<]*</a>)*</div><div[^>]*><div[^>]*><a [^>]*>(?P<category>[^<]+)</a><span[^>]*>[^<]*</span>[^<]*</div></div>(<div[^>]*><div[^>]*><a [^>]*>(?P<club>[^<]+)</a></div></div>)*</td><td[^>]*><div[^>]*>[^<]*</div><div[^>]*>(?P<place_gender>\d+)<span[^>]*>[^<]*</span></div></td><td[^>]*><div[^>]*><a [^>]*>[^<]*</a></div><div[^>]*>[^<]*</div></td><td[^>]*>(<div[^>]*><a [^>]*>[^<]*</a></div>)*[^<]*</td><td[^>]*><div[^>]*>(?P<result>[^<]+)</div><div[^>]*><span[^>]*>(?P<comment1>[^<]*)</span>(?P<comment2>[^<]*)')
parkrun_result_history_re = re.compile(r'<tr><td><a href="([^"]+)">(\d+)</a></td><td><a href="[^"]+">(\d\d)/(\d\d)/(\d\d\d\d)</a></td><td>(\d+)</td>')

PARKRUN_DISTANCE = models.Distance.objects.filter(distance_type=models.TYPE_METERS, length=5000).first()

SERIES_WITH_LATE_START_2018 = (2823, 2825, 4309, 4311, 4426, 4565, 4696)

# Load results for race with given race_id, either all or for Russians only
def load_race_results(race, url_results, user, load_only_russians=False):
	result, response, _ = results_util.read_url(url_results)
	if not result:
		models.write_log(u"Couldn't load results for parkrun {}, id={}, from url {}".format(race.event, race.event.id, url_results))
		return 0, set()
	html = response.read().decode('utf-8')
	race.result_set.filter(source=models.RESULT_SOURCE_DEFAULT).delete()
	results_added = 0
	runners_touched = set()

	category_sizes = {category_size.name: category_size for category_size in race.category_size_set.all()}
	category_lower_to_orig = {name.lower(): name for name in category_sizes}

	new_results = []

	for group in parkrun_result_re.finditer(html):
		groupdict = group.groupdict('')
		parkrun_id = results_util.int_safe(groupdict['parkrun_id'])
		lname, fname, midname = split_name(groupdict['name'].strip().title(), first_name_position=0)
		gender = models.string2gender(groupdict['gender'].strip())
		if gender == models.GENDER_UNKNOWN:
			models.send_panic_email(
				'views_parkrun: load_race_results: problem with gender',
				u"Problem with race id {}, url {} : gender '{}' cannot be parsed".format(race.id, url_results, groupdict['gender']),
			)
		runner, created = models.Runner.objects.get_or_create(
			parkrun_id=parkrun_id,
			defaults={'lname': lname, 'fname': fname, 'gender': gender}
		)

		centiseconds = models.string2centiseconds(groupdict['result'])
		if centiseconds == 0:
			models.send_panic_email(
				'views_parkrun: load_race_results: problem with time',
				u"Problem with race id {}, url {} : time '{}' cannot be parsed".format(race.id, url_results, groupdict['result']),
			)

		category = groupdict['category']
		if category:
			category_lower = category.lower()
			if category_lower not in category_lower_to_orig:
				category_sizes[category] = models.Category_size.objects.create(race=race, name=category)
				category_lower_to_orig[category_lower] = category

		new_results.append(models.Result(
			race=race,
			runner=runner,
			user=runner.user,
			parkrun_id=parkrun_id,
			name_raw=groupdict['name'],
			time_raw=groupdict['result'],
			club_raw=groupdict['club'],
			club_name=groupdict['club'],
			place_raw=results_util.int_safe(groupdict['place']),
			result=centiseconds,
			status=models.STATUS_FINISHED,
			status_raw=models.STATUS_FINISHED,
			category_size=category_sizes[category_lower_to_orig[category_lower]] if category else None,
			category_raw=category,
			comment=groupdict['comment1'] + groupdict['comment2'],
			lname=lname,
			fname=fname,
			midname=midname,
			gender=gender,
			gender_raw=gender,
			loaded_by=user,
			loaded_from=url_results,
		))
		runners_touched.add(runner)

	models.Result.objects.bulk_create(new_results)
	fill_places(race)
	fill_race_headers(race)
	if len(new_results) > 0:
		race.loaded = models.RESULTS_LOADED
		race.save()
	models.write_log(u"Race {}: {} results are loaded".format(race, len(new_results)))
	return len(new_results), runners_touched

def reload_parkrun_results(race, user): # Returns <success?>, <results loaded>, <runners touched>
	protocol = race.event.document_set.filter(document_type=models.DOC_TYPE_PROTOCOL).first()
	if protocol:
		url_results = protocol.url_original
		if url_results:
			runners_touched = set(result.runner for result in race.result_set.all() if result.runner)
			n_results, runners_touched_2 = load_race_results(race, url_results, user)
			runners_touched |= runners_touched_2
			for runner in runners_touched:
				update_runner_stat(runner=runner)
				if runner.user:
					update_runner_stat(user=runner.user, update_club_members=False)
			return True, n_results, len(runners_touched)
	return False, 0, 0

@group_required('admins')
def reload_race_results(request, race_id):
	race = get_object_or_404(models.Race, pk=race_id)
	success, n_results, n_runners_touched = reload_parkrun_results(race, request.user)
	if success:
		messages.success(request, u'Результаты загружены заново. Всего результатов: {}, затронуто бегунов: {}'.format(n_results, n_runners_touched))
	else:
		messages.warning(request, u'Протокол забега не найден. Результаты не перезагружены')
	return redirect(race)

# Creates new event and new race if needed
def get_or_create_parkrun_event_and_race(series, url_results, event_date, event_num, user):
	event = series.event_set.filter(start_date=event_date).first()
	race = None
	existed = False
	if event is None:
		start_time = "09:00"
		if (series.id in SERIES_WITH_LATE_START_2018) and (event_date <= datetime.date(2019, 1, 31)):
			start_time = "10:00"
		event = models.Event.objects.create(series=series, number=event_num, start_date=event_date, url_site=series.url_site,
			start_time=start_time, created_by=user, name=series.name + u" №" + unicode(event_num))
		event.clean()
		event.save()
	else:
		existed = True
		race = models.Race.objects.filter(event=event, distance=PARKRUN_DISTANCE).first()
	if url_results and not event.document_set.filter(document_type=models.DOC_TYPE_PROTOCOL).exists():
		models.Document.objects.create(event=event, document_type=models.DOC_TYPE_PROTOCOL,
			loaded_type=models.LOAD_TYPE_NOT_LOADED, url_original=url_results, created_by=user)
	if not race:
		race = models.Race.objects.create(event=event, distance=PARKRUN_DISTANCE, created_by=user)
		race.clean()
		race.save()
	return existed, race

# Creates new event and new race. Returns True(no results yet)/False(results are already loaded) and race id
def create_future_parkruns(series, user, debug=False):
	events_created = 0
	events = models.Event.objects.filter(series=series).order_by('-start_date')
	last_event = events.first()
	if last_event is None:
		models.write_log(u"Couldn't find any events for series {}, id {}. Stopped creating future events.".format(series, series.id), debug=debug)
		return 0
	if last_event.number is None:
		if events.count() == 1:
			last_event.number = 1
			if not last_event.name.endswith(u'№1'):
				last_event.name += u' №1'
			last_event.start_time="09:00"
			last_event.save()
		else:
			models.write_log(u"Problem with event number for series {}, id {}. Stopped creating future events.".format(series, series.id), debug=debug)
			return 0
	if (last_event.number == 1) and not last_event.race_set.exists(): # So it's enough to create first event in series without any distances
		race = models.Race.objects.create(event=last_event, distance=PARKRUN_DISTANCE, created_by=user)
		race.clean()
		race.save()
	event_number = last_event.number + 1
	event_date = last_event.start_date + datetime.timedelta(days=7)
	month_from_now = datetime.date.today() + datetime.timedelta(days=34)
	while event_date <= month_from_now:
		existed, race = get_or_create_parkrun_event_and_race(series, '', event_date, event_number, user)
		if not existed:
			events_created += 1
		event_number += 1
		event_date += datetime.timedelta(days=7)
	return events_created

# Creates events for old parkrun series
def create_future_old_parkrun_events():
	series = models.Series.objects.get(pk=results_util.OLD_PARKRUN_SERIES_ID)
	events_created = 0
	event = series.event_set.order_by('-start_date').first()
	event_date = event.start_date + datetime.timedelta(days=7)
	while (event_date.year <= 2017) and (events_created < 100): 
		event.start_date = event_date
		event.id = None
		event.clean()
		event.save()
		race = models.Race.objects.create(event=event, distance=PARKRUN_DISTANCE, created_by=models.USER_ROBOT_CONNECTOR)
		race.clean()
		race.save()
		event_date += datetime.timedelta(days=7)
		events_created += 1
	print 'Events created:', events_created

# Check: Are there any new runs with current series that are not in base? If yes, load them.
def update_series_results(series, user, reverse_races=False):
	new_races = []
	# print "Trying to read url {}".format(series.url_site + '/results/eventhistory/')
	url_history = series.url_site + '/results/eventhistory/'
	result, response, _ = results_util.read_url(url_history)
	if not result:
		models.send_panic_email(
			'views_parkrun: update_series_results: problem with event history',
			u"Couldn't load event history for {}, id={}, from url {}".format(series.name, series.id, url_history))
		return []
	html = response.read().decode('utf-8')
	new_races_created = False
	parts = parkrun_result_history_re.findall(html)
	if reverse_races:
		parts.reverse()

	runners_touched = set()
	for item in parts:
		url_event, event_num, ev_day, ev_month, ev_year, n_runners = item
		event_date = datetime.date(results_util.int_safe(ev_year), results_util.int_safe(ev_month), results_util.int_safe(ev_day))
		url_results = series.url_site + '/results' + url_event[2:]
		existed, race = get_or_create_parkrun_event_and_race(series, url_results, event_date, results_util.int_safe(event_num), user)
		if race.loaded != models.RESULTS_LOADED:
			models.write_log(u"New event found: {}".format(item))
			n_results, new_runners_touched = load_race_results(race, url_results, user)
			runners_touched |= new_runners_touched
			new_races.append((race, n_results, existed))
			if not existed:
				new_races_created = True
		elif not reverse_races:
			if new_races_created: # Maybe there were some extra parkruns, e.g. for New Year/Christmas
				fix_parkrun_numbers(race.event_id)
			break
	for runner in runners_touched:
		update_runner_stat(runner=runner)
		if runner.user:
			update_runner_stat(user=runner.user, update_club_members=False)
	return new_races, runners_touched

def get_empty_parkruns():
	series_ids = models.Series.get_russian_parkrun_ids() - set([results_util.OLD_PARKRUN_SERIES_ID])
	month_ago = datetime.date.today() - datetime.timedelta(days=30)
	return models.Race.objects.filter(event__series_id__in=series_ids, event__start_date__lte=month_ago).exclude(
		n_participants_finished__gt=0).select_related('event')

def send_update_results(new_races, future_events_created, email):
	body = u"Добрый день!\n\nСвежезагруженные результаты паркранов (всего забегов {}):\n\n".format(len(new_races))
	html_body = u"Добрый день!\n"
	html_body += u"<p/>Свежезагруженные результаты паркранов (всего забегов {}):\n".format(len(new_races))
	i = 1
	for race, n_results, existed in new_races:
		str_existed = ''
		if not existed:
			str_existed = u' (этого забега не было в календаре!)'
		body += u"{} – {}, {}, {} результатов{}\n".format(race.event.start_date, race.event, race.event.url_site, n_results, str_existed)
		html_body += u"<p/>{}. {} – <a href='{}'>{}</a>, <a href='{}{}'>{} результат{}</a>{}\n".format(
			i, race.event.start_date, race.event.url_site, race.event,
			 models.SITE_URL, race.get_absolute_url(), n_results, results_util.plural_ending_new(n_results, 1), str_existed)
		i += 1
	body += u"\n\nСоздано будущих паркранов: {}.".format(future_events_created)
	html_body += u"<p/>Создано будущих паркранов: {}.".format(future_events_created)

	for race in get_empty_parkruns():
		s = u'Найден паркран без результатов: {} {} {}{}'.format(race.event.name, race.event.start_date, models.SITE_URL, race.get_absolute_url())
		body += u"\n\n" + s
		html_body += u"<p/>" + s

	body += u"\n\nНа сегодня это всё. До связи!\nВаш кронтаб."
	html_body += u"<p/>На сегодня это всё. До связи!<p/>Ваш кронтаб."
	return send_mail(u'ПроБЕГ: результаты закачки паркранов', body, models.INFO_MAIL_HEADER, [email], html_message=html_body)

def update_parkrun_results(email=""):
	models.write_log(u"{} Started parkrun update...".format(datetime.datetime.now()))
	new_races = []
	runners_touched = set()
	future_events_created = 0
	for series in models.Series.get_russian_parkruns().filter(is_parkrun_closed=False).order_by('id'):
		races, runners = update_series_results(series, models.USER_ROBOT_CONNECTOR)
		new_races += races
		runners_touched |= runners
		future_events_created += create_future_parkruns(series, models.USER_ROBOT_CONNECTOR)
		time.sleep(5)
	for runner in runners_touched:
		update_runner_stat(runner=runner)
		if runner.user:
			update_runner_stat(user=runner.user, update_club_members=False)
	update_results_count()
	update_events_count()
	models.write_log(u"{} Finished parkrun update.".format(datetime.datetime.now()))
	generate_parkrun_stat_table()
	models.write_log(u"{} Generated new parkrun statistics table.".format(datetime.datetime.now()))
	if email:
		return send_update_results(new_races, future_events_created, email)

def create_parkrun_protocols():
	docs_added = 0
	for series in models.Series.get_russian_parkruns().order_by('id'):
		for event in series.event_set.all():
			if not event.document_set.filter(document_type=models.DOC_TYPE_PROTOCOL).exists():
				models.Document.objects.create(series=series, event=event, document_type=models.DOC_TYPE_PROTOCOL,
					loaded_type=models.LOAD_TYPE_NOT_LOADED, url_original=event.url_site, created_by=models.USER_ROBOT_CONNECTOR
					)
				docs_added += 1
	print 'Finished! Documents added:', docs_added

def create_future_parkruns_once(debug=False): # It should be called when new parkrun series is just created
	for series in models.Series.get_russian_parkruns().filter(is_parkrun_closed=False).order_by('id'):
		n_created = create_future_parkruns(series, models.USER_ROBOT_CONNECTOR, debug=debug)
		if debug:
			print u'Created {} parkruns in series {}'.format(n_created, series.name)
	if debug:
		print 'Finished!'

def fix_parkrun_numbers(correct_event_id=None, correct_event=None): # Enter id of last event (or last event itself) in series with correct number
	if correct_event is None:
		correct_event = models.Event.objects.get(pk=correct_event_id)
	series = correct_event.series
	last_correct_date = correct_event.start_date
	cur_number = correct_event.number
	n_fixed_parkruns = 0
	for event in series.event_set.filter(start_date__gt=last_correct_date).order_by('start_date'):
		cur_number += 1
		event.number = cur_number
		correct_name = u'{} №{}'.format(correct_event.series.name, cur_number)
		if event.name != correct_name:
			event.name = correct_name
			event.save()
			n_fixed_parkruns += 1
	return series, n_fixed_parkruns

def fix_start_times_2018():
	n_fixed = 0
	# for event in models.Event.objects.filter(series_id__in=SERIES_WITH_LATE_START_2018, start_date__gt=datetime.date(2018, 11, 1)):
	# 	event.start_time = "10:00"
	# 	event.save()
	# 	n_fixed += 1
	for event in models.Event.objects.filter(series_id=4426, start_date__gt=datetime.date(2018, 11, 1)):
		event.start_time = "09:00"
		event.save()
		n_fixed += 1
	print 'Done!', n_fixed

def generate_parkrun_stat_table():
	context = {}
	context['strange'] = []
	context['parkruns_data'] = []
	context['today'] = datetime.date.today().strftime("%d.%m.%Y")
	for series in models.Series.get_russian_parkruns().exclude(pk=results_util.OLD_PARKRUN_SERIES_ID).order_by('name'):
		data = {}
		data['series'] = series
		data['name'] = series.name[len('parkrun '):]
		races = models.Race.objects.filter(event__series=series, loaded=models.RESULTS_LOADED)
		data['n_events'] = races.count()
		if data['n_events'] == 0:
			context['parkruns_data'].append(data)
			continue

		data['sum_participants'] = races.aggregate(Sum('n_participants'))['n_participants__sum']
		data['avg_n_participants'] = data['sum_participants'] / data['n_events']
		results = models.Result.objects.filter(race__event__series=series, source=models.RESULT_SOURCE_DEFAULT)
		if results.count() != data['sum_participants']:
			context['strange'].append(u'В серии {} (id {}) сумма чисел участников — {}, а результатов в базе данных — {}'.format(
				series.name, series.id, data['sum_participants'], results.count()))

		parkrun_ids = Counter(results.values_list('parkrun_id', flat=True))
		data['n_different_participants'] = len(parkrun_ids)
		data['most_participations'] = parkrun_ids.most_common(1)[0][1]
		data['most_frequent_participants'] = [(models.Runner.objects.filter(parkrun_id=parkrun_id).first(), n)
			for parkrun_id, n in parkrun_ids.most_common(3)]
		data['women_percent'] = int(round((100 * results.filter(gender=models.GENDER_FEMALE).count()) / data['sum_participants']))

		for key, gender in (('male', models.GENDER_MALE), ('female', models.GENDER_FEMALE)):
			results_by_gender = results.filter(gender=gender).order_by('result')
			n_results_by_gender = results_by_gender.count()
			best_result = results_by_gender.first()
			if best_result:
				data[key + '_record'] = models.centisecs2time(best_result.result)
				data[key + '_recordsman'] = best_result.runner
				data[key + '_mean'] = models.centisecs2time(sum(results_by_gender.values_list('result', flat=True)) // n_results_by_gender,
					round_hundredths=True)
				data[key + '_median'] = results_by_gender[(n_results_by_gender - 1) // 2]

		context['parkruns_data'].append(data)
	generate_html('generators/parkrun_table.html', context, 'parkrun_table.html')

# In October 2019 parkrun changed the URLs of result pages:
#    https://www.parkrun.ru/timiryazevsky/weeklyresults/?runSeqNumber=233
# -> https://www.parkrun.ru/timiryazevsky/results/weeklyresults/?runSeqNumber=233
def fix_parkrun_protocol_urls():
	n_fixed = 0
	for doc in models.Document.objects.filter(document_type=models.DOC_TYPE_PROTOCOL,
			url_original__startswith='http://www.parkrun.ru'):
		doc.url_original = doc.url_original.replace('http://', 'https://')
		doc.save()
		n_fixed += 1
	print('https is added: {} protocols'.format(n_fixed))

	n_fixed = 0
	for doc in models.Document.objects.filter(document_type=models.DOC_TYPE_PROTOCOL,
			url_original__contains='//weeklyresults'):
		doc.url_original = doc.url_original.replace('//weeklyresults', '/results/weeklyresults')
		doc.save()
		n_fixed += 1
	print('// to /results: {} protocols'.format(n_fixed))

	n_fixed = 0
	for doc in models.Document.objects.filter(document_type=models.DOC_TYPE_PROTOCOL,
			url_original__contains='/weeklyresults').exclude(url_original__contains='/results/weeklyresults'):
		doc.url_original = doc.url_original.replace('/weeklyresults', '/results/weeklyresults')
		doc.save()
		n_fixed += 1
	print('/results added: {} protocols'.format(n_fixed))

def test_regexp():
	# url_results = 'https://www.parkrun.ru/volgogradpanorama/results/weeklyresults/?runSeqNumber=199'
	url_results = 'https://www.parkrun.ru/stavropol/results/eventhistory/'
	result, response, _ = results_util.read_url(url_results)
	if not result:
		print(u'Could not load results from url {}'.format(url_results))
		return
	html = response.read().decode('utf-8')
	r = re.compile(parkrun_result_history_re)
	for i, obj in enumerate(r.finditer(html)):
		print(u'{}. {}'.format(i, u', '.join(u'{}: {}'.format(k, v.strip() if v else v) for k, v in obj.groupdict().items())))

# If some parkrun didn't happen, we remove it and fix the numbers
def _delete_skipped_parkrun(race):
	event = race.event
	series = event.series
	if not series.is_russian_parkrun():
		return False, u'Это — не российский паркран'
	races_count = event.race_set.count()
	if races_count != 1:
		return False, u'Дистанций у забега {}, а не одна. Что-то не так'.format(races_count)
	if race.result_set.exists():
		return False, u'У забега уже есть загруженные результаты'
	if event.document_set.filter(document_type=models.DOC_TYPE_PROTOCOL).exists():
		return False, u'У забега уже есть протокол'
	race.delete()
	prev_event = series.event_set.filter(start_date__lt=event.start_date).order_by('-start_date').first()
	event.delete()
	if prev_event:
		fix_parkrun_numbers(correct_event=prev_event)
	return True, ''

@group_required('admins')
def delete_skipped_parkrun(request, race_id):
	race = get_object_or_404(models.Race, pk=race_id)
	series = race.event.series
	success, error = _delete_skipped_parkrun(race)
	if success:
		messages.success(request, u'Паркран успешно удалён. Номера последующих паркранов исправлены')
		return redirect(series)
	else:
		messages.warning(request, u'Паркран не удалён. Причина: {}'.format(error))
		return redirect(race)
