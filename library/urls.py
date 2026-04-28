from django.urls import path
from .views import BookListCreateView, BookDetailView, AuthorListCreateView, DBStatusView

urlpatterns = [
    path("books/", BookListCreateView.as_view(), name="book-list-create"),
    path("books/<int:pk>/", BookDetailView.as_view(), name="book-detail"),
    path("authors/", AuthorListCreateView.as_view(), name="author-list-create"),
    path("db-status/", DBStatusView.as_view(), name="db-status"),
]
