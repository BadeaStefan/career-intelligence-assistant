"""Project-wide constants.

Values here are deliberately *not* settings. See EMBEDDING_DIM for why.
"""

EMBEDDING_DIM = 1536
"""Dimension of OpenAI ``text-embedding-3-small`` vectors.

Deliberately a code constant rather than a setting. Alembic migrations
import this to declare ``Vector(EMBEDDING_DIM)`` columns, and a migration
must produce the same schema on every run. If this were read from live
config, switching the embedding model to ``text-embedding-3-large`` would
make the *same* migration file emit a 3072-dim column, silently diverging
two databases built from identical history.

Changing this therefore requires a new migration -- which is correct, since
it is a genuine schema change that also invalidates every stored vector.

See spec section 4.
"""

MODEL_PRICE_PER_MILLION_TOKENS: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "text-embedding-3-small": {"prompt": 0.02, "completion": 0.0},
}
"""USD per 1M tokens, published OpenAI pricing at time of writing.

A per-model table rather than a single rate: embeddings have no completion
tokens, and the two models differ by 7x on the prompt side. Read by
``llm/openai_client.py`` to compute ``llm_calls.cost_usd`` -- never by
migrations, so a price change never touches the schema.
"""
