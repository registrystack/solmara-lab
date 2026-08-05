fn derive(facts, selectors, evaluation_context) {
    if required(facts["spouse_uin"], "required_fact_missing") != selectors["subject"]["values"]["uin"] {
        throw("derivation_input_error");
    }
    [#{concept_id: "https://id.registrystack.org/solmara/concept/survivor-is-eligible", value: required(facts["survivor_eligible"], "required_fact_missing")}]
}
