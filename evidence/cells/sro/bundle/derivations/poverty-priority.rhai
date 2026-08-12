fn derive(facts, selectors, evaluation_context) {
    [#{concept_id: "https://id.registrystack.org/solmara/concept/household-below-poverty-threshold", value: required(facts["poverty_band"], "required_fact_missing") == "priority"}]
}
