fn derive(facts, selectors, evaluation_context) {
    if required(facts["uin"], "required_fact_missing") != selectors["subject"]["values"]["uin"] {
        throw("derivation_input_error");
    }
    let birth_date = parse_date(required(facts["birth_date"], "required_fact_missing"));
    let fifth_birthday = add_calendar_years(birth_date, 5);
    let as_of_date = parse_date(evaluation_context["parameters"]["as_of_date"]);
    let registered = required(facts["birth_registered"], "required_fact_missing");
    let under_five = !required(facts["deceased"], "required_fact_missing") &&
        compare_dates(as_of_date, birth_date) >= 0 &&
        compare_dates(as_of_date, fifth_birthday) < 0;
    [
        #{concept_id: "https://id.registrystack.org/solmara/concept/birth-is-registered", value: registered},
        #{concept_id: "https://id.registrystack.org/solmara/concept/child-age-under-5", value: under_five}
    ]
}
