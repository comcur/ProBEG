# -*- coding: utf-8 -*-
from django.views.generic.base import RedirectView
from django.conf.urls import url

from .views import views_age_group_record, views_club, views_klb, views_klb_team, views_mail, views_news, views_organizer, views_parkrun, views_payment
from .views import views_race, views_registration, views_report, views_result, views_runner, views_site, views_useful_link, views_user

app_name = 'results'

urlpatterns = [
	url(r'^$', views_site.main_page, name='main_page'),
	url(r'^home/$', views_user.home, name='home'),
	url(r'^series/(?P<series_id>[0-9]+)/$', views_race.series_details, name='series_details'),
	# url(r'^series/(?P<series_id>[0-9]+)/(?P<tab>[A-Za-z_]+)/$', views_race.series_details, name='series_details'),
	url(r'^series/(?P<series_id>[0-9]+)/(?P<tab>all_events|races_by_event|races_by_distance|reviews|default)/$', views_race.series_details,
		name='series_details'),

	url(r'^event/(?P<event_id>[0-9]+)/$', views_race.event_details, name='event_details'),
	url(r'^event/(?P<event_id>[0-9]+)/beta/(?P<beta>[0-9]+)/$', views_race.event_details, name='event_details'),
	url(r'^event/(?P<event_id>[0-9]+)/klb$', views_race.event_klb_results, name='event_klb_results'),
	# url(r'^event/ak/(?P<ak_race_id>[A-Za-z0-9]+)/$', views_race.event_details, name='event_details'),
	url(r'^race/(?P<race_id>[0-9]+)$', views_race.race_details, name='race_details'),
	url(r'^race/(?P<race_id>[0-9]+)/tab_editor/(?P<tab_editor>[0-9]+)/$', views_race.race_details, name='race_details'),
	url(r'^race/(?P<race_id>[0-9]+)/tab_unofficial/(?P<tab_unofficial>[0-9]+)/$', views_race.race_details, name='race_details'),
	url(r'^race/(?P<race_id>[0-9]+)/add_to_club/(?P<tab_add_to_club>[0-9]+)/$', views_race.race_details, name='race_details'),

	url(r'^logo/event/(?P<event_id>[0-9]+)/$', views_race.get_logo_page, name='get_logo_page'),
	url(r'^logo/series/(?P<series_id>[0-9]+)/$', views_race.get_logo_page, name='get_logo_page'),
	url(r'^logo/organizer/(?P<organizer_id>[0-9]+)/$', views_race.get_logo_page, name='get_logo_page'),

	url(r'^add_event_to_calendar/(?P<event_id>[0-9]+)/$', views_race.add_event_to_calendar, name='add_event_to_calendar'),
	url(r'^remove_event_from_calendar/(?P<event_id>[0-9]+)/$', views_race.remove_event_from_calendar, name='remove_event_from_calendar'),

	url(r'^results/disconnected/$', views_result.results_disconnected, name='results_disconnected'),
	url(r'^results/disconnected/fname/(?P<fname>[^/]*)/$', views_result.results_disconnected, name='results_disconnected'),
	url(r'^results/disconnected/(?P<lname>[^/]*)/$', views_result.results_disconnected, name='results_disconnected'),
	url(r'^results/disconnected/(?P<lname>[^/]*)/(?P<fname>[^/]*)/$', views_result.results_disconnected, name='results_disconnected'),
	url(r'^results/$', views_result.results, name='results'),
	url(r'^results/fname/(?P<fname>[^/]+)/$', views_result.results, name='results'),
	url(r'^results/(?P<lname>[^/]*)/$', views_result.results, name='results'),
	url(r'^results/(?P<lname>[^/]*)/(?P<fname>[^/]*)/$', views_result.results, name='results'),
	url(r'^races/$', views_race.races, name='races'),
	url(r'^races/view/(?P<view>[0-9]+)/$', views_race.races, name='races'),
	# url(r'^races/default/$', views_race.races_default, name='races_default'),
	# url(r'^races/default2/$', views_race.races_default2, name='races_default2'),
	url(r'^races/country/(?P<country_id>[A-Za-z]+)/$', views_race.races, name='races'),
	url(r'^races/region/(?P<region_id>[0-9]+)/$', views_race.races, name='races'),
	url(r'^races/region_group/(?P<region_group>[^/]+)/$', views_race.races, name='races'),
	url(r'^races/city/(?P<city_id>[0-9]+)/$', views_race.races, name='races'),
	url(r'^races/distance/(?P<distance_id>[0-9]+)/$', views_race.races, name='races'),
	url(r'^races/name/(?P<race_name>[^/]+)/$', views_race.races, name='races'),

	url(r'^races/date_region/(?P<date_region>[0-9]+)/$', views_race.races, name='races'),
	url(r'^races/country/(?P<country_id>[A-Za-z]+)/date_region/(?P<date_region>[0-9]+)/$', views_race.races, name='races'),
	url(r'^races/region/(?P<region_id>[0-9]+)/date_region/(?P<date_region>[0-9]+)/$', views_race.races, name='races'),
	url(r'^races/city/(?P<city_id>[0-9]+)/date_region/(?P<date_region>[0-9]+)/$', views_race.races, name='races'),
	
	url(r'^details/$', views_user.my_details, name='my_details'),
	url(r'^details/user/(?P<user_id>[0-9]+)/$', views_user.my_details, name='my_details'),
	url(r'^details/resend/$', views_user.send_confirmation_letter, name='send_confirmation_letter'),
	url(r'^verify_email/(?P<code>[A-Za-z0-9]+)/$', views_user.verify_email, name='verify_email'),

	url(r'^user/(?P<user_id>[0-9]+)/$', views_user.user_details, name='user_details'),
	url(r'^user/(?P<user_id>[0-9]+)/full/$', views_user.user_details_full, name='user_details_full'),
	url(r'^user/(?P<user_id>[0-9]+)/delete_series/(?P<series_id>[0-9]+)/$', views_user.user_details, name='user_delete_series'),
	url(r'^user/(?P<user_id>[0-9]+)/delete_club/(?P<club_id>[0-9]+)/$', views_user.user_details, name='user_delete_club'),
	url(r'^get_avatar/user/(?P<user_id>[0-9]+)/$', views_user.get_avatar_page, name='get_avatar_page'),

	url(r'^details/add_name/$', views_user.my_name_add, name='name_add'),
	url(r'^details/delete_name/(?P<name_id>[0-9]+)$', views_user.my_name_delete, name='name_delete'),

	url(r'^strava_links/$', views_user.my_strava_links, name='my_strava_links'),
	url(r'^strava_links/user/(?P<user_id>[0-9]+)/$', views_user.my_strava_links, name='my_strava_links'),

	url(r'^news/$', views_news.all_news, name='all_news'),
	url(r'^news/one_side/(?P<one_side>[0-9]+)/$', views_news.all_news, name='all_news'),
	url(r'^news/country/(?P<country_id>[A-Za-z]+)/$', views_news.all_news, name='all_news'),
	url(r'^news/region/(?P<region_id>[0-9]+)/$', views_news.all_news, name='all_news'),
	url(r'^news/city/(?P<city_id>[0-9]+)/$', views_news.all_news, name='all_news'),
	url(r'^news/(?P<news_id>[0-9]+)/$', views_news.news_details, name='news_details'),

	url(r'^find_results/$', views_user.find_results, name='find_results'),
	url(r'^find_results/user/(?P<user_id>[0-9]+)/$', views_user.find_results, name='find_results'),
	url(r'^find_results/runner/(?P<runner_id>[0-9]+)/$', views_user.find_results, name='find_results'),
	url(r'^claim_result/(?P<result_id>[0-9]+)/$', views_result.claim_result, name='claim_result'),
	url(r'^unclaim_result/(?P<result_id>[0-9]+)/$', views_result.unclaim_result, name='unclaim_result'),
	url(r'^unclaim_results/$', views_result.unclaim_results, name='unclaim_results'),
	url(r'^race/(?P<race_id>[0-9]+)/unclaim_result/(?P<result_id>[0-9]+)/$', views_result.unclaim_result, name='unclaim_result'),

	url(r'^send_message/$', views_mail.send_message, name='send_message'),
	url(r'^send_message_admin/$', views_mail.send_message_admin, name='send_message_admin'),
	url(r'^get_send_to_info_page/$', views_mail.get_send_to_info_page, name='get_send_to_info_page'),
	url(r'^get_send_from_info_page/$', views_mail.get_send_from_info_page, name='get_send_from_info_page'),
	url(r'^get_send_from_info_page/ticket/(?P<table_update_id>[0-9]+)/$', views_mail.get_send_from_info_page, name='get_send_from_info_page'),
	url(r'^get_send_from_info_page/ticket/(?P<table_update_id>[0-9]+)/wrong_club/(?P<wrong_club>[0-9]+)/$', views_mail.get_send_from_info_page, name='get_send_from_info_page'),
	url(r'^get_send_from_info_page/event/(?P<event_id>[0-9]+)/$', views_mail.get_send_from_info_page, name='get_send_from_info_page'),
	url(r'^get_send_from_info_page/event_participants/(?P<event_participants_id>[0-9]+)/$', views_mail.get_send_from_info_page,
		name='get_send_from_info_page'),
	url(r'^get_send_from_info_page/event_wo_protocols/(?P<event_wo_protocols_id>[0-9]+)/$', views_mail.get_send_from_info_page,
		name='get_send_from_info_page'),
	url(r'^get_send_from_info_page/user/(?P<user_id>[0-9]+)/$', views_mail.get_send_from_info_page, name='get_send_from_info_page'),

	url(r'^get_add_result_page/event/(?P<event_id>[0-9]+)/$', views_result.get_add_result_page, name='get_add_result_page'),
	url(r'^add_unofficial_result/event/(?P<event_id>[0-9]+)/$', views_result.add_unofficial_result, name='add_unofficial_result'),
	url(r'^delete_unofficial_result/(?P<result_id>[0-9]+)/$', views_result.delete_unofficial_result, name='delete_unofficial_result'),

	url(r'^get_add_event_page/series/(?P<series_id>[0-9]+)/$', views_mail.get_add_event_page, name='get_add_event_page'),
	url(r'^get_add_series_page/$', views_mail.get_add_series_page, name='get_add_series_page'),
	url(r'^add_unofficial_event/series/(?P<series_id>[0-9]+)/$', views_mail.add_unofficial_event, name='add_unofficial_event'),
	url(r'^add_unofficial_series/$', views_mail.add_unofficial_series, name='add_unofficial_series'),

	url(r'^get_add_review_page/event/(?P<event_id>[0-9]+)/$', views_mail.get_add_review_page, name='get_add_review_page'),
	url(r'^get_add_review_page/event/(?P<event_id>[0-9]+)/photo/(?P<photo>[0-9]+)/$', views_mail.get_add_review_page, name='get_add_review_page'),
	url(r'^add_review/$', views_mail.add_review, name='add_review'),

	url(r'^runner/(?P<runner_id>[0-9]+)/$', views_runner.runner_details, name='runner_details'),
	url(r'^runner/(?P<runner_id>[0-9]+)/full/$', views_runner.runner_details_full, name='runner_details_full'),
	url(r'^runners/fname/(?P<fname>[^/]+)/$', views_runner.runners, name='runners'),
	url(r'^runners/name/$', views_runner.runners, name='runners'),
	url(r'^runners/$', views_runner.runners, name='runners'),
	url(r'^runners/name/(?P<lname>[^/]+)/$', views_runner.runners, name='runners'),
	url(r'^runners/name/(?P<lname>[^/]*)/(?P<fname>[^/]+)/$', views_runner.runners, name='runners'),

	url(r'^result/(?P<result_id>[0-9]+)$', views_result.result_details, name='result_details'),

	url(r'^klb/$', views_klb.klb_match_summary, name='klb_match_summary'),
	url(r'^klb/(?P<year>[0-9]+)/$', views_klb.klb_match_summary, name='klb_match_summary'),
	url(r'^klb/tab/(?P<tab>[^/]+)/$', views_klb.klb_match_summary, name='klb_match_summary'),
	url(r'^klb/(?P<year>[0-9]+)/tab/(?P<tab>[^/]+)/$', views_klb.klb_match_summary, name='klb_match_summary'),
	url(r'^klb/invitation/$', views_klb.about_match, name='about_match'),
	url(r'^klb/(?P<year>[0-9]+)/invitation/$', views_klb.about_match, name='about_match'),

	url(r'^klb/application/$', views_klb.application, name='klb_application'),
	url(r'^klb/application/(?P<year>[0-9]+)/$', views_klb.application, name='klb_application'),
	url(r'^klb/application/payment/(?P<year>[0-9]+)/$', views_klb.application_payment, name='klb_application_payment'),
	url(r'^klb/application/make_payment/(?P<year>[0-9]+)/$', views_payment.klb_make_individual_payment, name='klb_make_individual_payment'),
	url(r'^klb/application/pay_nothing/(?P<year>[0-9]+)/$', views_klb.individual_pay_nothing, name='klb_individual_pay_nothing'),

	url(r'^klb/calculator/$', views_klb.calculator, name='calculator'),
	url(r'^klb/person/(?P<person_id>[0-9]+)/$', views_klb.klb_person_details, name='klb_person_details'),
	url(r'^klb/(?P<year>[0-9]+)/remove/$', views_klb.remove_from_match, name='klb_remove_from_match'),

	url(r'^klb/team/(?P<team_id>[0-9]+)/$', views_klb_team.klb_team_details, name='klb_team_details'),
	url(r'^klb/team/(?P<team_id>[0-9]+)/order/(?P<ordering>[0-9]+)/$', views_klb_team.klb_team_details, name='klb_team_details'),
	url(r'^klb/team/(?P<team_id>[0-9]+)/full/$', views_klb_team.klb_team_details_full, name='klb_team_details_full'),
	url(r'^klb/team/(?P<team_id>[0-9]+)/score_changes/$', views_klb_team.klb_team_score_changes, name='klb_team_score_changes'),
	url(r'^klb/team/(?P<team_id>[0-9]+)/results_for_moderation/$', views_klb_team.klb_team_results_for_moderation, name='klb_team_results_for_moderation'),
	url(r'^klb/team/(?P<team_id>[0-9]+)/refresh_stat$', views_klb_team.klb_team_refresh_stat, name='klb_team_refresh_stat'),

	url(r'^klb/team/(?P<team_id>[0-9]+)/payment/$', views_klb_team.team_or_club_payment, name='klb_team_payment'),
	url(r'^klb/club/(?P<club_id>[0-9]+)/payment/$', views_klb_team.team_or_club_payment, name='klb_club_payment'),
	url(r'^klb/team/(?P<team_id>[0-9]+)/make_payment/$', views_payment.klb_make_team_or_club_payment, name='klb_make_team_payment'),
	url(r'^klb/club/(?P<club_id>[0-9]+)/make_payment/$', views_payment.klb_make_team_or_club_payment, name='klb_make_club_payment'),

	url(r'^klb/medal/payment/$', views_payment.medal_payment, name='medal_payment'),
	url(r'^klb/medal/payment/2018/$', views_payment.medal_payment, {'year': 2018}, name='medal_payment'),
	url(r'^klb/medal/make_payment/$', views_payment.make_medal_payment, name='make_medal_payment'),

	url(r'^klb/age_group/$', views_klb.klb_age_group_details, name='klb_age_group_details'),
	url(r'^klb/age_group/(?P<age_group_id>[0-9]+)/$', views_klb.klb_age_group_details, name='klb_age_group_details'),
	url(r'^klb/age_group/(?P<age_group_id>[0-9]+)/all/(?P<show_all>[0-9]+)/$', views_klb.klb_age_group_details, name='klb_age_group_details'),

	url(r'^klb/participants/year/(?P<year>[0-9]+)/region/(?P<region_id>[0-9]+)/$', views_klb.klb_age_group_details, name='klb_age_group_details'),
	url(r'^klb/participants/year/(?P<year>[0-9]+)/country/(?P<country_id>[A-Za-z]+)/$', views_klb.klb_age_group_details, name='klb_age_group_details'),

	url(r'^klb/category/$', views_klb.klb_match_category_details, name='klb_match_category_details'),
	url(r'^klb/category/(?P<match_category_id>[0-9]+)/$', views_klb.klb_match_category_details, name='klb_match_category_details'),

	url(r'^klb/events_not_in_match/$', views_klb.events_not_in_match, name='events_not_in_match'),
	url(r'^klb/events_not_in_match/(?P<year>[0-9]+)/$', views_klb.events_not_in_match, name='events_not_in_match'),

	url(r'^klb/reports/$', views_klb.reports, name='klb_reports'),
	url(r'^klb/reports/(?P<year>[0-9]+)/$', views_klb.reports, name='klb_reports'),

	url(r'^klb/winners_by_regions/(?P<year>[0-9]+)/$', views_klb.winners_by_regions, name='klb_winners_by_regions'),

	url(r'^clubs/$', views_club.clubs, name='clubs'),
	url(r'^clubs/about/$', views_club.about_club_membership, name='about_club_membership'),
	url(r'^clubs/(?P<view>[0-9]+)/$', views_club.clubs, name='clubs'),
	url(r'^club/(?P<club_id>[0-9]+)/$', views_club.club_details, name='club_details'),
	url(r'^club/(?P<club_id>[0-9]+)/planned_starts/$', views_club.planned_starts, name='planned_starts'),
	url(r'^club/(?P<club_id>[0-9]+)/records/$', views_club.club_records, name='club_records'),
	url(r'^club/(?P<club_id>[0-9]+)/records/(?P<year>[0-9]+)/$', views_club.club_records, name='club_records'),
	url(r'^club/(?P<club_id>[0-9]+)/members/$', views_club.club_members, name='club_members'),
	url(r'^club/(?P<club_id>[0-9]+)/members/all/$', views_club.club_members_all, name='club_members_all'),
	url(r'^club/(?P<club_id>[0-9]+)/members/order/(?P<ordering>[^/]+)/$', views_club.club_members, name='club_members'),
	url(r'^club/(?P<club_id>[0-9]+)/members/all/order/(?P<ordering>[^/]+)/$', views_club.club_members_all, name='club_members_all'),

	url(r'^protocols_wanted/$', views_race.protocols_wanted, name='protocols_wanted'),
	url(r'^protocols_wanted/type/(?P<events_type>[0-9]+)/$', views_race.protocols_wanted, name='protocols_wanted'),

	url(r'^russia_report/(?P<year>[0-9]+)/$', views_report.country_report,
		{'country_id': 'RU'}, name='russia_report'),
	url(r'^russia_report/(?P<year>[0-9]+)/(?P<tab>[0-9]+)/$', views_report.country_report,
		{'country_id': 'RU'}, name='russia_report'),
	url(r'^russia_report/(?P<year>[0-9]+)/(?P<tab>[0-9]+)/full/$', views_report.country_report,
		{'country_id': 'RU', 'show_all': 1}, name='russia_report_full'),

	url(r'^belarus_report/(?P<year>[0-9]+)/$', views_report.country_report,
		{'country_id': 'BY'}, name='belarus_report'),
	url(r'^belarus_report/(?P<year>[0-9]+)/(?P<tab>[0-9]+)/$', views_report.country_report,
		{'country_id': 'BY'}, name='belarus_report'),
	url(r'^belarus_report/(?P<year>[0-9]+)/(?P<tab>[0-9]+)/full/$', views_report.country_report,
		{'country_id': 'BY', 'show_all': 1}, name='belarus_report_full'),

	url(r'^russia_report_generator/$', views_report.russia_report_generator, name='russia_report_generator'),
	url(r'^russia_report_generator/(?P<tab>[0-9]+)/$', views_report.russia_report_generator, name='russia_report_generator'),
	url(r'^russia_report_generator/(?P<tab>[0-9]+)/full/$', views_report.russia_report_generator, {'show_all': 1}, name='russia_report_generator'),

	url(r'^rating/$', views_race.rating, name='rating'),
	url(r'^rating/(?P<country_id>[A-Za-z]+)/(?P<distance_id>[0-9a-z]+)/(?P<year>[0-9]+)/(?P<rating_type>[0-9a-z_]+)/$',
		views_race.rating, name='rating'),

	url(r'^event/(?P<event_id>[0-9]+)/registration/$', views_race.old_registration, name='old_registration'),
	url(r'^event/(?P<event_id>[0-9]+)/reg/$', views_registration.reg_step1, name='reg_step1'),
	url(r'^race/(?P<race_id>[0-9]+)/registrant/(?P<registrant_id>[\-0-9]+)/$', views_registration.reg_step2, name='reg_step2'),

	url(r'^add_new_event/$', views_site.add_new_event, name='add_new_event'),
	url(r'^how_to_add_event/$', RedirectView.as_view(pattern_name='results:add_new_event', permanent=True), name='how_to_add_event'),

	url(r'^cart/$', views_registration.reg_cart, name='reg_cart'),
	url(r'^cart/registrant/(?P<registrant_id>[0-9]+)/$', views_registration.reg_cart, name='reg_cart'),

	url(r'^payment_form_old$', views_payment.payment_form, name='payment_form'),
	url(r'^my_payments$', views_payment.my_payments, name='my_payments'),
	url(r'^make_payment/(?P<payment_id>[0-9]+)/$', views_payment.make_payment, name='make_payment'),
	url(r'^payment/(?P<payment_id>[0-9]+)/delete/$', views_payment.payment_delete, name='payment_delete'),

	url(r'^moneta/pay_url$', views_payment.pay_url, name='pay_url'),
	url(r'^moneta/success$', views_payment.success, name='success'),
	url(r'^moneta/fail$', views_payment.fail, name='fail'),
	url(r'^moneta/in_progress$', views_payment.in_progress, name='in_progress'),
	url(r'^moneta/return$', views_payment.return_url, name='return_url'),

	url(r'^organizers/$', views_organizer.organizers, name='organizers'),
	url(r'^organizer/(?P<organizer_id>[0-9]+)/$', views_organizer.organizer_details, name='organizer_details'),

	url(r'^parkrun/stat$', views_parkrun.parkrun_stat, name='parkrun_stat'),

	url(r'^links$', views_useful_link.useful_links, name='useful_links'),

	url(r'^age_group_records$', views_age_group_record.age_group_records, name='age_group_records'),
	url(r'^age_group_records/(?P<country_id>RU|UA|BY)$', views_age_group_record.age_group_records, name='age_group_records'),
	url(r'^age_group_records/(?P<country_id>RU|UA|BY)/gender/(?P<gender_code>[a-z]+)/age/(?P<age>[0-9]+)'
			+ r'/distance/(?P<distance_code>[0-9a-z]+)/indoor/(?P<is_indoor>[0-9]+)/$',
		views_age_group_record.age_group_details, name='age_group_record_details'),

	url(r'^age_group_records/(?P<country_id>RU|UA|BY)/(?P<distance_code>[0-9a-z]+)$',
		views_age_group_record.records_for_distance, name='age_group_records_for_distance'),
	url(r'^age_group_records/(?P<country_id>RU|UA|BY)/(?P<distance_code>[0-9a-z]+)/indoor/(?P<is_indoor>[0-9]+)/$',
		views_age_group_record.records_for_distance, name='age_group_records_for_distance'),

	url(r'^age_group_records/marathon/(?P<gender_code>[a-z]+)/$',
		views_age_group_record.records_for_marathon, name='age_group_records_for_marathon'),

	url(r'^records_better_than_shatilo$', views_age_group_record.records_better_than_shatilo, name='records_better_than_shatilo'),

	url(r'^archive$', views_site.archive, name='archive'),
]