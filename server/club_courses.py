# -*- coding: utf-8 -*-
"""2026 学年第一学期本部社团目录种子。"""

import json
from pathlib import Path


SEMESTER = "2026学年第一学期"


with (Path(__file__).with_name("club_courses_2026s1.json")).open(encoding="utf-8") as source:
    COURSES = json.load(source)

for course in COURSES:
    course["semester"] = SEMESTER

COURSES_BY_ID = {course["id"]: course for course in COURSES}
