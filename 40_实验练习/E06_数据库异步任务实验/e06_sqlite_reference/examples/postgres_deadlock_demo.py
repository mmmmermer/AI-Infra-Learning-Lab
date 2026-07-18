from __future__ import annotations

import argparse
import os
import threading
from uuid import uuid4

try:
    import psycopg
    from psycopg import sql
    from psycopg.errors import DeadlockDetected
except ModuleNotFoundError as error:
    raise SystemExit(
        "psycopg is required; install requirements-postgres.lock first"
    ) from error


def run_transaction(
    dsn: str,
    table_name: str,
    first_row: int,
    second_row: int,
    barrier: threading.Barrier,
    outcomes: dict[str, str],
    session_name: str,
) -> None:
    try:
        with psycopg.connect(dsn, application_name=f"e06-{session_name}") as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute(
                        sql.SQL("UPDATE {} SET value = value + 1 WHERE id = %s").format(
                            sql.Identifier(table_name)
                        ),
                        (first_row,),
                    )
                    barrier.wait(timeout=10)
                    cursor.execute(
                        sql.SQL("UPDATE {} SET value = value + 1 WHERE id = %s").format(
                            sql.Identifier(table_name)
                        ),
                        (second_row,),
                    )
                connection.commit()
                outcomes[session_name] = "committed"
            except DeadlockDetected as error:
                connection.rollback()
                outcomes[session_name] = f"deadlock:{error.sqlstate}"
    except Exception as error:
        barrier.abort()
        outcomes[session_name] = f"error:{type(error).__name__}:{error}"


def run_demo(dsn: str) -> tuple[dict[str, str], list[tuple[int, int]]]:
    table_name = f"e06_deadlock_{uuid4().hex}"
    create_table = sql.SQL(
        "CREATE TABLE {} (id integer PRIMARY KEY, value integer NOT NULL)"
    ).format(sql.Identifier(table_name))
    drop_table = sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(table_name))

    with psycopg.connect(dsn, autocommit=True, application_name="e06-setup") as admin:
        with admin.cursor() as cursor:
            cursor.execute(create_table)
            cursor.execute(
                sql.SQL("INSERT INTO {} (id, value) VALUES (1, 0), (2, 0)").format(
                    sql.Identifier(table_name)
                )
            )

    outcomes: dict[str, str] = {}
    barrier = threading.Barrier(2)
    workers = [
        threading.Thread(
            target=run_transaction,
            args=(dsn, table_name, 1, 2, barrier, outcomes, "session-a"),
            daemon=True,
        ),
        threading.Thread(
            target=run_transaction,
            args=(dsn, table_name, 2, 1, barrier, outcomes, "session-b"),
            daemon=True,
        ),
    ]

    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=20)
        if any(worker.is_alive() for worker in workers):
            raise RuntimeError("deadlock demo did not finish within 20 seconds")

        with psycopg.connect(dsn, application_name="e06-verify") as verifier:
            with verifier.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT id, value FROM {} ORDER BY id").format(
                        sql.Identifier(table_name)
                    )
                )
                rows = [(int(row[0]), int(row[1])) for row in cursor.fetchall()]
        return outcomes, rows
    finally:
        with psycopg.connect(dsn, autocommit=True, application_name="e06-cleanup") as admin:
            with admin.cursor() as cursor:
                cursor.execute(drop_table)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reproduce and verify a two-transaction PostgreSQL deadlock."
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("E06_POSTGRES_DSN"),
        help="PostgreSQL DSN; defaults to E06_POSTGRES_DSN",
    )
    args = parser.parse_args()
    if not args.dsn:
        parser.error("provide --dsn or set E06_POSTGRES_DSN")

    outcomes, rows = run_demo(args.dsn)
    print(f"outcomes={outcomes}")
    print(f"rows_after_recovery={rows}")

    values = sorted(outcomes.values())
    if len(values) != 2 or values.count("committed") != 1:
        raise SystemExit("expected exactly one committed transaction")
    deadlocks = [value for value in values if value == "deadlock:40P01"]
    if len(deadlocks) != 1:
        raise SystemExit("expected exactly one PostgreSQL 40P01 deadlock victim")
    if rows != [(1, 1), (2, 1)]:
        raise SystemExit("victim rollback invariant failed")

    print("verified: one victim rolled back and one transaction committed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
