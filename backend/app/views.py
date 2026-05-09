from sqlalchemy import text
from sqlalchemy.engine import Engine


def create_sqlite_views(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS v_gov_overview"))
        conn.execute(text("DROP VIEW IF EXISTS v_store_stats"))
        conn.execute(text("DROP VIEW IF EXISTS v_abnormal_events"))

        conn.execute(
            text(
                """
                CREATE VIEW v_gov_overview AS
                SELECT
                    COALESCE(SUM(l.item_count), 0) AS loans_total,
                    COALESCE(SUM(l.returned_count), 0) AS returned_total,
                    ROUND(
                        CASE
                            WHEN COALESCE(SUM(l.item_count), 0) = 0 THEN 0
                            ELSE CAST(COALESCE(SUM(l.returned_count), 0) AS REAL) / SUM(l.item_count)
                        END,
                        4
                    ) AS recovery_rate,
                    COALESCE(SUM(
                        CASE
                            WHEN l.returned_at IS NOT NULL
                                AND (l.returned_at > l.due_at OR COALESCE(l.return_condition, 'normal') != 'normal')
                            THEN l.returned_count
                            ELSE 0
                        END
                    ), 0) AS abnormal_total,
                    COALESCE(SUM(l.deposit_amount * l.item_count), 0) AS deposit_total,
                    COALESCE(SUM(r.refund_amount), 0) AS refund_total
                FROM loans l
                LEFT JOIN refund_ledgers r ON r.loan_id = l.id
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE VIEW v_store_stats AS
                SELECT
                    s.id AS store_id,
                    s.code AS store_code,
                    s.name AS store_name,
                    COALESCE(issued.issued_count, 0) AS issued_count,
                    COALESCE(returned.returned_count, 0) AS returned_count,
                    COALESCE(returned.cross_store_count, 0) AS cross_store_count,
                    COALESCE(returned.abnormal_count, 0) AS abnormal_count
                FROM stores s
                LEFT JOIN (
                    SELECT issued_store_id AS store_id, SUM(item_count) AS issued_count
                    FROM loans
                    GROUP BY issued_store_id
                ) issued ON issued.store_id = s.id
                LEFT JOIN (
                    SELECT
                        returned_store_id AS store_id,
                        SUM(returned_count) AS returned_count,
                        SUM(CASE WHEN returned_store_id != issued_store_id THEN returned_count ELSE 0 END) AS cross_store_count,
                        SUM(
                            CASE
                                WHEN returned_at > due_at OR COALESCE(return_condition, 'normal') != 'normal'
                                THEN returned_count
                                ELSE 0
                            END
                        ) AS abnormal_count
                    FROM loans
                    WHERE returned_count > 0
                    GROUP BY returned_store_id
                ) returned ON returned.store_id = s.id
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE VIEW v_abnormal_events AS
                SELECT
                    se.id AS event_id,
                    se.created_at,
                    se.result,
                    se.reason,
                    se.note,
                    se.store_id,
                    s.code AS store_code,
                    s.name AS store_name,
                    se.loan_id,
                    l.invoice_code,
                    l.container_type,
                    l.issued_store_id,
                    l.returned_store_id,
                    l.issued_at,
                    l.due_at,
                    l.returned_at,
                    l.return_condition
                FROM scan_events se
                LEFT JOIN stores s ON s.id = se.store_id
                LEFT JOIN loans l ON l.id = se.loan_id
                WHERE
                    se.result != 'returned'
                    OR se.reason IS NOT NULL
                    OR (l.returned_at IS NOT NULL AND l.returned_at > l.due_at)
                    OR COALESCE(l.return_condition, 'normal') != 'normal'
                """
            )
        )
