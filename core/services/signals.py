from django.db.models.signals import post_delete
from django.dispatch import receiver
from core.models import Subject
from core.services.vector_store import ChromaVectorStore


@receiver(post_delete, sender=Subject)
def delete_subject_embeddings(sender, instance, **kwargs):
    store = ChromaVectorStore()
    store.delete_by_subject(instance.id)
