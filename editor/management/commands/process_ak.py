# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
import datetime

from results import models, results_util
from results.views import views_report
from results.views.views_user import send_letters_with_code
from editor.views.views_mail import send_old_messages
from editor.views.views_stat import generate_default_calendar
from editor.views.views_klb_stat import generate_klb_winners_by_regions
from editor.views.views_age_group_record import generate_better_age_group_results
from editor.views.views_parkrun import fix_parkrun_protocol_urls, test_regexp

class Command(BaseCommand):
	help = 'Worked with AK55 base. Now does strange things'

	def handle(self, *args, **options):
		print datetime.datetime.now()
		views_report.generate_country_report('BY', 2018, tabs=[0])
		# views_report.generate_country_report('RU', 2019, tabs=[1])
		# print datetime.datetime.now()
		results_util.restart_django()
		# generate_better_age_group_results(country_id='RU', debug=1)
		# views_report.count_min_n_participants('RU', year=2018)
		# views_report.count_min_n_participants('RU', year=2019)
		# generate_default_calendar()
		# send_old_messages(41991)
		# send_letters_with_code()
		# check_bonuses(2019, 20)
		# check_bonuses(2020)
		# check_wrong_results(2019)
		# delete_unpaid_participants(2019, test_mode=True)
		# delete_unpaid_participants(2019, test_mode=False)
		# create_all_for_new_match(2020)
		# send_letters_to_unpaid_team_participants(test_mode=True)
		# print_most_active_users()
		# update_match(2019)
		# send_letters_for_not_paid_teams(2019, test_mode=True)
		# send_letters_for_not_paid_teams(2019, test_mode=False)
		# send_letters_to_not_paid_participants()
		# teams_with_professionals()
		# test_regexp()
		# fix_parkrun_protocol_urls()
		# update_match(year=models.CUR_KLB_YEAR, debug=True)
		# send_letters_to_not_paid_participants
		# add_participants_to_payment()
		# make_connections_small()
		# make_connections()
		# send_messages_with_results()
		# fix_partially_loaded_results(models.Race.objects.get(pk=31487))
		# update_all_tuples()
		# update_records_for_given_tuple(models.Country.objects.get(pk='RU'), 1, models.Record_age_group.objects.get(age_min=55),
		# 	models.Distance.objects.get(pk=232), False)
		# generate_better_age_group_results(country_id='BY', debug=1)
		# update_records_once()
		# fill_n_parkrun_results_once()
		# generate_parkrun_stat_table()
		# get_min_n_participants_v2()
		# get_n_finishers_wo_parkrun()
		# load_splits()
		# generate_russia_report()
		# create_age_groups()
		# update_runners_stat(id_from=0, debug=1)
		# fill_match_places(year=2019)
		# print datetime.datetime.now()
		# generate_events_in_seria_by_year2()
		# print datetime.datetime.now()
		# print get_db_checks_report()
		# print check_users_and_runners_links(None)
		# add_participants_to_payment()
		# for club in models.Club.objects.filter(id__gte=34).exclude(pk=166).order_by('pk'):
		# 	# create_club_members(club)
		# 	time_started = datetime.datetime.now()
		# 	for member in club.club_member_set.all():
		# 		update_runner_stat(club_member=member)
		# 	print u'Done! {} members of club {} (id {}) are updated. Time spent: {}'.format(club.club_member_set.count(), club.name, club.id,
		# 		datetime.datetime.now() - time_started)

		# connect_runners_with_fi_maybe_o()
		# fill_cities_for_just_connected_runners()

		# get_result_stat()
		# get_result_quantiles()

		# get_results_for_melekhov()
		# get_result_quantiles_context()

		# update_klb_result_bonuses()

		# reset_series_by_letter()

		# update_match(year=models.CUR_KLB_YEAR, debug=True)

		# generate_last_added_reviews()
		# update_race_size_stat(debug=True)
		# make_connections()
		# compare_with_old_results()
		# generate_parkrun_stat_table()
		# fix_start_times_2018()
		# fix_all_partially_loaded_results()
		# find_too_slow_results()
		# make_connections()
		# fix_results_gender()
		# set_unique_starts_as_race_records()
		# print_different_scores()
		# print try_different_match_formulas()
		# create_all_for_new_match(2019)
		# most_popular_clubs()
		# fill_bonus_score(2019)
		# update_match(year=models.NEXT_KLB_YEAR, debug=True)
		# reload_parkrun_results(models.Race.objects.get(pk=44684), models.USER_ADMIN)
		# generate_reg_activity()
		# generate_klb_winners_by_regions(2019)
		# generate_klb_winners_by_regions(2018)
		# generate_klb_winners_by_regions(2017)
		# generate_klb_winners_by_regions(2016)
		# generate_klb_winners_by_regions(2015)
		# print_teams_without_captains()

		# send_sample_payment_email()

		# send_messages_with_results()

		# fix_categories_case()

		# update_club_members_stat()

		# for member in club.club_member_set.order_by('date_registered', 'date_removed'):
		# 	print member.date_registered, member.date_removed, member.runner.fname, member.runner.lname, member.email, member.phone_number		# views_klb.fill_klb_races()
		# views_ak.mark_equal_results_in_race_step2()
		# views_ak.update_field_in_ex_ak_result(ak_result_id=77468, old_ak_result_id=235856, race_id=4565,
		# 	field_names=['comment', 'comment_raw'], ak_field_name='comment')
		# views_ak.update_field_in_ex_ak_result(ak_result_id=346208, old_ak_result_id=346208, result_id=387984,
		# 	field_names=['comment', 'comment_raw'], ak_field_name='comment')
		# views_ak.update_manids_for_v2()
		# for r in models.Runner.objects.filter(gender=0,ak_person__isnull=False).select_related('ak_person').order_by('pk')[:20000]:
		# 	r.gender = models.GENDER_MALE if r.ak_person.gender_raw.lower() == u'м' else models.GENDER_FEMALE
		# 	r.save()
		# for r in models.Runner.objects.filter(gender=0, user__user_profile__isnull=False).select_related('user__user_profile').order_by('pk')[:20000]:
		# 	r.gender = r.user.user_profile.gender
		# 	r.save()
		# for runner in models.Runner.objects.filter(gender=0, parkrun_id__gt=0):
		# 	result = runner.result_set.filter(parkrun_id__gt=0).first()
		# 	if result:
		# 		runner.gender = result.gender
		# 		runner.save()
		# for runner in models.Runner.objects.filter(gender=0, parkrun_id__gt=0):
		# 	result = runner.result_set.filter(parkrun_id__gt=0).first()
		# 	if result:
		# 		runner.gender = result.gender
		# 		runner.save()
		# print models.Runner.objects.filter(gender=0).count()
		# print 'Finished!'
		# for year in range(2010, 2017):
		# 	fill_klb_result_participants(year)
		# generate_events_in_seria_by_year(debug=True)
		# fill_klb_results_for_car_2()
		# get_runner_quantity_in_series(3854)
		# connect_winner_runners()
		# check_document_old_fields()
