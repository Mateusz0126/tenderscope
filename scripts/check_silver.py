
import duckdb


def main() -> None:
    con = duckdb.connect(":memory:")

    con.execute("""
        CREATE VIEW notice AS
        SELECT * FROM read_parquet('data/silver/notice.parquet')
    """)

    con.execute("""
        CREATE VIEW notice_cpv AS
        SELECT * FROM read_parquet('data/silver/notice_cpv.parquet')
    """)

    con.execute("""
        CREATE VIEW notice_buyer AS
        SELECT * FROM read_parquet('data/silver/notice_buyer.parquet')
    """)

    print("\n=== DATA QUALITY ===")

    print(con.sql("""
        SELECT
            COUNT(*) AS total_notices,
            COUNT(DISTINCT notice_id) AS unique_notices,
            COUNT(*) - COUNT(DISTINCT notice_id) AS duplicates,
            COUNT(*) FILTER (
                WHERE title_pl IS NULL OR TRIM(title_pl) = ''
            ) AS missing_titles
        FROM notice
    """))

    print("\n=== CPV DISTRIBUTION ===")

    print(con.sql("""
        SELECT
            cpv_code,
            COUNT(DISTINCT notice_id) AS notice_count
        FROM notice_cpv
        GROUP BY cpv_code
        ORDER BY notice_count DESC, cpv_code
        LIMIT 10
    """))

    print("\n=== ORPHAN CPV RELATIONSHIPS ===")

    print(con.sql("""
        SELECT COUNT(*) AS orphan_count
        FROM notice_cpv c
        LEFT JOIN notice n
            ON c.notice_id = n.notice_id
        WHERE n.notice_id IS NULL
    """))

    con.close()


if __name__ == "__main__":
    main()
