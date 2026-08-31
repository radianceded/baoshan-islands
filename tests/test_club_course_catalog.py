import unittest
from collections import Counter

from server.club_courses import COURSES, COURSES_BY_ID, SEMESTER


class ClubCourseCatalogTests(unittest.TestCase):
    def test_imported_catalog_has_expected_source_breakdown(self):
        self.assertEqual(SEMESTER, "2026学年第一学期")
        self.assertEqual(len(COURSES), 70)
        self.assertEqual(
            Counter(course["selection_mode"] for course in COURSES),
            {"selectable": 51, "info_only": 13, "draft": 6},
        )
        self.assertEqual(
            Counter(course["campus"] for course in COURSES),
            {"东校区": 52, "西校区": 18},
        )
        self.assertEqual(len(COURSES_BY_ID), len(COURSES))

    def test_grade_scope_matches_the_two_sites(self):
        for course in COURSES:
            with self.subTest(course=course["id"]):
                self.assertEqual(course["semester"], SEMESTER)
                if course["campus"] == "西校区":
                    self.assertTrue(
                        set(course["eligible_grades"]) <= {"一年级", "二年级"}
                    )
                elif course["campus"] == "东校区":
                    if course["selection_mode"] == "draft":
                        continue
                    self.assertTrue(
                        set(course["eligible_grades"]) <= {"三年级", "四年级", "五年级"}
                    )

    def test_non_selectable_courses_are_never_exposed_as_open(self):
        for course in COURSES:
            if course["selection_mode"] != "selectable":
                self.assertEqual(course["capacity"], 1)


if __name__ == "__main__":
    unittest.main()
