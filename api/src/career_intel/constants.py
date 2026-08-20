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
