fn derive(facts, selectors, evaluation_context) {
    [#{concept_id: "https://id.registrystack.org/solmara/concept/survivor-is-eligible", value: required(facts["survivor_eligible"], "required_fact_missing")}]
}
