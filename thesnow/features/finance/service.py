from dataclasses import dataclass

from thesnow.core.database import Database
from thesnow.shared.validation import Oops


@dataclass(frozen=True)
class LoanRecord:
    """Active or settled loan record."""

    loan_id: int
    party: str
    direction: str
    total: int
    paid: int
    note: str


async def get_active_loans(db: Database, guild_id: int) -> list[LoanRecord]:
    """Fetch all unpaid loans for a guild."""
    rows = await db.many(
        "SELECT id, party, direction, total, paid, note FROM loans "
        "WHERE guild_id=? AND paid<total ORDER BY id",
        (guild_id,),
    )
    return [
        LoanRecord(
            loan_id=int(row["id"]),
            party=str(row["party"]),
            direction=str(row["direction"]),
            total=int(row["total"]),
            paid=int(row["paid"]),
            note=str(row["note"] or ""),
        )
        for row in rows
    ]


async def create_loan(
    db: Database,
    guild_id: int,
    *,
    party: str,
    direction: str,
    amount: int,
    note: str,
) -> int:
    """Create a loan record atomically and return its new ID."""
    return await db.insert(
        "INSERT INTO loans(guild_id,party,direction,total,note) VALUES(?,?,?,?,?)",
        (guild_id, party, direction, amount, note),
    )


async def pay_loan(
    db: Database,
    guild_id: int,
    *,
    query: str,
    amount: int,
) -> tuple[LoanRecord, int, bool]:
    """Atomically apply a payment toward a loan matched by #ID or party name."""
    target = query.strip()
    if not target:
        raise Oops("Enter a person name or Loan #ID.")

    async with db.transaction():
        multiple_matches = False
        stripped_id = target.lstrip("#")
        if stripped_id.isdigit():
            row = await db.one(
                "SELECT id, party, direction, total, paid, note FROM loans "
                "WHERE id=? AND guild_id=? AND paid<total",
                (int(stripped_id), guild_id),
            )
        else:
            rows = await db.many(
                "SELECT id, party, direction, total, paid, note FROM loans "
                "WHERE guild_id=? AND LOWER(party)=LOWER(?) AND paid<total ORDER BY id",
                (guild_id, target),
            )
            row = rows[0] if rows else None
            multiple_matches = len(rows) > 1

        if row is None:
            raise Oops(f"No active loan found for `{target}`.")

        loan = LoanRecord(
            loan_id=int(row["id"]),
            party=str(row["party"]),
            direction=str(row["direction"]),
            total=int(row["total"]),
            paid=int(row["paid"]),
            note=str(row["note"] or ""),
        )
        left = loan.total - loan.paid
        if amount > left:
            raise Oops(f"Only ${left:,} left on loan #{loan.loan_id} ({loan.party}).")

        updated = await db.run(
            "UPDATE loans SET paid=paid+? WHERE id=? AND guild_id=? AND total-paid>=?",
            (amount, loan.loan_id, guild_id, amount),
        )
        if updated != 1:
            raise Oops("Loan balance changed concurrently; please try again.")

        return loan, left - amount, multiple_matches
