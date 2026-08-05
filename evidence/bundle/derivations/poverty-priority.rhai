fn derive(facts, selectors, evaluation_context) {
    if required(facts["uin"], "required_fact_missing") != selectors["subject"]["values"]["uin"] {
        throw("derivation_input_error");
    }
    [#{concept_id: "https://id.registrystack.org/solmara/concept/household-below-poverty-threshold", value: required(facts["poverty_band"], "required_fact_missing") == "priority"}]
}
