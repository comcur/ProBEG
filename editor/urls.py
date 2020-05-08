# -*- coding: utf-8 -*-
from django.conf.urls import url
from django.views.generic import RedirectView

from .views import views_ajax, views_city, views_distance, views_document, views_event, views_klb, views_news, views_user_actions
from .views import views_protocol, views_race, views_region, views_result, views_runner, views_series, views_site, views_social, views_user
from .views import views_klb_race, views_klb_person, views_parkrun, views_mail, views_club, views_klb_team, views_name, views_registration, views_payment
from .views import views_db_structure, views_klb_report, views_util, views_organizer, views_klb_stat, views_age_group_record

app_name = 'editor'

urlpatterns = [
	url(r'^cities/$', views_city.cities, name='cities'),
	url(r'^cities/country/(?P<country_id>[A-Za-z]+)/$', views_city.cities, name='cities'),
	url(r'^cities/region/(?P<region_id>[0-9]+)/$', views_city.cities, name='cities'),

	url(r'^city/(?P<city_id>[0-9]+)/$', views_city.city_details, name='city_details'),
	url(r'^city/(?P<city_id>[0-9]+)/update/$', views_city.city_update, name='city_update'),
	url(r'^city/(?P<city_id>[0-9]+)/delete/$', views_city.city_delete, name='city_delete'),
	url(r'^city/create/$', views_city.city_create, name='city_create'),
	url(r'^city/create/region/(?P<region_id>[0-9]+)/$', views_city.city_create, name='city_create'),
	url(r'^city/(?P<city_id>[0-9]+)/history/$', views_city.city_changes_history, name='city_changes_history'),

	url(r'^cities/list/$', views_ajax.cities_list, name='cities_list'),
	url(r'^cities/list_by_name/$', views_ajax.cities_list_by_name, name='cities_list_by_name'),
	url(r'^klb/participants/list/race/(?P<race_id>[0-9]+)/$', views_ajax.participants_list, name='participants_list'),
	url(r'^klb/unpaid_participants/list/$', views_ajax.unpaid_participants_list, name='unpaid_participants_list'),
	url(r'^race/(?P<race_id>[0-9]+)/results/list/$', views_ajax.race_result_list, name='race_result_list'),
	url(r'^runners/list/$', views_ajax.runners_list, name='runners_list'),
	url(r'^runners/list/runner/(?P<runner_id>[0-9]+)/$', views_ajax.runners_list, name='runners_list'),
	url(r'^runners/list/race/(?P<race_id>[0-9]+)/$', views_ajax.runners_list, name='runners_list'),
	url(r'^organizers/list/$', views_ajax.organizers_list, name='organizers_list'),
	url(r'^organizers/list/organizer/(?P<organizer_id>[0-9]+)/$', views_ajax.organizers_list, name='organizers_list'),
	url(r'^series/list/$', views_ajax.series_list, name='series_list'),
	url(r'^series/list/organizer/(?P<organizer_id>[0-9]+)/$', views_ajax.series_list, name='series_list'),
	url(r'^persons/list/$', views_ajax.persons_list, name='persons_list'),
	url(r'^persons/list/person/(?P<person_id>[0-9]+)/$', views_ajax.persons_list, name='persons_list'),

	url(r'^series/$', views_series.seria, name='seria'),
	url(r'^series/country/(?P<country_id>[A-Za-z]+)/$', views_series.seria, name='seria'),
	url(r'^series/region/(?P<region_id>[0-9]+)/$', views_series.seria, name='seria'),
	url(r'^series/city/(?P<city_id>[0-9]+)/$', views_series.seria, name='seria'),
	url(ur'^series/name/(?P<series_name>[A-Za-zА-Яа-я]+)/$', views_series.seria, name='seria'),
	url(r'^events_wo_protocol/(?P<year>[0-9]+)/$', views_series.events_wo_protocol, name='events_wo_protocol'),
	url(r'^events_wo_protocol_for_klb/(?P<year>[0-9]+)/$', views_series.events_wo_protocol_for_klb, name='events_wo_protocol_for_klb'),
	url(r'^events_not_in_next_year/(?P<year>[0-9]+)/$', views_series.events_not_in_next_year, name='events_not_in_next_year'),
	url(r'^events_wo_statistics/(?P<year>[0-9]+)/$', views_series.events_wo_statistics, name='events_wo_statistics'),
	url(r'^all_events_by_year/regions/(?P<regions>[0-9]+)/$', views_series.all_events_by_year, name='all_events_by_year'),
	url(r'^events_in_seria_by_year/$', views_series.events_in_seria_by_year, name='events_in_seria_by_year'),
	url(r'^events_with_xls_protocol/$', views_series.events_with_xls_protocol, name='events_with_xls_protocol'),
	url(r'^events_in_klb/$', views_series.events_in_klb, name='events_in_klb'),
	url(r'^series_wo_new_event/$', views_series.series_wo_new_event, name='series_wo_new_event'),

	url(r'^series_by_letter/(?P<letter>[^/]+)/$', views_series.series_by_letter, name='series_by_letter'),
	url(r'^series_by_letter/$', views_series.series_by_letter, name='series_by_letter'),

	url(r'^series/(?P<series_id>[0-9]+)/$', views_series.series_details, name='series_details'),
	url(r'^series/(?P<series_id>[0-9]+)/update/$', views_series.series_update, name='series_update'),
	url(r'^series/(?P<series_id>[0-9]+)/delete/$', views_series.series_delete, name='series_delete'),
	url(r'^series/(?P<series_id>[0-9]+)/update_documents/$', views_series.series_documents_update, name='series_documents_update'),

	url(r'^series/create/$', views_series.series_create, name='series_create'),
	url(r'^series/create/series/(?P<series_id>[0-9]+)/$', views_series.series_create, name='series_create'),
	url(r'^series/create/country/(?P<country_id>[A-Za-z]+)/$', views_series.series_create, name='series_create'),
	url(r'^series/create/region/(?P<region_id>[0-9]+)/$', views_series.series_create, name='series_create'),
	url(r'^series/create/city/(?P<city_id>[0-9]+)/$', views_series.series_create, name='series_create'),
	url(r'^series/(?P<series_id>[0-9]+)/history/$', views_series.series_changes_history, name='series_changes_history'),

	url(r'^event/(?P<event_id>[0-9]+)/$', views_event.event_details, name='event_details'),
	url(r'^event/(?P<event_id>[0-9]+)/news/(?P<news_id>[0-9]+)/$', views_event.event_details, name='event_details'),
	url(r'^event/(?P<event_id>[0-9]+)/update/$', views_event.event_update, name='event_update'),
	url(r'^event/(?P<event_id>[0-9]+)/update_distances/$', views_event.event_distances_update, name='event_distances_update'),
	url(r'^event/(?P<event_id>[0-9]+)/update_documents/$', views_event.event_documents_update, name='event_documents_update'),
	url(r'^event/(?P<event_id>[0-9]+)/update_news/$', views_event.event_news_update, name='event_news_update'),
	url(r'^event/(?P<event_id>[0-9]+)/delete/$', views_event.event_delete, name='event_delete'),
	url(r'^event/(?P<event_id>[0-9]+)/change_series/$', views_event.event_change_series, name='event_change_series'),
	url(r'^event/(?P<event_id>[0-9]+)/copy/$', views_event.event_create, name='event_create'),
	url(r'^series/(?P<series_id>[0-9]+)/event/create/$', views_event.event_create, name='event_create'),
	url(r'^event/(?P<event_id>[0-9]+)/history/$', views_event.event_changes_history, name='event_changes_history'),
	url(r'^event/(?P<event_id>[0-9]+)/make_news/$', views_event.event_details_make_news, name='event_details_make_news'),
	url(r'^event/(?P<event_id>[0-9]+)/remove_races_with_no_results/$', views_event.remove_races_with_no_results, name='remove_races_with_no_results'),

	url(r'^refresh_default_calendar/$', views_event.refresh_default_calendar, name='refresh_default_calendar'),
	url(r'^restart/$', views_site.restart, name='restart'),

	url(r'^race/(?P<race_id>[0-9]+)/$', views_race.race_details, name='race_details'),
	url(r'^race/(?P<race_id>[0-9]+)/update/$', views_race.race_update, name='race_update'),
	url(r'^race/(?P<race_id>[0-9]+)/fill_places/$', views_result.race_fill_places, name='race_fill_places'),
	url(r'^race/(?P<race_id>[0-9]+)/swap/(?P<swap_type>[0-9]+)/$', views_result.race_swap_names, name='race_swap_names'),
	url(r'^race/(?P<race_id>[0-9]+)/update_headers/$', views_result.update_race_headers, name='update_race_headers'),
	url(r'^race/(?P<race_id>[0-9]+)/update_stat/$', views_race.race_update_stat, name='race_update_stat'),
	url(r'^race/(?P<race_id>[0-9]+)/reload_parkrun/$', views_parkrun.reload_race_results, name='reload_parkrun_results'),
	url(r'^race/(?P<race_id>[0-9]+)/delete_skipped_parkrun/$', views_parkrun.delete_skipped_parkrun, name='delete_skipped_parkrun'),
	url(r'^race/(?P<race_id>[0-9]+)/add_unoff_result/$', views_race.race_add_unoff_result, name='race_add_unoff_result'),
	url(r'^race/(?P<race_id>[0-9]+)/delete_off_results/$', views_race.race_delete_off_results, name='race_delete_off_results'),

	url(r'^regions/$', views_region.regions, name='regions'),
	url(r'^regions/country/(?P<country_id>[A-Za-z]+)/$', views_region.regions, name='regions'),

	url(r'^distances/$', views_distance.distances, name='distances'),
	url(r'^distance/(?P<distance_id>[0-9]+)/$', views_distance.distance_details, name='distance_details'),
	url(r'^distance/(?P<distance_id>[0-9]+)/update/$', views_distance.distance_update, name='distance_update'),
	url(r'^distance/(?P<distance_id>[0-9]+)/delete/$', views_distance.distance_delete, name='distance_delete'),
	url(r'^distance/(?P<distance_id>[0-9]+)/history/$', views_distance.distance_changes_history, name='distance_changes_history'),

	url(r'^distance/create/$', views_distance.distance_create, name='distance_create'),

	url(r'^dist_splits/$', views_distance.dist_splits, name='dist_splits'),

	url(r'^create_distances_from_dists/$', views_distance.create_distances_from_dists, name='create_distances_from_dists'),

	url(r'^documents/add/$', views_document.add_docs, name='add_docs'),
	url(r'^documents/add_to_old_fields/$', views_document.add_docs_to_old_fields, name='add_docs_to_old_fields'),

	# url(r'^district/(?P<district_id>[0-9]+)/$', views.district_details, name='district_details'),
	# url(r'^district/(?P<district_id>[0-9]+)/update/$', views.district_update, name='district_update'),

	url(r'^result/(?P<result_id>[0-9]+)/$', views_result.result_details, name='result_details'),
	url(r'^result/(?P<result_id>[0-9]+)/update/$', views_result.result_update, name='result_update'),
	url(r'^result/(?P<result_id>[0-9]+)/delete/$', views_result.result_delete, name='result_delete'),
	url(r'^result/(?P<result_id>[0-9]+)/update_splits/$', views_result.result_splits_update, name='result_splits_update'),
	url(r'^result/(?P<result_id>[0-9]+)/klb_add/$', views_result.result_add_to_klb, name='result_klb_add'),
	url(r'^result/(?P<result_id>[0-9]+)/klb_delete/$', views_result.result_delete_from_klb, name='result_klb_delete'),
	url(r'^result/(?P<result_id>[0-9]+)/mark_as_error/$', views_result.result_mark_as_error, name='result_mark_as_error'),

	url(r'^runner/(?P<runner_id>[0-9]+)/$', views_runner.runner_details, name='runner_details'),
	url(r'^runner/(?P<runner_id>[0-9]+)/update/$', views_runner.runner_update, name='runner_update'),
	url(r'^runner/(?P<runner_id>[0-9]+)/delete/$', views_runner.runner_delete, name='runner_delete'),
	url(r'^runner/(?P<runner_id>[0-9]+)/history/$', views_runner.runner_changes_history, name='runner_changes_history'),
	url(r'^runner/(?P<runner_id>[0-9]+)/update_stat/$', views_runner.runner_update_stat, name='runner_update_stat'),
	url(r'^runner/create/$', views_runner.runner_create, name='runner_create'),
	url(r'^runner/create/(?P<lname>[^/]+)/(?P<fname>[^/]+)/$', views_runner.runner_create, name='runner_create'),

	# url(r'^add_distances_from_ak_rezult/$', views_ak.add_distances_from_ak_rezult, name='add_distances_from_ak_rezult'),

	# url(r'^result/load_results_from_ak_rezult/$', views_ak.load_results_from_ak_rezult, name='load_results_from_ak_rezult'),
	# url(r'^result/load_results_from_ak_rezult/ak/(?P<ak_id>[A-Za-z0-9]+)/$',
	# 	views_ak.load_results_from_ak_rezult, name='load_results_from_ak_rezult'),
	# url(r'^result/load_results_from_ak_rezult/ak/(?P<ak_id>[A-Za-z0-9]+)/force/(?P<force>[0-9]+)/$',
	# 	views_ak.load_results_from_ak_rezult, name='load_results_from_ak_rezult'),
	# url(r'^result/load_results_from_ak_rezult/ak/(?P<ak_id>[A-Za-z0-9]+)/force/(?P<force>[0-9]+)/race/(?P<race_only_id>[0-9]+)/$',
	# 	views_ak.load_results_from_ak_rezult, name='load_results_from_ak_rezult'),
	# url(r'^result/load_results_from_ak_rezult/ak_start/(?P<ak_start>[A-Za-z0-9]+)/$',
	# 	views_ak.load_results_from_ak_rezult, name='load_results_from_ak_rezult'),

	url(r'^news/create/$', views_news.news_create, name='news_create'),
	url(r'^news/create/country/(?P<country_id>[A-Za-z]+)/$', views_news.news_create, name='news_create'),
	url(r'^news/create/region/(?P<region_id>[0-9]+)/$', views_news.news_create, name='news_create'),
	url(r'^news/create/city/(?P<city_id>[0-9]+)/$', views_news.news_create, name='news_create'),

	url(r'^news/(?P<news_id>[0-9]+)/update/$', views_news.news_update, name='news_update'),
	url(r'^news/(?P<news_id>[0-9]+)/delete/$', views_news.news_delete, name='news_delete'),
	url(r'^news/(?P<news_id>[0-9]+)/history/$', views_news.news_changes_history, name='news_changes_history'),
	url(r'^news/(?P<news_id>[0-9]+)/$', views_news.news_details, name='news_details'),
	url(r'^news/(?P<news_id>[0-9]+)/post$', views_news.news_post, name='news_post'),
	
	url(r'^users/$', views_user.users, name='users'),
	url(r'^user/(?P<user_id>[0-9]+)/history/$', views_user.user_changes_history, name='user_changes_history'),
	url(r'^user/(?P<user_id>[0-9]+)/update_stat/$', views_user.user_update_stat, name='user_update_stat'),

	url(r'^memo_editor/$', views_site.memo_editor, name='memo_editor'),
	url(r'^memo_admin/$', views_site.memo_admin, name='memo_admin'),
	url(r'^memo_spelling/$', views_site.memo_spelling, name='memo_spelling'),
	url(r'^memo_templates/$', views_site.memo_templates, name='memo_templates'),
	url(r'^memo_salary/$', views_site.memo_salary, name='memo_salary'),
	url(r'^db_structure/$', views_db_structure.db_structure, name='db_structure'),
	url(r'^db_structure/(?P<model_name>[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)/$', views_db_structure.db_structure, name='db_structure'),

	url(r'^search_by_id/$', views_site.search_by_id, name='search_by_id'),
	url(r'^search_by_id/id/(?P<id>[0-9]+)/$', views_site.search_by_id, name='search_by_id'),

	url(r'^action_history/$', views_user.action_history, name='action_history'),
	url(r'^action/(?P<table_update_id>[0-9]+)/$', views_user.action_details, name='action_details'),

	url(r'^event/(?P<event_id>[0-9]+)/protocol/$', views_protocol.protocol_details, name='protocol_details'),
	url(r'^event/(?P<event_id>[0-9]+)/protocol/(?P<protocol_id>[0-9]+)/$', views_protocol.protocol_details, name='protocol_details'),
	url(r'^event/(?P<event_id>[0-9]+)/protocol/(?P<protocol_id>[0-9]+)/sheet/(?P<sheet_id>[0-9]+)/$', views_protocol.protocol_details,
		name='protocol_details'),
	url(r'^event/(?P<event_id>[0-9]+)/protocol/sheet/(?P<sheet_id>[0-9]+)/$', views_protocol.protocol_details, name='protocol_details'),
	url(r'^race/(?P<race_id>[0-9]+)/protocol/(?P<protocol_id>[0-9]+)/$', views_protocol.protocol_details, name='protocol_details'),
	url(r'^protocol/(?P<protocol_id>[0-9]+)/mark_processed/$', views_protocol.protocol_mark_processed, name='protocol_mark_processed'),
	url(r'^loaded_protocols_by_month/$', views_series.loaded_protocols_by_month, name='loaded_protocols_by_month'),
	url(r'^all_events_with_social_links/$', views_series.all_events_with_social_links, name='all_events_with_social_links'),

	url(r'^events_for_result_import/$', views_protocol.events_for_result_import, name='events_for_result_import'),
	# url(r'^show_different_results/$', views_ak.show_different_results, name='show_different_results'),

	url(r'^social_pages/$', views_social.social_pages, name='social_pages'),
	url(r'^social_page/(?P<page_id>[0-9]+)/history/$', views_social.social_page_history, name='social_page_history'),

	url(r'^klb_status/$', views_klb.klb_status, name='klb_status'),
	url(r'^klb_status/year/(?P<year>[0-9]+)/$', views_klb.klb_status, name='klb_status'),
	url(r'^klb_status/connect_klb_results$', views_klb.connect_klb_results, name='connect_klb_results'),
	url(r'^klb_status/connect_unoff_results$', views_klb.connect_unoff_results, name='connect_unoff_results'),

	url(r'^klb/race/(?P<race_id>[0-9]+)/$', views_klb_race.klb_race_details, name='klb_race_details'),
	url(r'^klb/race/(?P<race_id>[0-9]+)/page/(?P<page>[0-9]+)/$', views_klb_race.klb_race_details, name='klb_race_details'),
	url(r'^klb/race/(?P<race_id>[0-9]+)/process/$', views_klb_race.klb_race_process, name='klb_race_process'),
	url(r'^klb/race/(?P<race_id>[0-9]+)/add_results/$', views_klb_race.klb_race_add_results, name='klb_race_add_results'),

	url(r'^klb/person/(?P<person_id>[0-9]+)/$', views_klb_person.klb_person_details, name='klb_person_details'),
	url(r'^klb/person/(?P<person_id>[0-9]+)/participant_update/year/(?P<year>[0-9]+)/$', views_klb_person.klb_person_participant_update,
		name='klb_person_participant_update'),
	url(r'^klb/person/(?P<person_id>[0-9]+)/refresh/$', views_klb_person.klb_person_refresh_stat, name='klb_person_refresh_stat'),
	url(r'^klb/person/create/runner/(?P<runner_id>[0-9]+)/$', views_klb_person.klb_person_create, name='klb_person_create'),
	url(r'^klb/person/(?P<person_id>[0-9]+)/update/$', views_klb_person.klb_person_update, name='klb_person_update'),
	url(r'^klb/person/(?P<person_id>[0-9]+)/delete/$', views_klb_person.klb_person_delete, name='klb_person_delete'),
	url(r'^klb/person/(?P<person_id>[0-9]+)/history/$', views_klb_person.klb_person_changes_history, name='klb_person_changes_history'),

	url(r'^klb/team/(?P<team_id>[0-9]+)/history/$', views_klb_team.klb_team_changes_history, name='klb_team_changes_history'),
	url(r'^klb/team/(?P<team_id>[0-9]+)/delete/$', views_klb_team.klb_team_delete, name='klb_team_delete'),
	url(r'^klb/team/(?P<team_id>[0-9]+)/change_name/$', views_klb_team.klb_team_change_name, name='klb_team_change_name'),
	url(r'^klb/team/(?P<team_id>[0-9]+)/details/$', views_klb_team.klb_team_contact_info, name='klb_team_contact_info'),
	url(r'^klb/team/(?P<team_id>[0-9]+)/details/order/(?P<ordering>[0-9]+)/$', views_klb_team.klb_team_contact_info, name='klb_team_contact_info'),
	url(r'^klb/team/(?P<team_id>[0-9]+)/add_old_participants/$',
		views_klb_team.klb_team_add_old_participants, name='klb_team_add_old_participants'),
	url(r'^klb/team/(?P<team_id>[0-9]+)/add_new_participant/$',
		views_klb_team.klb_team_add_new_participant, name='klb_team_add_new_participant'),
	url(r'^klb/team/(?P<team_id>[0-9]+)/delete_participants/$',
		views_klb_team.klb_team_delete_participants, name='klb_team_delete_participants'),
	url(r'^klb/team/(?P<team_id>[0-9]+)/move_participants/$',
		views_klb_team.klb_team_move_participants, name='klb_team_move_participants'),

	url(r'^klb/team/(?P<team_id>[0-9]+)/did_not_run/$', views_klb_team.did_not_run, name='klb_team_did_not_run'),
	url(r'^klb/team/(?P<team_id>[0-9]+)/did_not_run/with_marked/(?P<with_marked>[0-9]+)$', views_klb_team.did_not_run, name='klb_team_did_not_run'),

	url(r'^klb/participant/(?P<participant_id>[0-9]+)/contact_info$', views_klb_person.klb_participant_for_captain_details,
		name='klb_participant_for_captain_details'),

	url(r'^klb/update_match/(?P<year>[0-9]+)/$', views_klb.klb_update_match, name='klb_update_match'),

	url(r'^klb/make_report/(?P<year>[0-9]+)/type/(?P<role>[a-z]+)/$', views_klb_report.make_report, name='klb_make_report'),

	url(r'^klb/team_leaders_emails/$', views_klb.klb_team_leaders_emails, name='klb_team_leaders_emails'),
	url(r'^klb/team_leaders_emails/year/(?P<year>[0-9]+)/$', views_klb.klb_team_leaders_emails, name='klb_team_leaders_emails'),
	url(r'^klb/did_not_pay/$', views_klb.klb_who_did_not_pay, name='klb_who_did_not_pay'),
	url(r'^klb/did_not_pay/year/(?P<year>[0-9]+)/$', views_klb.klb_who_did_not_pay, name='klb_who_did_not_pay'),
	url(r'^klb/repeating_contact_data/$', views_klb.klb_repeating_contact_data, name='klb_repeating_contact_data'),
	url(r'^klb/repeating_contact_data/year/(?P<year>[0-9]+)/$', views_klb.klb_repeating_contact_data, name='klb_repeating_contact_data'),

	url(r'^letter/(?P<user_id>[0-9]+)/$', views_user.user_mail, name='user_mail'),
	url(r'^letter_txt/(?P<user_id>[0-9]+)/$', views_user.user_mail_txt, name='user_mail_txt'),
	url(r'^newsletter/(?P<user_id>[0-9]+)/(?P<filename>[A-Za-z0-9_]+)/$', views_mail.show_newsletter, name='show_newsletter'),
	url(r'^newsletter_txt/(?P<user_id>[0-9]+)/(?P<filename>[A-Za-z0-9_]+)/$', views_mail.show_newsletter_txt, name='show_newsletter_txt'),

	url(r'^message/(?P<message_id>[0-9]+)/$', views_mail.message_details, name='message_details'),

	url(r'^club/create/$', views_club.club_create, name='club_create'),
	url(r'^club/(?P<club_id>[0-9]+)/$', views_club.club_details, name='club_details'),
	url(r'^club/(?P<club_id>[0-9]+)/delete/$', views_club.club_delete, name='club_delete'),
	url(r'^club/(?P<club_id>[0-9]+)/history/$', views_club.club_changes_history, name='club_changes_history'),
	url(r'^club/(?P<club_id>[0-9]+)/add_cur_year_team/$', views_club.add_cur_year_team, name='add_cur_year_team'),
	url(r'^club/(?P<club_id>[0-9]+)/add_next_year_team/$', views_club.add_next_year_team, name='add_next_year_team'),
	url(r'^club/(?P<club_id>[0-9]+)/name/(?P<club_name_id>[0-9]+)/delete/$', views_club.club_name_delete, name='club_name_delete'),

	url(r'^club/(?P<club_id>[0-9]+)/add_new_member/$', views_club.add_club_member, name='club_add_new_member'),
	url(r'^club/(?P<club_id>[0-9]+)/add_runner/(?P<runner_id>[0-9]+)/$', views_club.add_runner, name='club_add_runner'),
	url(r'^club/(?P<club_id>[0-9]+)/member/(?P<member_id>[0-9]+)/edit/$', views_club.member_details, name='club_member_details'),
	url(r'^club/(?P<club_id>[0-9]+)/member/(?P<member_id>[0-9]+)/edit/return/(?P<return_page>[a-z]+)/$', views_club.member_details,
		name='club_member_details'),
	url(r'^club/(?P<club_id>[0-9]+)/member/(?P<member_id>[0-9]+)/delete/$', views_club.delete_member, name='club_delete_member'),

	url(r'^runner_names/$', views_name.runner_names, name='runner_names'),
	url(r'^runner_name/(?P<runner_name_id>[0-9]+)/delete/$', views_name.runner_name_delete, name='runner_name_delete'),
	url(r'^popular_names_in_free_results/$', views_name.popular_names_in_free_results, name='popular_names_in_free_results'),

	url(r'^event/(?P<event_id>[0-9]+)/create_reg/step1/$', views_registration.registration_create_step1, name='registration_create_step1'),
	url(r'^event/(?P<event_id>[0-9]+)/create_reg/step2/$', views_registration.registration_create_step2, name='registration_create_step2'),
	url(r'^event/registration/(?P<event_id>[0-9]+)/$', views_registration.registration_details, name='registration_details'),
	url(r'^event/registration/(?P<event_id>[0-9]+)/info$', views_registration.registration_info, name='registration_info'),
	url(r'^event/registration/(?P<event_id>[0-9]+)/delete$', views_registration.registration_delete, name='registration_delete'),
	url(r'^event/(?P<event_id>[0-9]+)/registration/history/$', views_registration.registration_changes_history, name='registration_changes_history'),
	url(r'^event/question/(?P<question_id>[0-9]+)/$', views_registration.question_details, name='question_details'),
	url(r'^race/(?P<race_id>[0-9]+)/registration/$', views_registration.reg_race_details, name='reg_race_details'),

	url(r'^runner/(?P<runner_id>[0-9]+)/add_name/$', views_runner.runner_name_add, name='runner_name_add'),
	url(r'^runner/(?P<runner_id>[0-9]+)/delete_name/(?P<name_id>[0-9]+)$', views_runner.runner_name_delete, name='runner_name_delete'),

	url(r'^admin_work_stat/$', views_user.admin_work_stat, name='admin_work_stat'),
	url(r'^admin_work_stat/year/(?P<year>[0-9]+)/$', views_user.admin_work_stat, name='admin_work_stat'),

	url(r'^all_payments/$', views_payment.all_payments, name='all_payments'),
	url(r'^all_medal_payments/$', views_payment.all_medal_payments, name='all_medal_payments'),
	url(r'^all_payments/user/(?P<user_id>[0-9]+)/$', views_payment.all_payments, name='all_payments'),
	url(r'^payment/create/$', views_payment.payment_create, name='payment_create'),
	url(r'^payment/(?P<payment_id>[0-9]+)/$', views_payment.payment_details, name='payment_details'),
	url(r'^payment/(?P<payment_id>[0-9]+)/delete/$', views_payment.payment_delete, name='payment_delete'),
	url(r'^payment/(?P<payment_id>[0-9]+)/add_participant/$', views_payment.payment_add_participant, name='payment_add_participant'),
	url(r'^payment/(?P<payment_id>[0-9]+)/delete_participant/(?P<participant_id>[0-9]+)/$', views_payment.payment_delete_participant,
		name='payment_delete_participant'),

	url(r'^organizer/(?P<organizer_id>[0-9]+)/$', views_organizer.organizer_details, name='organizer_details'),
	url(r'^organizer/(?P<organizer_id>[0-9]+)/history/$', views_organizer.organizer_changes_history, name='organizer_changes_history'),
	url(r'^organizer/(?P<organizer_id>[0-9]+)/add_series/$', views_organizer.add_series, name='organizer_add_series'),
	url(r'^organizer/(?P<organizer_id>[0-9]+)/remove_series/(?P<series_id>[0-9]+)/$', views_organizer.remove_series, name='organizer_remove_series'),
	url(r'^organizer/create/$', views_organizer.organizer_details, name='organizer_create'),

	url(r'^util/$', views_util.util, name='util'),
	url(r'^replace_in_event_names/$', views_util.replace_in_event_names, name='replace_in_event_names'),

	url(r'^age_group_records/$', views_age_group_record.age_group_records_edit, name='age_group_records_edit'),
	url(r'^age_group_records/(?P<country_id>RU|UA|BY)/(?P<gender_code>[a-z]+)/(?P<distance_code>[0-9a-z]+)/(?P<is_indoor>[0-9]+)/$',
		views_age_group_record.age_group_records_edit, name='age_group_records_edit'),
	url(r'^age_group_records/(?P<country_id>RU|UA|BY)/(?P<gender_code>[a-z]+)/absolute/$',
		views_age_group_record.age_group_records_edit, {'age': '0'}, name='country_records_edit'),

	url(r'^age_group_record/add/$', views_age_group_record.age_group_record_details, name='age_group_record_add'),
	url(r'^age_group_record/(?P<record_result_id>[0-9]+)/$', views_age_group_record.age_group_record_details, name='age_group_record_details'),
	url(r'^age_group_record/(?P<record_result_id>[0-9]+)/delete/$', views_age_group_record.age_group_record_delete, name='age_group_record_delete'),

	url(r'^better_age_group_results/$', views_age_group_record.better_age_group_results, name='better_age_group_results'),
	url(r'^better_age_group_results/(?P<country_id>RU|UA|BY)/$', views_age_group_record.better_age_group_results, name='better_age_group_results'),
	url(r'^better_age_group_results/(?P<country_id>RU|UA|BY)/show_bad_results$', views_age_group_record.better_age_group_results,
		{'hide_bad_results': False}, name='better_age_group_results_with_bad'),

	url(r'^mark_possible_age_group_record_as_bad/(?P<country_id>RU|UA|BY)/(?P<age_group_id>[0-9]+)/$',
		views_age_group_record.mark_possible_age_group_record_as_bad, name='mark_possible_age_group_record_as_bad'),
	url(r'^mark_possible_age_group_record_as_good/(?P<country_id>RU|UA|BY)/(?P<age_group_id>[0-9]+)/$',
		views_age_group_record.mark_possible_age_group_record_as_good, name='mark_possible_age_group_record_as_good'),

	url(r'^add_possible_age_group_records/$', views_age_group_record.add_possible_age_group_records, name='add_possible_age_group_records'),
	url(r'^update_age_group_records/(?P<country_id>RU|UA|BY)/(?P<gender_code>[a-z]+)/(?P<age>[0-9]+)'
			+ r'/(?P<distance_code>[0-9a-z]+)/(?P<is_indoor>[0-9]+)/$',
		views_age_group_record.update_age_group_records, name='update_age_group_records'),
	url(r'^generate_better_age_group_results/(?P<country_id>RU|UA|BY)/(?P<gender_code>[a-z]+)/(?P<age>[0-9]+)'
			+ r'/(?P<distance_code>[0-9a-z]+)/(?P<is_indoor>[0-9]+)/$',
		views_age_group_record.generate_better_age_group_results_for_tuple, name='generate_better_age_group_results_for_tuple'),
]