import asyncio
from sqlalchemy import text
from app.db.session import engine

DDL_PATH = "sql/wcoa_schema.sql"


def split_sql(sql: str) -> list[str]:
    statements = []
    current = []
    in_single = False
    in_double = False
    in_dollar = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        nxt2 = sql[i:i+2]
        if not in_single and not in_double and nxt2 == "$$":
            in_dollar = not in_dollar
            current.append(nxt2)
            i += 2
            continue
        if not in_double and not in_dollar and ch == "'":
            in_single = not in_single
        elif not in_single and not in_dollar and ch == '"':
            in_double = not in_double
        if ch == ";" and not in_single and not in_double and not in_dollar:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


async def main():
    with open(DDL_PATH, "r", encoding="utf-8") as f:
        ddl = f.read()
    async with engine.begin() as conn:
        for stmt in split_sql(ddl):
            await conn.execute(text(stmt))
    print("DB initialized.")


if __name__ == "__main__":
    asyncio.run(main())
