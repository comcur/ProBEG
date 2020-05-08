from django.core.management.base import BaseCommand

from results import models
from editor.views.views_result import fix_all_partially_loaded_results
# from results.views.views_report import get_age_stat, get_result_stat, get_result_quantiles, get_regions_stat, get_min_n_participants
# from results.views.views_report import check_distinct_results, get_min_n_participants_v2
# from results.views.views_report import get_n_participants
# from editor.views import views_klb_stat
# from editor.views.views_nn import connect_runners_with_birthday
from editor.views.views_klb_stat import update_match, fix_team_numbers
# from editor.views.views_klb_report import main_test2
# from editor.views.views_result import make_names_title

class Command(BaseCommand):
	help = 'Works with KLBresults'

	def handle(self, *args, **options):
		# views_klb.fill_klb_races()
		# views_klb.fill_klb_results(year=2010)
		# views_klb.fill_was_real_distance_used()
		# views_klb.check_klb_scores()
		# views_klb.fill_bonus_score()

		# views_klb.update_match(debug=True)
		# views_klb.check_score_sums()
		# views_klb.create_results_for_klb(debug=True, year=2010)
		# views_klb.check_klb_meters_results()

		# views_klb.fill_match_places()
		# views_klb.fill_teams(year=2015)
		# views_document.fill_document_ids()

		# views_result.attach_results_with_birthday()
		# views_stat.update_runners_stat(debug=True)
		# views_user.send_messages_with_results()
		# fill_age_categories(to_save=0)
		# get_age_stat()
		# get_result_stat()
		# get_result_quantiles()
		# get_regions_stat()
		# get_min_n_participants()
		# get_min_n_participants_v2()
		# check_distinct_results()
		# views_klb_stat.check_deleted_results()
		# connect_runners_with_birthday()
		# update_events_count()
		# make_names_title()
		# get_n_participants()
		# fix_team_numbers(2017)
		update_match(year=2020, debug=True)
		# main_test2(1)
		# find_empty_parkruns()
		# for i in (38261, 29768, 18606, 35666, 35468, 18606, 35468, 18606, 35468, 29768, ):
		# 	fix_hours_minutes(i)
		# fix_all_partially_loaded_results()
		