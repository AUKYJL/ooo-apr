from elasticsearch import AsyncElasticsearch

from app.core.config import Settings


def create_elasticsearch_client(settings: Settings) -> AsyncElasticsearch:
    """Create the application's asynchronous Elasticsearch client."""
    return AsyncElasticsearch(settings.elasticsearch_url)
