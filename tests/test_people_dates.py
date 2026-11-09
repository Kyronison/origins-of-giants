import unittest
from orchestrator.stages.story import _validate_people, _fact_life_years

class PeopleDatesTests(unittest.TestCase):
    def scene(self):
        return {"id":"v6_1", "type":"people", "anchor":"Martin Shugrue", "slots":[],
                "data":{"persons":[{"name":"Martin Shugrue", "years":"1933–2008"}]}}

    def test_missing_registry_dates_do_not_accept_generated_dates(self):
        sc, _ = _validate_people(self.scene(), "Martin Shugrue became trustee.",
                               {"cast":[{"name":"Martin Shugrue", "years":""}]})
        self.assertEqual(sc["data"]["persons"][0]["years"], "")
        self.assertEqual(sc["slots"][0]["years"], "")

    def test_verified_registry_dates_replace_wrong_generated_dates(self):
        sc, _ = _validate_people(self.scene(), "Martin Shugrue became trustee.",
                               {"cast":[{"name":"Martin Shugrue", "years":"1940–1999"}]})
        self.assertEqual(sc["data"]["persons"][0]["years"], "1940–1999")

    def test_narration_name_without_registry_cannot_source_life_dates(self):
        sc, _ = _validate_people(self.scene(), "Martin Shugrue became trustee.", {"cast":[]})
        self.assertEqual(sc["data"]["persons"][0]["years"], "")

    def test_generated_cast_dates_are_not_a_source(self):
        c={"name":"Harold Pitcairn","years":"1897–1965"}
        self.assertEqual(_fact_life_years(c,[{"text":"Harold Pitcairn founded the company in 1927."}]),"")

    def test_biographical_fact_must_match_both_dates(self):
        facts=[{"text":"Harold Pitcairn was born in 1897 and died in 1960."}]
        self.assertEqual(_fact_life_years({"name":"Harold Pitcairn","years":"1897–1960"},facts),"1897–1960")
        self.assertEqual(_fact_life_years({"name":"Harold Pitcairn","years":"1897–1965"},facts),"")

    def test_dates_for_a_different_person_cannot_support_the_cast_record(self):
        facts=[{"text":"Another Pilot was born in 1897 and died in 1965."}]
        self.assertEqual(_fact_life_years({"name":"Harold Pitcairn","years":"1897–1965"},facts),"")

    def test_fathers_death_is_not_the_subjects_death(self):
        facts=[{'text':'Harold Pitcairn was born in 1897; his father died in 1965.'}]
        self.assertEqual(_fact_life_years({'name':'Harold Pitcairn','years':'1897–1965'},facts),'')

    def test_year_of_company_event_is_not_a_death_date(self):
        facts=[{'text':'Harold Pitcairn was born in 1897 and died in 1960; the company was sold in 1965.'}]
        self.assertEqual(_fact_life_years({'name':'Harold Pitcairn','years':'1897–1965'},facts),'')
        self.assertEqual(_fact_life_years({'name':'Harold Pitcairn','years':'1897–1960'},facts),'1897–1960')
