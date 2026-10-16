"""Simulated citizen registry used to demonstrate linking a violation to a person.

All records are fictional. The real system would need authorised access to an
identity database, which is out of scope for this prototype.
"""
from __future__ import annotations

import random

from .db import utcnow

FIRST = ["Aarav", "Vivaan", "Aditya", "Ishaan", "Rohan", "Kabir", "Arjun", "Karan", "Yash", "Dev",
         "Ananya", "Diya", "Saanvi", "Isha", "Meera", "Kavya", "Riya", "Priya", "Nisha", "Pooja"]
LAST = ["Sharma", "Verma", "Gupta", "Singh", "Kumar", "Mehta", "Malhotra", "Arora", "Bansal", "Chopra",
        "Kapoor", "Joshi", "Saxena", "Agarwal", "Bhatia"]
AREAS = ["Pitampura", "Rohini Sector 7", "Shalimar Bagh", "Model Town", "Karol Bagh", "Janakpuri",
         "Lajpat Nagar", "Dwarka Sector 10", "Mayur Vihar", "Saket", "Paschim Vihar", "Ashok Vihar"]


def make_citizens(n: int = 30, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    used = set()
    people = []
    while len(people) < n:
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        if name in used:
            continue
        used.add(name)
        i = len(people) + 1
        people.append({
            "_id": f"cit_{i:04d}",
            "citizen_ref": f"SIM-{i:04d}",
            "name": name,
            "phone": f"9{rng.randint(100, 999)}XXXX{rng.randint(10, 99)}",
            "address": f"{rng.randint(1, 250)}, {rng.choice(AREAS)}, Delhi",
            "simulated": True,
            "created_at": utcnow(),
        })
    return people


async def seed_citizens(db) -> int:
    if await db.citizens.count_documents({}) > 0:
        return 0
    people = make_citizens()
    await db.citizens.insert_many(people)
    return len(people)
