from django.urls import path

import coldfront.core.field_of_science.views as fos_views

urlpatterns = [
    path('', fos_views.DepartmentAllocationListView.as_view()),
    path('<int:pk>/invoice/', fos_views.DepartmentAllocationInvoiceDetailView.as_view(), name="department_invoice")
]
