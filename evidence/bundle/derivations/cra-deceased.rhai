fn derive(facts, selectors, evaluation_context) {
    if required(facts["uin"], "required_fact_missing") != selectors["subject"]["values"]["uin"] {
        throw("derivation_input_error");
    }
    [#{concept_id: "https://id.registrystack.org/solmara/concept/person-is-deceased", value: required(facts["deceased"], "required_fact_missing")}]
}
