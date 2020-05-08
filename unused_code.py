# Moved from editor.views.views_klb
def fill_was_real_distance_used(): # Isn't used. Now we fill was_real_distance_used in /klb_status
	dist1 = 0
	dist2 = 0
	distances_absent = set()
	distances_wrong = set()
	distances_not_parsed = set()
	klb_results = models.Klb_result.objects.filter(race__isnull=False, # race__event__start_date__year=models.CUR_KLB_YEAR,
			was_real_distance_used=models.DISTANCE_FOR_KLB_UNKNOWN)
	print "Results to work:", klb_results.count()
	i = 0
	for klb_result in klb_results:
		i += 1
		if (i % 500) == 0:
			print i
		race = klb_result.race
		distance_type, length = get_distance(klb_result.distance_raw, klb_result.time_seconds_raw)
		if distance_type is None:
			distances_not_parsed.add((race.id, klb_result.distance_raw, klb_result.time_seconds_raw))
			continue
		distance = models.Distance.objects.filter(distance_type=distance_type, length=length).first()
		if distance is None:
			distances_absent.add((race.id, distance_type, length))
			continue
		if race.distance == distance:
			dist1 += 1
			klb_result.was_real_distance_used = models.DISTANCE_FOR_KLB_FORMAL
			klb_result.save()
		elif race.distance_real == distance:
			dist2 += 1
			klb_result.was_real_distance_used = models.DISTANCE_FOR_KLB_REAL
			klb_result.save()
		else:
			distances_wrong.add((race.id, klb_result.distance_raw, klb_result.time_seconds_raw))
	print 'Formal distances:', dist1
	print 'Real distances:', dist2
	print "Not parsed distances:", len(distances_not_parsed)
	print 'Absent distances:', len(distances_absent)
	print 'Wrong distances:', len(distances_wrong)

def fill_klb_races(): # Isn't used. Open /klb_status instead
	events_absent = set()
	distances_not_parsed = set()
	distances_absent = set()
	races_absent = set()
	# for event_id, distance_raw, time_seconds_raw in set(models.Klb_result.objects.filter(
	# 		race=None, last_update__year__gte=models.CUR_KLB_YEAR).values_list('event_raw', 'distance_raw', 'time_seconds_raw')):
	n_results = 0
	for result in models.Klb_result.objects.filter(race=None).select_related('event_raw'): #, last_update__year__gte=models.CUR_KLB_YEAR):
		distance_raw = result.distance_raw
		time_seconds_raw = result.time_seconds_raw
		event = result.event_raw
		if event is None:
			events_absent.add(result.id)
			continue
		distance_type, length = get_distance(distance_raw, time_seconds_raw)
		if distance_type is None:
			distances_not_parsed.add((event.id, distance_raw, time_seconds_raw))
			continue
		distance = models.Distance.objects.filter(distance_type=distance_type, length=length).first()
		if distance is None:
			distances_absent.add((event.id, distance_type, length))
			continue
		race = event.race_set.filter(Q(distance=distance) | Q(distance_real=distance)).first()
		if race is None:
			races_absent.add((event, distance))
			continue
		result.race = race
		result.save()
		n_results += 1
		if n_results % 500 == 0:
			print n_results
	print "Absent events:", len(events_absent)
	print "Not parsed distances:", len(distances_not_parsed)
	print "Absent distances:", len(distances_absent)
	print "Absent races:", len(races_absent)
	print "Races filled in KLB results:", n_results

def fill_klb_results(year=models.CUR_KLB_YEAR): # Isn't used. Open /klb_status instead
	results_absent = {}
	results_found = 0
	race_ids = set(models.Klb_result.objects.filter(
		Q(result=None) | Q(result__source=models.RESULT_SOURCE_KLB),
		race__event__start_date__year__gte=year,
	).values_list('race__id', flat=True))
	races = models.Race.objects.filter(loaded=1, id__in=race_ids).select_related('distance').order_by('id')
	print 'Races to work:', races.count()
	for race in races:
		results = race.klb_result_set.filter(Q(result=None) | Q(result__source=models.RESULT_SOURCE_KLB)).select_related('klb_person')
		for klb_result in results:
			result_found = False
			result = models.Result.objects.filter(race=race, lname=klb_result.klb_person.lname, fname=klb_result.klb_person.fname).first()
			if result:
				results_are_equal = False
				if race.distance.distance_type == models.TYPE_MINUTES:
					parsed, meters = distance2meters(klb_result.distance_raw)
					if parsed and (result.result == meters):
						results_are_equal = True
				else: # Distance type is regular
					seconds = int(math.ceil(result.result / 100)) if (result.result % 100) else (result.result // 100)
					if seconds == klb_result.time_seconds_raw:
						results_are_equal = True
				if results_are_equal:
					if klb_result.result: # Now this result with source=RESULT_SOURCE_KLB isn't needed
						klb_result.result.delete()
					klb_result.result = result
					klb_result.save()
					klb_person = klb_result.klb_person
					if result.runner is None:
						runner, created = klb_person.get_or_create_runner(request.user)
						result.runner = runner
						result.save()
					result_found = True
					results_found += 1
			if not result_found:
				if race.id in results_absent:
					results_absent[race.id].add((klb_result, result))
				else:
					results_absent[race.id] = set([(klb_result, result)])
	print 'Results found:', results_found
	print "Results not found:", len(results_absent)
	# for race, results in results_absent.items():
	# 	print "Race", race, ":",
	# 	print '\n'.join([unicode(x) + ', ' + unicode(y) for x, y in results])

def check_klb_score_for_result(klb_result, debug=False):
	my_score = get_klb_score_for_result(klb_result, debug)
	return (klb_result.klb_score == my_score), my_score

def check_klb_scores():
	debug = False
	i = 0
	for result in models.Klb_result.objects.filter(result__race__event__start_date__year=models.CUR_KLB_YEAR,
			was_real_distance_used__gt=models.DISTANCE_FOR_KLB_UNKNOWN).order_by('-id'):
	# for result in models.Klb_result.objects.filter(id=70161,
	# 		was_real_distance_used__gt=models.DISTANCE_FOR_KLB_UNKNOWN).order_by('-id')[:1000]:
		equal, my_score = check_klb_score_for_result(result, debug=debug)
		if not equal:
			print "Wrong result! id {}, person id {}, actual value: {}, my value: {}".format(
				result.id, result.klb_person.id, result.klb_score, my_score)
		i += 1
	print 'Finished! Results tried:', i

def check_klb_meters_results(): # There were mistakes with rounding results
	results_ok = 0
	results_wrong = []
	problems = []
	for klb_result in models.Klb_result.objects.filter(result__race__distance__distance_type=models.TYPE_MINUTES):
		parsed, value = klb_result2value(klb_result)
		if parsed:
			if value == klb_result.result.result:
				results_ok += 1
			else:
				results_wrong.append((klb_result.klb_person.id, value, klb_result.result.result))
		else:
			problems.append((klb_result.klb_person.id, klb_result.race.id, klb_result.time_seconds_raw))
	print "Results OK:", results_ok
	print "Results wrong:", results_wrong
	print "Not parsed:", problems

def check_score_sums():
	THREEPLACES = Decimal('0.001')
	getcontext().rounding = ROUND_HALF_UP
	wrong_score = []
	wrong_bonus = []
	n_correct_score = 0
	team_scores = {}
	team_bonuses = {}
	for participant in models.Klb_participant.objects.filter(match_year=models.CUR_KLB_YEAR):
		results = participant.klb_person.klb_result_set.filter(race__event__start_date__year=models.CUR_KLB_YEAR)
		score_sum = results.filter(is_in_best=True).aggregate(Sum('klb_score'))['klb_score__sum']
		if score_sum is None:
			score_sum = Decimal(0)
		bonus_sum = results.filter(is_in_best_bonus=True).aggregate(Sum('bonus_score'))['bonus_score__sum']
		if bonus_sum is None:
			bonus_sum = Decimal(0)
		# score_orig = Decimal(participant.score_sum - participant.bonus_sum).quantize(THREEPLACES)
		# bonus_orig = Decimal(participant.bonus_sum).quantize(THREEPLACES)
		score_orig = participant.score_sum - participant.bonus_sum
		bonus_orig = participant.bonus_sum
		if abs(score_sum - score_orig) > THREEPLACES:
		# if score_sum != score_orig:
			wrong_score.append((participant.klb_person.id, score_orig, score_sum))
		elif abs(bonus_sum - bonus_orig) > THREEPLACES:
		# elif bonus_sum != bonus_orig:
			wrong_bonus.append((participant.klb_person.id, bonus_orig, bonus_sum))
		else:
			n_correct_score += 1
		team = participant.klb_person.get_team()
		if team:
			team_scores[team.id] = team_scores.get(team.id, 0) + score_sum
			team_bonuses[team.id] = team_bonuses.get(team.id, 0) + bonus_sum
	print "Wrong scores:", wrong_score
	print "Wrong bonuses:"
	for it in wrong_bonus:
		print it
	print "Correct scores:", n_correct_score
	wrong_score_team = []
	wrong_bonus_team = []
	n_correct_score_team = 0
	for team in models.Klb_team.objects.filter(year=models.CUR_KLB_YEAR).exclude(number=models.INDIVIDUAL_RUNNERS_CLUB_NUMBER):
		score_sum = team_scores.get(team.id, 0)
		bonus_sum = team_bonuses.get(team.id, 0)
		score_orig = team.score - team.bonus_score
		bonus_orig = team.bonus_score
		if abs(score_sum - score_orig) > THREEPLACES:
			wrong_score_team.append((team.id, score_orig, score_sum))
		elif abs(bonus_sum - bonus_orig) > THREEPLACES:
		# elif bonus_sum != bonus_orig:
			wrong_bonus_team.append((team.id, bonus_orig, bonus_sum))
		else:
			n_correct_score_team += 1
	print "Wrong team scores:", wrong_score_team
	print "Wrong team bonuses:"
	for it in wrong_bonus_team:
		print it
	print "Correct team scores:", n_correct_score_team

def delete_klb_results(request):
	if request.method == 'POST':
		results_deleted = 0
		touched_persons = set()
		touched_teams = set()
		for key, val in request.POST.items():
			if key.startswith("to_delete_"):
				klb_result_id = models.int_safe(key[len("to_delete_"):])
				klb_result = models.Klb_result.objects.filter(id=klb_result_id).first()
				if not klb_result:
					messages.warning(request, u'Результат с id {} не найден. Пропускаем'.format(klb_result_id))
					continue
				touched_persons.add(klb_result.klb_person)
				team = klb_result.klb_person.get_team()
				if team:
					touched_teams.add(team)
				models.log_obj_delete(request.user, klb_result.event_raw, child_object=klb_result, action_type=models.ACTION_KLB_RESULT_DELETE)
				klb_result.delete()
				results_deleted += 1
		if results_deleted:
			messages.success(request, u'Из КЛБМатча удалено результатов: {}'.format(results_deleted))
		if touched_persons:
			update_persons_score(year=models.CUR_KLB_YEAR, persons_to_update=touched_persons)
			messages.success(request, u'Затронуто участников Матча: {}. Их результаты пересчитаны.'.format(len(touched_persons)))
		if touched_teams:
			messages.success(request, u'Затронуты команды: {}'.format(', '.join(team.name for team in touched_teams)))
	return redirect('editor:klb_status')
