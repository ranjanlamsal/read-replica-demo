import logging
from django.db import connections
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Book, Author
from .serializers import BookSerializer, BookCreateSerializer, AuthorSerializer

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helper — log which physical DB connection was used
# ─────────────────────────────────────────────────────────────────────────────
def _log_db_used(alias: str, operation: str):
    host = connections[alias].settings_dict.get("HOST", "?")
    logger.info(f"[DB ROUTER] {operation} → alias='{alias}'  host={host}")


# ─────────────────────────────────────────────────────────────────────────────
# GET  /api/books/     — list all books
# POST /api/books/     — create a book
# ─────────────────────────────────────────────────────────────────────────────
class BookListCreateView(APIView):

    def get(self, request):
        """
        READ operation → router sends this to the REPLICA.

        Django automatically calls PrimaryReplicaRouter.db_for_read()
        before executing Book.objects.all() — no manual DB selection needed.
        """
        books = Book.objects.select_related("author").all()

        # Log which DB alias was resolved for this queryset
        db_alias = books.db          # Django exposes the resolved alias here
        _log_db_used(db_alias, "SELECT books")

        serializer = BookSerializer(books, many=True)
        return Response({
            "db_used": db_alias,     # shows 'replica' in response
            "count": books.using(db_alias).count(),
            "books": serializer.data,
        })

    def post(self, request):
        """
        WRITE operation → router sends this to the MASTER (default).

        book.save() triggers db_for_write() → 'default' (master).
        """
        serializer = BookCreateSerializer(data=request.data)
        if serializer.is_valid():
            book = serializer.save()    # INSERT hits master

            _log_db_used(book._state.db, "INSERT book")

            return Response({
                "db_used": book._state.db,   # shows 'default' in response
                "book": BookSerializer(book).data,
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────────────────────
# GET  /api/books/<id>/   — get single book
# ─────────────────────────────────────────────────────────────────────────────
class BookDetailView(APIView):

    def get(self, request, pk):
        """Single book fetch — also goes to replica."""
        try:
            book = Book.objects.select_related("author").get(pk=pk)
        except Book.DoesNotExist:
            return Response({"error": "Book not found"}, status=status.HTTP_404_NOT_FOUND)

        _log_db_used(book._state.db, f"SELECT book id={pk}")

        return Response({
            "db_used": book._state.db,
            "book": BookSerializer(book).data,
        })


# ─────────────────────────────────────────────────────────────────────────────
# GET  /api/authors/   — list authors
# POST /api/authors/   — create author
# ─────────────────────────────────────────────────────────────────────────────
class AuthorListCreateView(APIView):

    def get(self, request):
        authors = Author.objects.all()
        _log_db_used(authors.db, "SELECT authors")
        return Response({
            "db_used": authors.db,
            "authors": AuthorSerializer(authors, many=True).data,
        })

    def post(self, request):
        serializer = AuthorSerializer(data=request.data)
        if serializer.is_valid():
            author = serializer.save()
            _log_db_used(author._state.db, "INSERT author")
            return Response({
                "db_used": author._state.db,
                "author": AuthorSerializer(author).data,
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/db-status/  — sanity check: shows which host each alias points to
# ─────────────────────────────────────────────────────────────────────────────
class DBStatusView(APIView):
    def get(self, request):
        info = {}
        for alias in ["default", "replica"]:
            cfg = connections[alias].settings_dict
            info[alias] = {
                "host": cfg.get("HOST"),
                "port": cfg.get("PORT"),
                "role": "MASTER (writes)" if alias == "default" else "REPLICA (reads)",
            }
        return Response(info)
