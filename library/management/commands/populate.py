from django.core.management.base import BaseCommand
from faker import Faker
from library.models import Author, Book

fake = Faker()

GENRES = ["Fiction", "Sci-Fi", "Mystery", "History", "Biography", "Fantasy", "Thriller", "Romance"]


class Command(BaseCommand):
    help = "Seed the database with fake authors and books"

    def handle(self, *args, **kwargs):
        if Author.objects.using('default').exists():
            self.stdout.write("[populate] Data already exists, skipping seed.")
            return

        self.stdout.write("[populate] Seeding database via MASTER node...")

        for _ in range(10):
            author = Author.objects.create(
                name=fake.name(),
                bio=fake.paragraph(nb_sentences=3),
            )
            self.stdout.write(f"  ✓ Author: {author.name}  [db={author._state.db}]")

            for _ in range(5):
                Book.objects.create(
                    title=fake.sentence(nb_words=4).rstrip("."),
                    author=author,
                    isbn=fake.unique.isbn13(),
                    published_year=int(fake.year()),
                    genre=fake.random_element(GENRES),
                    rating=round(fake.random.uniform(1.0, 5.0), 1),
                )

        total_books = Book.objects.using('default').count()
        total_authors = Author.objects.using('default').count()
        self.stdout.write(f"\n[populate] Done → {total_authors} authors, {total_books} books seeded on MASTER.")
