from django.core.management.base import BaseCommand
from core.models import TextChunk
from core.services.embeddings import embed_text

class Command(BaseCommand):
    help = "Generate embeddings for all text chunks"

    def handle(self, *args, **kwargs):
        chunks = TextChunk.objects.filter(embedding__isnull=True)
        self.stdout.write(f"Found {chunks.count()} chunks")

        for chunk in chunks:
            chunk.embedding = embed_text(chunk.content)
            chunk.save()

        self.stdout.write(self.style.SUCCESS("Embeddings generated"))
