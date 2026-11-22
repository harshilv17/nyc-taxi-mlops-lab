"""S6: the wiki RAG branch, in the `rag` database on RDS (pgvector), on a daily schedule.

- wiki_pages: the published pages from the ops wiki (resource `wiki`: labpipes/wiki.py). Store each
  page's ETag and send it next time: an unchanged page then costs a 304 and no body.
- wiki_chunks: split changed pages with labpipes.chunking.chunk_markdown (chunk size and overlap are
  decision 015) and store the chunks; use Chunk.content_hash as the id so unchanged text keeps it.
- wiki_embeddings: embed only the chunks that have no vector yet (resource `embed`: nomic-embed-text,
  768 dimensions) and store them as pgvector `vector(768)`, with an index (HNSW or IVFFlat: decision 016).
- A blocking check that every chunk has a vector, and a schedule (and a job you can run by hand with
  scripts/dagster-run.sh) for the three.
The RDS admin connection comes from the `rag` resource (RagStore.connect); `create extension vector`
works there. Copy asset and check shapes from pipelines/reference/patterns.py.

Tables (schema rag): pages (one row per published page: its ETag, its body, and the ETag it was last
chunked at) and chunks (id = content hash, embedding null until embedded). The author's decisions are the
constants below; while one is None, the asset that needs it fails and says so.
"""

import dagster as dg

from ..chunking import chunk_markdown
from ..resources import LlmEmbed, RagStore, WikiApi

# Decision 015: chunk size and overlap, in estimated tokens (labpipes/chunking.py). None = not decided.
CHUNK_MAX_TOKENS: int | None = None
CHUNK_OVERLAP_TOKENS: int | None = None
# Decision 016: the vector index, "hnsw" or "ivfflat". None = not decided (retrieval still works, by a
# sequential scan, which is fine at a few hundred chunks).
VECTOR_INDEX: str | None = None

DIMENSIONS = 768

SCHEMA = f"""
create extension if not exists vector;
create schema if not exists rag;
create table if not exists rag.pages (
  id text primary key,
  title text not null,
  updated_at text not null,
  etag text not null,
  body text not null,
  chunked_etag text,
  fetched_at timestamptz not null default now()
);
create table if not exists rag.chunks (
  id text primary key,
  page_id text not null references rag.pages (id) on delete cascade,
  idx int not null,
  heading text not null,
  content text not null,
  tokens int not null,
  embedding vector({DIMENSIONS})
);
create index if not exists chunks_page on rag.chunks (page_id);
"""

INDEXES = {  # pgvector 0.8: cosine distance (<=>) is what the app's retrieval orders by
    "hnsw": "create index if not exists chunks_embedding_hnsw on rag.chunks using hnsw (embedding vector_cosine_ops)",
    "ivfflat": "create index if not exists chunks_embedding_ivfflat on rag.chunks using ivfflat (embedding vector_cosine_ops)",
}


def vector_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


@dg.asset(group_name="rag", kinds={"postgres"})
def wiki_pages(context: dg.AssetExecutionContext, wiki: WikiApi, rag: RagStore) -> dg.MaterializeResult:
    """Conditional GET of every published page; a 304 costs no body. Unpublished pages are deleted (and
    their chunks with them)."""
    client = wiki.client()
    refs = client.pages()
    conn = rag.connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(SCHEMA)
            cur.execute("select id, etag from rag.pages")
            known = dict(cur.fetchall())
        fetched = unchanged = 0
        for ref in refs:
            page = client.page(ref.id, known.get(ref.id))
            if page is None:
                unchanged += 1
                continue
            fetched += 1
            with conn, conn.cursor() as cur:
                cur.execute(
                    "insert into rag.pages (id, title, updated_at, etag, body) values (%s, %s, %s, %s, %s) "
                    "on conflict (id) do update set title = excluded.title, updated_at = excluded.updated_at, "
                    "etag = excluded.etag, body = excluded.body, fetched_at = now()",
                    (page.id, page.title, page.updated_at, page.etag, page.body),
                )
        gone = sorted(set(known) - {r.id for r in refs})
        if gone:
            with conn, conn.cursor() as cur:
                cur.execute("delete from rag.pages where id = any(%s)", (gone,))
    finally:
        conn.close()
    context.log.info(f"{len(refs)} pages: {fetched} fetched, {unchanged} unchanged (304), {len(gone)} deleted")
    return dg.MaterializeResult(metadata={
        "pages": dg.MetadataValue.int(len(refs)),
        "pages_fetched": dg.MetadataValue.int(fetched),
        "pages_unchanged": dg.MetadataValue.int(unchanged),
        "pages_deleted": dg.MetadataValue.int(len(gone)),
    })


@dg.asset(deps=[wiki_pages], group_name="rag", kinds={"postgres"})
def wiki_chunks(context: dg.AssetExecutionContext, rag: RagStore) -> dg.MaterializeResult:
    """Re-chunk only pages whose ETag changed since they were last chunked. A chunk's id is its content
    hash, so a chunk whose text didn't change keeps its row and its vector."""
    if CHUNK_MAX_TOKENS is None or CHUNK_OVERLAP_TOKENS is None:
        raise dg.Failure("not decided yet: set CHUNK_MAX_TOKENS and CHUNK_OVERLAP_TOKENS in defs/rag.py (decision 015)")
    conn = rag.connect()
    added = removed = pages = 0
    try:
        with conn, conn.cursor() as cur:
            cur.execute("select id, title, body, etag from rag.pages where chunked_etag is distinct from etag")
            todo = cur.fetchall()
        for page_id, title, body, etag in todo:
            chunks = chunk_markdown(title, body, CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS)
            rows = {c.content_hash(page_id): c for c in chunks}
            with conn, conn.cursor() as cur:
                cur.execute("select id from rag.chunks where page_id = %s", (page_id,))
                existing = {r[0] for r in cur.fetchall()}
                cur.execute("delete from rag.chunks where page_id = %s and not (id = any(%s))", (page_id, list(rows)))
                removed += cur.rowcount
                for cid, c in rows.items():
                    cur.execute(
                        "insert into rag.chunks (id, page_id, idx, heading, content, tokens) values (%s, %s, %s, %s, %s, %s) "
                        "on conflict (id) do update set idx = excluded.idx",
                        (cid, page_id, c.index, c.heading, c.text, c.tokens),
                    )
                added += len(set(rows) - existing)
                cur.execute("update rag.pages set chunked_etag = %s where id = %s", (etag, page_id))  # the version chunked
            pages += 1
        with conn, conn.cursor() as cur:
            cur.execute("select count(*), count(*) filter (where embedding is null) from rag.chunks")
            total, unembedded = cur.fetchone()
    finally:
        conn.close()
    context.log.info(f"re-chunked {pages} pages: {added} chunks added, {removed} removed; {total} chunks, {unembedded} without a vector")
    return dg.MaterializeResult(metadata={
        "pages_chunked": dg.MetadataValue.int(pages),
        "chunks_added": dg.MetadataValue.int(added),
        "chunks_removed": dg.MetadataValue.int(removed),
        "chunks": dg.MetadataValue.int(total),
        "chunks_without_vector": dg.MetadataValue.int(unembedded),
        "max_tokens": dg.MetadataValue.int(CHUNK_MAX_TOKENS),
        "overlap_tokens": dg.MetadataValue.int(CHUNK_OVERLAP_TOKENS),
    })


@dg.asset(deps=[wiki_chunks], group_name="rag", kinds={"postgres"})
def wiki_embeddings(context: dg.AssetExecutionContext, embed: LlmEmbed, rag: RagStore) -> dg.MaterializeResult:
    """Embed only the chunks without a vector, then make sure the index exists."""
    conn = rag.connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("select id, content from rag.chunks where embedding is null order by page_id, idx")
            todo = cur.fetchall()
        for i in range(0, len(todo), embed.batch):
            batch = todo[i : i + embed.batch]
            vectors = embed.embed_documents([content for _, content in batch])
            with conn, conn.cursor() as cur:
                for (cid, _), v in zip(batch, vectors, strict=True):
                    cur.execute("update rag.chunks set embedding = %s::vector where id = %s", (vector_literal(v), cid))
        index = "none (sequential scan)"
        if VECTOR_INDEX is not None:
            with conn, conn.cursor() as cur:
                cur.execute(INDEXES[VECTOR_INDEX])
            index = VECTOR_INDEX
        with conn, conn.cursor() as cur:
            cur.execute("select count(*) from rag.chunks")
            total = cur.fetchone()[0]
    finally:
        conn.close()
    context.log.info(f"embedded {len(todo)} chunks; {total} chunks in all; index: {index}")
    return dg.MaterializeResult(metadata={
        "chunks_embedded": dg.MetadataValue.int(len(todo)),
        "chunks": dg.MetadataValue.int(total),
        "index": index,
    })


@dg.asset_check(asset=wiki_embeddings, blocking=True, description="Every chunk has a vector of the right size.")
def every_chunk_embedded(rag: RagStore) -> dg.AssetCheckResult:
    conn = rag.connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(f"select count(*), count(*) filter (where embedding is null or vector_dims(embedding) <> {DIMENSIONS}) from rag.chunks")
            total, missing = cur.fetchone()
    finally:
        conn.close()
    return dg.AssetCheckResult(
        passed=total > 0 and missing == 0,
        severity=dg.AssetCheckSeverity.ERROR,
        description=f"{missing} of {total} chunks have no {DIMENSIONS}-dimension vector" if missing or not total else f"all {total} chunks embedded",
        metadata={"chunks": dg.MetadataValue.int(total), "missing": dg.MetadataValue.int(missing)},
    )


ingest_wiki = dg.define_asset_job("ingest_wiki", selection=dg.AssetSelection.assets(wiki_pages, wiki_chunks, wiki_embeddings))

# Daily: the wiki is re-read once a day (stages/S6.md); unchanged pages cost a 304 each.
ingest_wiki_daily = dg.ScheduleDefinition(job=ingest_wiki, cron_schedule="0 5 * * *", execution_timezone="UTC",
                                          default_status=dg.DefaultScheduleStatus.RUNNING)
