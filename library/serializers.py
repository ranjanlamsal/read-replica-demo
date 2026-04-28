from rest_framework import serializers
from .models import Author, Book


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ["id", "name", "bio", "created_at"]
        read_only_fields = ["id", "created_at"]


class BookSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.name", read_only=True)

    class Meta:
        model = Book
        fields = [
            "id", "title", "author", "author_name",
            "isbn", "published_year", "genre", "rating", "created_at",
        ]
        read_only_fields = ["id", "created_at", "author_name"]


class BookCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = ["title", "author", "isbn", "published_year", "genre", "rating"]
