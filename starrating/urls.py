from django.conf.urls import url

from . import views

app_name = 'starrating'
urlpatterns = [
	url(r'^race/(?P<race_id>[0-9]+)/add_marks/$', views.add_marks, name='add_marks'),
	url(r'^race/(?P<race_id>[0-9]+)/add_marks/user/(?P<user_id>[0-9]+)/$', views.add_marks, name='add_marks_for_user'),

	url(
		r'^race/(?P<race_id>[0-9]+)/test_add_marks/user/(?P<user_id>[0-9]+)/$',
		views.add_marks,
		dict(test_mode=True),
		name='test_add_marks_for_user',
	),

	url(
		r'^race/(?P<race_id>[0-9]+)/add_marks2/user/(?P<user_id>[0-9]+)/$',
		views.add_marks,
		dict(to_move_to_next_race=True),
		name='add_marks2_for_user',
	),

	url(
		r'^race/(?P<race_id>[0-9]+)/abstain/user/(?P<user_id>[0-9]+)/$',
		views.abstain, name='abstain',
	),
	url(
		r'^user/(?P<user_id>[0-9]+)/postpone_rating/$',
		views.postpone_adding_marks, name='postpone_adding_marks',
	),
	url(
		r'^user/(?P<user_id>[0-9]+)/bulk_stop/$',
		views.stop_adding_marks, name='stop_adding_marks',
	),

	url(r'^race/(?P<race_id>[0-9]+)/my_marks/$', views.my_marks, name='my_marks'),

	url(r'^race/(?P<race_id>[0-9]+)/rating/user/(?P<user_id>[0-9]+)/$', views.my_marks, name='my_marks_for_user'),
	url(r'^editor/all_marks/$', views.editor_rating_details, name='editor_rating_details'),
	url(r'^editor/(?P<level>(race|event|series|organizer))/(?P<id_>[0-9]+)/rating/$', views.editor_rating_details, name='editor_rating_details'),
	url(r'^starrating/save_marks/$', views.save_marks, name='save_marks'),
	url(r'^starrating/parameters/$', views.parameters, name='parameters'),
	url(r'^starrating/methods/$', views.methods, name='methods'),
	url(r'^(?P<level>(race|event|series|organizer|root))/(?P<id_>[0-9]+)/rating/$', views.rating_details, name='rating_details'),

	url(r'^group/(?P<group_id>[0-9]+)/delete/$', views.group_delete, name='group_delete'),
]
