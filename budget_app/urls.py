from django.urls import path
from . import views

app_name = 'budget_app'

urlpatterns = [
    # トップページ（月次計画一覧）
    path('', views.plan_list, name='index'),

    # シミュレーション設定
    path('config/', views.config_view, name='config'),
    path('update-initial-balance/', views.update_initial_balance, name='update_initial_balance'),

    # 月次計画
    path('plans/', views.plan_list, name='plan_list'),
    path('plans/create/', views.plan_create, name='plan_create'),
    path('plans/<int:pk>/edit/', views.plan_edit, name='plan_edit'),
    path('plans/<int:pk>/delete/', views.plan_delete, name='plan_delete'),

    # 給与一覧
    path('salaries/', views.salary_list, name='salary_list'),

    # 過去の明細
    path('past-transactions/', views.past_transactions_list, name='past_transactions'),

    # クレカ見積り
    path('credit-estimates/', views.credit_estimate_list, name='credit_estimates'),
    path('credit-estimates/<int:pk>/edit/', views.credit_estimate_edit, name='credit_estimate_edit'),
    path('credit-estimates/delete/<int:pk>/', views.credit_estimate_delete, name='credit_estimate_delete'),
    # 定期デフォルト
    path('credit-defaults/', views.credit_default_list, name='credit_defaults'),
    path('credit-defaults/<int:pk>/delete/', views.credit_default_delete, name='credit_default_delete'),

    # シミュレーション実行
    path('simulate/', views.simulate, name='simulate'),

    # 結果表示
    path('results/', views.results_list, name='results_list'),
]
