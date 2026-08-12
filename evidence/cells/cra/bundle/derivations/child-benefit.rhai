fn derive(facts, selectors, evaluation_context) {
    let birth_date = parse_date(required(facts["birth_date"], "required_fact_missing"));
    let fifth_birthday = add_calendar_years(birth_date, 5);
    let as_of_date = parse_date(evaluation_context["parameters"]["as_of_date"]);
    [
        #{concept_id: "https://id.registrystack.org/solmara/concept/birth-is-registered", value: required(facts["birth_registered"], "required_fact_missing")},
        #{concept_id: "https://id.registrystack.org/solmara/concept/child-age-under-5", value: compare_dates(as_of_date, birth_date) >= 0 && compare_dates(as_of_date, fifth_birthday) < 0}
    ]
}
