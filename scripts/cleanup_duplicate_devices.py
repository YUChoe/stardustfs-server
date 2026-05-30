"""중복 디바이스 정리 스크립트.

같은 user_id + name + os 조합에서 가장 최근 것만 남기고 나머지 삭제.
"""
import sqlite3


def main():
    conn = sqlite3.connect("data/stardustfs.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 중복 그룹 찾기 (같은 user_id + name + os)
    cursor.execute("""
        SELECT user_id, name, os, COUNT(*) as cnt
        FROM devices
        GROUP BY user_id, name, os
        HAVING cnt > 1
    """)
    duplicates = cursor.fetchall()

    if not duplicates:
        print("중복 디바이스 없음.")
        conn.close()
        return

    total_deleted = 0
    for dup in duplicates:
        user_id = dup["user_id"]
        name = dup["name"]
        os_name = dup["os"]
        print(f"중복 발견: user={user_id}, name={name}, os={os_name} ({dup['cnt']}개)")

        # 가장 최근 heartbeat 것만 남기고 삭제
        cursor.execute("""
            DELETE FROM devices
            WHERE user_id = ? AND name = ? AND os = ?
            AND id NOT IN (
                SELECT id FROM devices
                WHERE user_id = ? AND name = ? AND os = ?
                ORDER BY last_heartbeat DESC
                LIMIT 1
            )
        """, (user_id, name, os_name, user_id, name, os_name))
        deleted = cursor.rowcount
        total_deleted += deleted
        print(f"  -> {deleted}개 삭제")

    conn.commit()
    conn.close()
    print(f"\n총 {total_deleted}개 중복 디바이스 삭제 완료.")


if __name__ == "__main__":
    main()
